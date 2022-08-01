#!/usr/bin/env nix-shell
#!nix-shell --pure -i python3 -p nix gnused "python3.withPackages( ps: [ ps.click ] )"

import filecmp
import json
import os
import shutil
import subprocess
import sys

from collections.abc import Iterable

import click

denyFileList = [
    "node-packages.nix", # node, it will mark all node packages as broken
    "generic-builder.nix", # haskell, it will mark all haskell packages as broken
]

denyAttrList = [
    "python27Packages",
    "python39Packages",
    "python310Packages",
    "linuxPackages_",
    "rubyPackages_",
]

supportedPlatforms = [
    "aarch64-linux",
    "x86_64-linux",
    "aarch64-darwin",
    "x86_64-darwin",
]

def failMark(attr, message):
    print(f"{attr}: {message}", file=sys.stderr)
    #with open("failed-marks.txt", "a+") as err_file:
    #    print(attr, file=err_file)

def attemptToMarkBroken(attr: str, platforms: Iterable[str]):
    if len(platforms) == 0:
        return
    for platform in platforms:
        if platform not in supportedPlatforms:
            print(f"{platform} is not supported", file=sys.stderr)
            return

    for badAttr in denyAttrList:
        if badAttr in attr:
            failMark(attr, f"attr contained {badAttr}, skipped.")
            return

    nixInstantiate = subprocess.run([ "nix-instantiate", "--eval", "--json", "-E", f"with import ./. {{}}; (builtins.unsafeGetAttrPos \"description\" {attr}.meta).file" ], capture_output=True)
    if nixInstantiate.returncode != 0:
        failMark(attr, "Couldn't locate correct file")
        return
    nixFile = json.loads(nixInstantiate.stdout.decode('utf-8'))

    for filename in denyFileList:
        # should use basename instead of doing this
        if filename in os.path.basename(nixFile):
            failMark(attr, f"filename matched {filename}, skipped.")
            return

    platforms.sort()
    supportedPlatforms.sort()

    brokenText = ""
    for platform in platforms:
        if len(brokenText) > 0:
            brokenText += " || "
        if platform == "aarch64-linux":
            brokenText += "\(stdenv.isLinux \&\& stdenv.isAarch64\)"
        elif platform == "x86_64-linux":
            brokenText += "\(stdenv.isLinux \&\& stdenv.isx86_64\)"
        elif platform == "aarch64-darwin":
            brokenText += "\(stdenv.isDarwin \&\& stdenv.isAarch64\)"
        elif platform == "x86_64-darwin":
            brokenText += "\(stdenv.isDarwin \&\& stdenv.isx86_64\)"

    if platforms == supportedPlatforms:
        brokenText = "true"

    # insert broken attribute
    subprocess.run([ "sed", "-i.bak", nixFile, "-r",
        # Delete any old broken mark
        "-e", "/^\s*broken\s*=.*$/d",
        # Insert new broken mark in meta 
        "-e", "s/(\\s*)meta\\s*=.*\\{/&\\n\\1  broken = " + brokenText + ";/" ]
    )

    if filecmp.cmp(nixFile, f"{nixFile}.bak", shallow=False):
        shutil.move(f"{nixFile}.bak", nixFile)
        failMark(attr, "Does it have a meta attribute?")
        return

    # broken should evaluate to true now (for the given platform(s))
    for platform in platforms:
        nixMarkedCheck = subprocess.run([ "nix-instantiate", "--eval", "--json", "-E", f"with import ./. {{ localSystem = \"{platform}\"; }}; {attr}.meta.broken" ], capture_output=True)
        if nixMarkedCheck.returncode != 0:
            shutil.move(f"{nixFile}.bak", nixFile)
            failMark(attr, f"Failed to check {attr}.meta.broken for platform {platform}")
            return
        markedSuccessfully = json.loads(nixMarkedCheck.stdout.decode('utf-8'))
        if not markedSuccessfully:
            shutil.move(f"{nixFile}.bak", nixFile)
            failMark(attr, f"{attr}.meta.broken doesn't evaluate to true for {platform}.")
            return

    os.remove(f"{nixFile}.bak")

if __name__ == "__main__":
    attemptToMarkBroken("jq", ["aarch64-linux", "x86_64-darwin"])

