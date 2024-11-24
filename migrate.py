#! /usr/bin/env nix-shell
#! nix-shell -i python3 --pure -p "pkgs.python3.withPackages(ps: with ps; [ ])" nix

import sqlite3
import argparse

# CREATE TABLE build_results(
    #   id              INT PRIMARY KEY NOT NULL,
    #   url             TEXT            NOT NULL,
    #   eval_id         INT             NOT NULL,
    #   eval_timestamp  INT             NOT NULL,
    #   status          INT,
    #   job             TEXT            NOT NULL,
    #   system          TEXT            NOT NULL
    # , jobset TEXT);


def migrate():
    parser = argparse.ArgumentParser()
    parser.add_argument("--old", default="hydra.db")
    parser.add_argument("--new", default="hydra2.db")
    args = parser.parse_args()

    old_db = sqlite3.connect(args.old)
    old_db_cursor = old_db.cursor()

    new_db = sqlite3.connect(args.new)
    new_db_cursor = new_db.cursor()

    new_db_cursor.execute("""PRAGMA foreign_keys = ON;""")
    new_db.commit()

    new_db_cursor.execute("""CREATE TABLE IF NOT EXISTS jobsets(
    jobset_id       INTEGER PRIMARY KEY NOT NULL,
    url             TEXT                NOT NULL,
    jobset          TEXT                NOT NULL
    );
    """)
    new_db_cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS jobsets_unique on jobsets (url, jobset);
    """)
    new_db.commit()

    new_db_cursor.execute("""CREATE TABLE IF NOT EXISTS build_results(
    build_id        INTEGER PRIMARY KEY NOT NULL,
    jobset_id       INTEGER,
    eval_id         INTEGER             NOT NULL,
    eval_timestamp  INTEGER             NOT NULL,
    status          INTEGER,
    job             TEXT            NOT NULL,
    system          TEXT            NOT NULL,
    FOREIGN KEY(jobset_id) REFERENCES jobsets(jobset_id)
    );
    """)
    new_db.commit()

    new_db_cursor.execute("""CREATE TABLE IF NOT EXISTS attr_files(
    attr_files_id   INTEGER PRIMARY KEY NOT NULL,
    attribute       TEXT                NOT NULL,
    file            TEXT                NOT NULL
    );
    """)
    new_db.commit()

    build_results = old_db_cursor.execute("SELECT * from build_results")
    results = build_results.fetchall()
    print(f"migrating {len(results)} builds")
    def get_jobset_id(url, jobset):
        new_db_cursor.execute("""SELECT jobset_id FROM jobsets WHERE url = ? and jobset = ?""", (url, jobset))
        return new_db_cursor.fetchone()[0]
    counter = 0
    for result in results:
        # (199374120, 'https://hydra.nixos.org', 1785874, 1669047021, 0, 'nsxiv', 'x86_64-linux', 'nixpkgs/trunk')
        build_id, url, eval_id, eval_timestamp, status, job, system, jobset = result
        inserted_values = new_db_cursor.execute("""INSERT OR IGNORE INTO jobsets (jobset_id, url, jobset) VALUES(NULL, ?, ?)""", (url, jobset))
        jobset_id = get_jobset_id(url, jobset)
        assert isinstance(jobset_id, int), f"jobset_id should be int, is {type(jobset_id)}, {jobset_id}"
        new_db_cursor.execute("""INSERT INTO build_results
            (build_id, jobset_id, eval_id, eval_timestamp, status, job, system)
            VALUES(?, ?, ?, ?, ?, ?, ?)""",
            (build_id, jobset_id, eval_id, eval_timestamp, status, job, system))
        # new_db.commit()
        counter += 1
        if counter % 1000 == 0:
            print(f"{counter}/{len(results)}: migrate {build_id}: {job}: {system}")
            new_db.commit()
    new_db.commit()

    new_db.commit()
if __name__ == "__main__":
    migrate()
