#! /usr/bin/env nix-shell
#! nix-shell -i python3 --pure -p "pkgs.python3.withPackages(ps: with ps; [ requests ])" nix

# consider using click to make the CLI
# - update (updates the local database with the latest eval)
# - update --eval <eval_id> (updates the local database with a specific eval)
# - update --use-cached (updates the local database with the latest cached eval)
# - update --missing-status (update all rows in the local database that are missing a build status)
# - mark-broken <path/to/nixpkgs> (generates a list of broken attrs/packages and marks them broken)
# - mark-broken --dry-run <path/to/nixpkgs> (generates a list of broken attrs/packages to be marked broken)

#💡 the hydra endpoint /{project-id}/{jobset-id}/{job-id}/latest (as documented here: https://github.com/NixOS/hydra/issues/1036) will return the latest _working_ build for a job! This makes it very easy to see how long a job has been broken already.
import argparse
from collections import defaultdict
import datetime
import hashlib
import json
from multiprocessing import JoinableQueue, Process, Queue
import requests
import sqlite3
import sys
import mark_broken_v2

class EvalFetcher:
    def fetch(self, baseurl, jobset):
        start = datetime.datetime.now()
        evals = requests.get(f"{baseurl}/jobset/{jobset}/evals", headers={"Accept": "application/json"})
        print("requesting evals took", datetime.datetime.now() - start)

        baseurl_hash = hashlib.sha1(baseurl.encode()).hexdigest()
        jobset_hash = hashlib.sha1(jobset.encode()).hexdigest()
        filename = f"evals-{baseurl_hash}-{jobset_hash}.json"
        print(f"Create eval cache with filename {filename}")
        with open(filename, "w") as eval_file:
            print(evals.text, file=eval_file)

        # TODO(ricsch): Handle errors

        all_evals = evals.json()["evals"]

        print(f"number of evals: {len(all_evals)}")

        return all_evals

    def get_cache(self):
        baseurl_hash = hashlib.sha1(baseurl.encode()).hexdigest()
        jobset_hash = hashlib.sha1(jobset.encode()).hexdigest()
        filename = f"evals-{baseurl_hash}-{jobset_hash}.json"
        print(f"Loading cache from {filename}")
        with open(filename, "r") as eval_file:
            return json.load(eval_file)["evals"]

class BuildsInEvalFetcher:
    def fetch(self, baseurl, eval_id):
        builds = requests.get(f"{baseurl}/eval/{last_eval_id}", headers={"Accept": "application/json"})

        # TODO(ricsch): Handle errors

        all_builds_in_eval = builds.json()["builds"]
        print(f"number of builds: {len(all_builds_in_eval)}")

        baseurl_hash = hashlib.sha1(baseurl.encode()).hexdigest()
        jobset_hash = hashlib.sha1(jobset.encode()).hexdigest()
        with open(f"builds-{baseurl_hash}-{jobset_hash}.json", "w") as build_file:
            print(builds.text, file=build_file)

        return all_builds_in_eval

    def get_cache(self):
        baseurl_hash = hashlib.sha1(baseurl.encode()).hexdigest()
        jobset_hash = hashlib.sha1(jobset.encode()).hexdigest()
        with open(f"builds-{baseurl_hash}-{jobset_hash}.json", "r") as build_file:
            return json.load(build_file)["builds"]

class Database:
    def __init__(self, path):
        self.connection = sqlite3.connect(path)
        self.cursor = self.connection.cursor()

        self.cursor.execute("""CREATE TABLE IF NOT EXISTS build_results(
        id              INT PRIMARY KEY NOT NULL,
        url             TEXT            NOT NULL,
        jobset          TEXT            NOT NULL,
        eval_id         INT             NOT NULL,
        eval_timestamp  INT             NOT NULL,
        status          INT,
        job             TEXT            NOT NULL,
        system          TEXT            NOT NULL
        );
        """)
        self.connection.commit()

    def insert_or_update_build_result(
        self,
        build_id,
        baseurl,
        jobset,
        eval_id,
        timestamp,
        status,
        jobname,
        system
    ):
        if self.get_build_id(build_id) != None:
            # Status is still none, no need to update DB row.
            if status == None:
                return
            else:
                self.update_build_status(build_id, status)
                return
        self.cursor.execute("""INSERT INTO build_results
            (id, url, jobset, eval_id, eval_timestamp, status, job, system)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?)""",
            (build_id, baseurl, jobset, eval_id, timestamp, status, jobname, system))
        self.connection.commit()

    def get_known_builds(self, eval_id):
        known_builds = self.cursor.execute("SELECT id, status FROM build_results WHERE eval_id = ?", (eval_id,))
        found_builds = []
        for [build_id, status] in known_builds:
            found_builds.append((build_id, status))
        return found_builds

    def get_build_id(self, build_id):
        res = self.cursor.execute("SELECT id, status FROM build_results WHERE id = ?", (build_id,))
        return res.fetchone()

    def update_build_status(self, build_id, new_status):
        self.cursor.execute("UPDATE build_results SET status = ? WHERE id = ?", (new_status, build_id))
        self.connection.commit()

    def get_broken_builds(self):
        # Select only latest builds (highest timestamp per job.system combination)
        res = self.cursor.execute("SELECT id, status, job, system, url, jobset FROM (SELECT id, status, job, system, url, jobset, max(eval_timestamp) over (partition by job, system) max_eval_timestamp FROM build_results WHERE status IS NOT NULL) WHERE status != 0 GROUP by job,system")
        return res.fetchall()

    def get_estimated_last_working_build(self, jobname, system):
        res = self.cursor.execute("SELECT id, status, max(eval_timestamp) FROM build_results WHERE status = 0 AND job = ? AND system = ?", (jobname, system))
        return res.fetchone()

