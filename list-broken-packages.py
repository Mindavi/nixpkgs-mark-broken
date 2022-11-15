#! /usr/bin/env nix-shell
#! nix-shell -i python3 --pure -p "pkgs.python3.withPackages(ps: [ ps.requests ])"

import requests
import datetime
import sys
import multiprocessing
import sqlite3

class EvalFetcher:
    def fetch(self, baseurl, jobset):
        start = datetime.datetime.now()
        evals = requests.get(f"{baseurl}/jobset/{jobset}/evals", headers={"Accept": "application/json"})
        print("requesting evals took", datetime.datetime.now() - start)

        with open("evals.json", "w") as eval_file:
            print(evals.text, file=eval_file)

        # TODO(ricsch): Handle errors

        # convert to list?
        all_evals = evals.json()["evals"]

        print(f"number of evals: {len(all_evals)}")

        return all_evals

if __name__ == "__main__":
    baseurl = "https://hydra.nixos.org"
    #baseurl = "http://localhost:3000"

    # Selecting a different jobset may be handy for debugging the script.
    jobset = "nixpkgs/trunk"
    #jobset = "nixos/release-22.05"
    #jobset = "nixpkgs/cross-trunk"
    #jobset = "patchelf/master"

    #jobset = "nixpkgs/nixpkgs-master"

    print(f"listing packages with build status from {baseurl}")

    fetcher = EvalFetcher()
    all_evals = fetcher.fetch(baseurl, jobset)

    # typically the last eval?
    last_eval_id = all_evals[0]["id"]
    print(f"using eval {last_eval_id}")
    sys.stdout.flush()

    builds = requests.get(f"{baseurl}/eval/{last_eval_id}", headers={"Accept": "application/json"})

    # TODO(ricsch): Handle errors

    #print(builds.json())
    all_builds_in_eval = builds.json()["builds"]
    print(f"number of builds: {len(all_builds_in_eval)}")

    with open("builds.json", "w") as build_file:
        print(builds.text, file=build_file)

    sql_con = sqlite3.connect("hydra.db")
    cursor = sql_con.cursor()

    cursor.execute("""CREATE TABLE IF NOT EXISTS build_results(
      id              INT PRIMARY KEY NOT NULL,
      url             TEXT            NOT NULL,
      eval_id         INT             NOT NULL,
      eval_timestamp  INT             NOT NULL,
      status          INT,
      job             TEXT            NOT NULL,
      system          TEXT            NOT NULL
    );
    """)

    # TODO(ricsch): Parallelize?
    def print_build_result(build_id):
        build_result = requests.get(f"{baseurl}/build/{build_id}", headers={"Accept": "application/json"})
        try:
            job = build_result.json()["job"]
            status = build_result.json()["buildstatus"]
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
        jobname, system = job.rsplit(".", maxsplit=1)
        result = (build_id, baseurl, last_eval_id, 1234, status, jobname, system)
        cursor.execute("INSERT INTO build_results VALUES(?, ?, ?, ?, ?, ?, ?)", result)
        sql_con.commit()
        print(f"status {status}, id {build_id}, job {job}")

    pool = multiprocessing.Pool(250)
    start_retrieve_build_results = datetime.datetime.now()
    pool.map(print_build_result, all_builds_in_eval)
    print("retrieving build results took", datetime.datetime.now() - start_retrieve_build_results)

