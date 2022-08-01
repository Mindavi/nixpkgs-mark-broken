#!/usr/bin/env nix-shell
#! nix-shell -i python3 --pure -p "pkgs.python3"

from collections import defaultdict
import sys

if len(sys.argv) != 2:
    print("Usage: filter-broken-pkgs.py FILENAME", file=sys.stderr)
    sys.exit(1)

jobs = []

class Job:
    def __init__(self, Status, Id, Jobname):
        self.Status = Status
        self.Id = Id
        self.Name = Jobname.rsplit('.', 1)[0]
        self.Platform = Jobname.rsplit('.', 1)[1]
        assert(self.Name != "")
        assert(self.Platform != "")

    def __lt__(self, other):
        if self.Name == other.Name:
            return self.Platform < other.Platform
        return self.Name < other.Name

with open(sys.argv[1]) as input_file:
    # line example:
    # status 0, id 185414062, job rubyPackages_3_0.kramdown.aarch64-linux
    for line in input_file:
        # skip header lines
        if "status" not in line or "job" not in line:
            continue
        line = line.strip()
        parts = line.split(',')
        parts = [x.strip() for x in parts]
        status = parts[0].split(' ')[1]
        id = parts[1].split(' ')[1]
        job = parts[2].split(' ')[1]
        # No platform defined for this job... Seen in the wild for 'manual' job
        if "." not in job:
            print(f'Job {job} has no platform defined, skipping...', file=sys.stderr)
            continue
        jobs.append(Job(status, id, job))

#jobs2 = defaultdict(list)

#for job in jobs:
#    jobs2[job.Name] = job

# Filter (directly) failing jobs
jobs = list(filter(lambda job: job.Status == "1", jobs))
jobs.sort()
for job in jobs:
    #print(job.Platform, '\t', job.Status, job.Name)
    print(f'{job.Name}.{job.Platform}')