class BuildFetcher(Process):
    def __init__(self, baseurl, work_queue, result_queue):
        super(BuildFetcher, self).__init__()
        self.baseurl = baseurl
        self.work_queue = work_queue
        self.result_queue = result_queue

    def run(self):
        for build_id in iter(self.work_queue.get, None):
            build_result = requests.get(f"{self.baseurl}/build/{build_id}", headers={"Accept": "application/json"})
            try:
                job = build_result.json()["job"]
                status = build_result.json()["buildstatus"]
                timestamp = build_result.json()["timestamp"]
                build_system = build_result.json()["system"]
            except:
                print(f"build {build_id} unknown status, {build_result}", file=sys.stderr)
                self.work_queue.task_done()
                return
            # status can be:
            #   None: not built yet
            #   0: success
            #   1: Build returned a non-zero exit code
            #   2: dependency failed
            #   3: aborted
            #   4: canceled by the user
            #   6: failed with output
            #   7: timed out
            #   9: aborted
            #   10: log size limit exceeded
            #   11: output limit exceeded
            if "." in job:
                jobname, system = job.rsplit(".", maxsplit=1)
                # Sanity check for system name.
                known_system = system in ["aarch64-linux", "x86_64-linux", "x86_64-darwin", "aarch64-darwin"]
                # e.g. stdenvBootstrapTools.x86_64-darwin.test, or stdenvBootstrapTools.x86_64-darwin.dist
                # let's just skip em for now.
                host_is_not_build = system != build_system
                if not known_system:
                    print(f"Unknown system {system} in job {job} with id {build_id}, skipping")
                elif host_is_not_build:
                    print(f"Host system {system} is not equal to build system {build_system}")
                else:
                    # For now, make this a hard assumption. We can always relax later.
                    assert(system == build_system)
                    self.result_queue.put((build_id, baseurl, last_eval_id, timestamp, status, jobname, system))
            else:
                print(f"Job without system (job: {job}, id: {build_id}, status: {status}), skipping")
            self.work_queue.task_done()
        self.result_queue.put(None)
        # Call task_done() for the 'None' item too.
        self.work_queue.task_done()

