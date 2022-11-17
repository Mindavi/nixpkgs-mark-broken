#! /usr/bin/env nix-shell
#! nix-shell -i python3 --pure -p "pkgs.python3.withPackages(ps: [ ps.requests ])"

import argparse
import datetime
import json
from multiprocessing import JoinableQueue, Process, Queue
import requests
import sqlite3
import sys

class EvalFetcher:
    def fetch(self, baseurl, jobset):
        start = datetime.datetime.now()
        evals = requests.get(f"{baseurl}/jobset/{jobset}/evals", headers={"Accept": "application/json"})
        print("requesting evals took", datetime.datetime.now() - start)

        with open("evals.json", "w") as eval_file:
            print(evals.text, file=eval_file)

        # TODO(ricsch): Handle errors

        all_evals = evals.json()["evals"]

        print(f"number of evals: {len(all_evals)}")

        return all_evals

    def get_cache(self):
        with open("evals.json", "r") as eval_file:
            return json.load(eval_file)["evals"]

class BuildsInEvalFetcher:
    def fetch(self, baseurl, eval_id):
        builds = requests.get(f"{baseurl}/eval/{last_eval_id}", headers={"Accept": "application/json"})

        # TODO(ricsch): Handle errors

        all_builds_in_eval = builds.json()["builds"]
        print(f"number of builds: {len(all_builds_in_eval)}")

        with open("builds.json", "w") as build_file:
            print(builds.text, file=build_file)

        return all_builds_in_eval

    def get_cache(self):
        with open("builds.json", "r") as build_file:
            return json.load(build_file)["builds"]

class Database:
    def __init__(self, name):
        self.connection = sqlite3.connect("hydra.db")
        self.cursor = self.connection.cursor()

        self.cursor.execute("""CREATE TABLE IF NOT EXISTS build_results(
        id              INT PRIMARY KEY NOT NULL,
        url             TEXT            NOT NULL,
        eval_id         INT             NOT NULL,
        eval_timestamp  INT             NOT NULL,
        status          INT,
        job             TEXT            NOT NULL,
        system          TEXT            NOT NULL
        );
        """)

    def insert_build_result(
        self,
        build_id,
        baseurl,
        eval_id,
        timestamp,
        status,
        jobname,
        system
    ):
        result = (build_id, baseurl, last_eval_id, timestamp, status, jobname, system)
        self.cursor.execute("INSERT INTO build_results VALUES(?, ?, ?, ?, ?, ?, ?)",
            result)
        self.connection.commit()

    def get_known_builds(self, eval_id):
        known_builds = self.cursor.execute("SELECT id, status FROM build_results WHERE eval_id = ?", (eval_id,))
        found_builds = []
        for [build_id, status] in known_builds:
            found_builds.append((build_id, status))
        return found_builds

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
                assert(system in ["aarch64-linux", "x86_64-linux", "x86_64-darwin", "aarch64-darwin"])
                self.result_queue.put((build_id, baseurl, last_eval_id, timestamp, status, jobname, system))
            else:
                print(f"Job without system (job: {job}, id: {build_id}, status: {status}), skipping")
            self.work_queue.task_done()
        self.result_queue.put(None)
        # Call task_done() for the 'None' item too.
        self.work_queue.task_done()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog = 'nixpkgs-broken',
        description = 'Tool to identify and mark packages in nixpkgs as broken',
    )
    parser.add_argument('--baseurl', default='https://hydra.nixos.org', required=False)
    parser.add_argument('--jobset', default='nixpkgs/trunk', required=False)
    parser.add_argument('--use-cached', action='store_true')

    args = parser.parse_args()
    baseurl = args.baseurl
    jobset = args.jobset
    use_cached = args.use_cached

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

    database = Database('hydra.db')

    # TODO(ricsch): Parallelize?
    def record_build_result(build_id):
        build_result = requests.get(f"{baseurl}/build/{build_id}", headers={"Accept": "application/json"})
        try:
            job = build_result.json()["job"]
            status = build_result.json()["buildstatus"]
            timestamp = build_result.json()["timestamp"]
        except:
            print(f"build {build_id} unknown status, {build_result}", file=sys.stderr)
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
            assert(system in ["aarch64-linux", "x86_64-linux", "x86_64-darwin", "aarch64-darwin"])
        else:
            print(f"Job without system (job: {job}, id: {build_id}, status: {status}), skipping")
            return
        result = (build_id, baseurl, last_eval_id, timestamp, status, jobname, system)
        try:
            database.insert_build_result(
                build_id,
                baseurl,
                last_eval_id,
                timestamp,
                status,
                jobname,
                system)
        except Exception as e:
            print("Sqlite error:", e)
        print(f"status {status}, id {build_id}, job {job}")

    print(f"total build ids: {len(all_builds_in_eval)}")
    already_known_builds = database.get_known_builds(last_eval_id)
    to_remove = []
    for [build_id, status] in already_known_builds:
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

    for result in iter(result_queue.get, None):
        build_id, baseurl, eval_id, timestamp, status, jobname, system = result
        try:
            database.insert_build_result(
                build_id,
                baseurl,
                last_eval_id,
                timestamp,
                status,
                jobname,
                system)
        except Exception as e:
            print("Sqlite error:", e)
        print(f"status {status}, id {build_id}, job {job}")
    work_queue.join()

    print("retrieving build results took", datetime.datetime.now() - start_retrieve_build_results)
