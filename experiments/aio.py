#! /usr/bin/env nix-shell
#! nix-shell -i python3 -p "pkgs.python3.withPackages(ps: [ ps.aiohttp ])"

import aiohttp
import asyncio
import ssl
import time

start_time = time.time()

async def get_job(session, url):
    async with session.get(url, headers={"Accept": "application/json"}) as resp:
        build_info = await resp.json()
        return build_info

async def main():
    print("App start")
    conn = aiohttp.TCPConnector(limit=20)
    timeout = aiohttp.ClientTimeout(total=60)
    async with aiohttp.ClientSession(connector=conn, timeout=timeout) as session:
        tasks = set()
        for number in range(142461210, 142461210 + 300):
            hydra_url = f'https://hydra.nixos.org/build/{number}'
            task = asyncio.ensure_future(get_job(session, hydra_url))
            tasks.add(task)
            task.add_done_callback(tasks.discard)

        previous = 0
        while(len(tasks) > 0):
            if len(tasks) != previous:
                previous = len(tasks)
                print(f"still {len(tasks)} to be done")
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                job = task.result()
                name = job['job']
                id = job['id']
                status = job['buildstatus']
                print(f'job name: {name}, id {id}, status {status}')

        # job_info = await asyncio.gather(*tasks)
        # for job in job_info:
        #     name = job['job']
        #     id = job['id']
        #     status = job['buildstatus']
        #     print(f'job name: {name}, id {id}, status {status}')

asyncio.run(main())
elapsed_time = time.time() - start_time
print(f"--- {elapsed_time:.3f} seconds ---")