def list_broken_pkgs(database):
    print("Listing broken pkgs")
    broken_builds = database.get_broken_builds()
    already_done_jobs = []
    never_built_ok = []
    previously_successful = []
    print(f"There are {len(broken_builds)} builds to consider")
    broken_builds.sort(key=lambda k:k[2])
    counter = 0
    for [id, status, jobname, system, baseurl, jobset] in broken_builds:
        if counter % 100 == 0 and counter != 0:
            print(f"Checked {counter}/{len(broken_builds)} packages")
        counter += 1
        if status != 1:
            continue
        if 'Packages.' in jobname or 'Packages_' in jobname or 'linuxKernel.' in jobname or 'linuxPackages_' in jobname or 'tests.' in jobname:
            continue
        if (jobname, system, status) in already_done_jobs:
            #print(f"Skip duplicate job {job}.{system}")
            continue
        lwb_id, lwb_status, lwb_timestamp = database.get_estimated_last_working_build(jobname, system)
        if lwb_id != None:
            #lwb_human_time = datetime.datetime.fromtimestamp(lwb_timestamp)
            #print(f"last working build: {jobname}.{system}, status: {lwb_status}, timestamp: {lwb_human_time}, id: {lwb_id}")
            previously_successful.append((id, status, jobname, system, lwb_timestamp, baseurl, jobset))
            continue
        already_done_jobs.append((jobname, system, status))
        url = f"{baseurl}/job/{jobset}/{jobname}.{system}/latest"
        overview_url = f"{baseurl}/job/{jobset}/{jobname}.{system}"
        res = requests.get(url, headers={"Accept": "application/json"}).json()
        if 'error' in res:
            never_built_ok.append((id, status, jobname, system, baseurl, jobset))
        else:
            res_timestamp = res["timestamp"]
            human_time = datetime.datetime.fromtimestamp(res_timestamp)
            previously_successful.append((id, status, jobname, system, res_timestamp, baseurl, jobset))
            # Insert into database
            res_build_id = res["id"]
            # Just grab the latest, it shouldn't matter too much for now.
            res_eval_id = res["jobsetevals"][0]
            res_status = res["buildstatus"]
            database.insert_or_update_build_result(
              res_build_id,
              baseurl,
              jobset,
              res_eval_id,
              res_timestamp,
              res_status,
              jobname,
              system)


    previously_successful.sort(key=lambda k: k[4])
    for [id, status, jobname, system, timestamp, baseurl, jobset] in previously_successful:
        overview_url = f"{baseurl}/job/{jobset}/{jobname}.{system}"
        human_time = datetime.datetime.fromtimestamp(timestamp)
        print(f"build {id} was last successful at {human_time} (status {status}): {jobname}.{system}, overview {overview_url}")
    never_built_ok.sort(key=lambda k: k[2])
    #mark_broken_list = defaultdict(list)
    for [id, status, jobname, system, baseurl, jobset] in never_built_ok:
        overview_url = f"{baseurl}/job/{jobset}/{jobname}.{system}"
        print(f"build {id}: {jobname}.{system} was never successful, overview {overview_url}")
    #    mark_broken_list[jobname].append(system)
    #for [pkgname, platforms] in mark_broken_list.items():
    #    platforms_text = ", ".join(platforms)
    #    mark_broken_v2.attemptToMarkBroken(pkgname, platforms, extraText=f"never built on {platforms_text} since first introduction in nixpkgs")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog = 'nixpkgs-broken',
        description = 'Tool to identify and mark packages in nixpkgs as broken',
    )
    parser.add_argument('--baseurl', default='https://hydra.nixos.org', required=False)
    parser.add_argument('--jobset', default='nixpkgs/trunk', required=False, help="The jobset to use (e.g. nixpkgs/trunk, nixpkgs/nixpkgs-unstable-aarch64-darwin)")
    parser.add_argument('--use-cached', action='store_true')
    parser.add_argument('--list-broken-pkgs', action='store_true')
    parser.add_argument('--db-path', default='hydra.db', required=False)

    args = parser.parse_args()
    baseurl = args.baseurl
    jobset = args.jobset
    use_cached = args.use_cached
    list_broken = args.list_broken_pkgs
    db_path = args.db_path

    print("Initializing database")
    database = Database(db_path)

    if list_broken:
        list_broken_pkgs(database)
        sys.exit(0)

    print(f"listing packages with build status from {baseurl}, jobset {jobset}")

    evalfetcher = EvalFetcher()
    if use_cached:
        all_evals = evalfetcher.get_cache()
    else:
        all_evals = evalfetcher.fetch(baseurl, jobset)

    # typically the last eval?
    last_eval_id = all_evals[0]["id"]
    print(f"using eval {last_eval_id}")

    buildsinevalfetcher = BuildsInEvalFetcher()
    if use_cached:
        all_builds_in_eval = buildsinevalfetcher.get_cache()
    else:
        all_builds_in_eval = buildsinevalfetcher.fetch(baseurl, last_eval_id)

    print(f"total build ids: {len(all_builds_in_eval)}")
    already_known_builds = database.get_known_builds(last_eval_id)
    to_remove = []
    # Skip all builds that were in the same eval and which we already stored data for.
    for [build_id, status] in already_known_builds:
        to_remove.append(build_id)
    # Skip all builds we already have data for from a different eval.
    for build_id in all_builds_in_eval:
        found_item = database.get_build_id(build_id)
        if found_item != None:
            build_id, status = found_item
            # We want to update the status for this build, so don't put it in the remove list.
            if status == None:
                continue
            to_remove.append(build_id)
    build_ids_to_check = list(set(all_builds_in_eval) - set(to_remove))
    print(f"to check: {len(build_ids_to_check)}")

    start_retrieve_build_results = datetime.datetime.now()

    num_processes = 100
    work_queue = JoinableQueue()
    result_queue = Queue()
    for i in range(num_processes):
        BuildFetcher(baseurl, work_queue, result_queue).start()
    for id in build_ids_to_check:
        work_queue.put(id)
    for i in range(num_processes):
        work_queue.put(None)

    number = 0
    none_counter = 0
    for result in iter(result_queue.get, "The_End"):
        if result == None:
            none_counter += 1
            # print(f"A worker exited, {num_processes - none_counter} left")
            if none_counter == num_processes:
                result_queue.put("The_End")
            continue
        build_id, baseurl, eval_id, timestamp, status, jobname, system = result
        database.insert_or_update_build_result(
          build_id,
          baseurl,
          jobset,
          eval_id,
          timestamp,
          status,
          jobname,
          system)
        number += 1
        print(f"{number}/{len(build_ids_to_check)}: status {status}, id {build_id}, job {jobname}, system {system}")
    work_queue.join()

    print("retrieving build results took", datetime.datetime.now() - start_retrieve_build_results)

