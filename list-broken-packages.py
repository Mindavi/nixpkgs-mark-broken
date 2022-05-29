#! /usr/bin/env nix-shell
#! nix-shell -i python3 --pure -p "pkgs.python3.withPackages(ps: [ ps.requests ])"

import requests
import datetime
import sys
import multiprocessing

# Selecting a different jobset may be handy for debugging the script.
jobset = "nixpkgs/trunk"
#jobset = "nixpkgs/cross-trunk"
#jobset = "patchelf/master"

print("listing packages with build status")

start = datetime.datetime.now()
evals = requests.get(f"https://hydra.nixos.org/jobset/{jobset}/evals", headers={"Accept": "application/json"})
print("requesting evals took", datetime.datetime.now() - start)

# TODO(ricsch): Handle errors

# convert to list?
all_evals = evals.json()["evals"]
#all_evals.sort()
#print("all_evals[0]", all_evals[0])
#print("all_evals[10]", all_evals[10])

print(f"number of evals: {len(all_evals)}")

# typically the last eval?
last_eval_id = all_evals[0]["id"]
print(f"using eval {last_eval_id}")

builds = requests.get(f"https://hydra.nixos.org/eval/{last_eval_id}", headers={"Accept": "application/json"})

# TODO(ricsch): Handle errors

#print(builds.json())
all_builds_in_eval = builds.json()["builds"]
print(f"number of builds: {len(all_builds_in_eval)}")

# TODO(ricsch): Parallelize?
def print_build_result(build_id):
    build_result = requests.get(f"https://hydra.nixos.org/build/{build_id}", headers={"Accept": "application/json"})
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
    #   2: indirect failure
    #   4: timed out (?)
    #   7: timed out
    #   11: output limit exceeded
    print(f"status {status}, id {build_id}, job {job}")
    if status != 0:
        sys.stdout.flush()

pool = multiprocessing.Pool(250)
start_retrieve_build_results = datetime.datetime.now()
pool.map(print_build_result, all_builds_in_eval)
print("retrieving build results took", datetime.datetime.now() - start_retrieve_build_results)

