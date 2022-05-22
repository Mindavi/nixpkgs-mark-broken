#!/usr/bin/env python3

import requests
import datetime
import sys

# Selecting a different jobset may be handy for debugging the script.
#jobset = "nixpkgs/trunk"
jobset = "nixpkgs/cross-trunk"
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
for build in all_builds_in_eval:
    build_result = requests.get(f"https://hydra.nixos.org/build/{build}", headers={"Accept": "application/json"})
    try:
        job = build_result.json()["job"]
        status = build_result.json()["buildstatus"]
    except:
        print(f"build {build} unknown status, {build_result}", file=sys.stderr)
        continue
    # status can be:
    #   None: not built yet
    #   0: success
    #   1: Build returned a non-zero exit code 
    #   2: indirect failure
    #   11: output limit exceeded
    print(f"status {status},\tjob {job}")

