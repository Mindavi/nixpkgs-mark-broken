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
    conn = aiohttp.TCPConnector(limit=10)
    timeout = aiohttp.ClientTimeout(total=60)
    async with aiohttp.ClientSession(connector=conn, timeout=timeout) as session:
        tasks = []
        for number in range(142461210, 142461210 + 300):
            hydra_url = f'https://hydra.nixos.org/build/{number}'
            tasks.append(asyncio.ensure_future(get_job(session, hydra_url)))

        job_info = await asyncio.gather(*tasks)
        for job in job_info:
            name = job['job']
            id = job['id']
            status = job['buildstatus']
            print(f'job name: {name}, id {id}, status {status}')

asyncio.run(main())
elapsed_time = time.time() - start_time
print(f"--- {elapsed_time:.3f} seconds ---")

