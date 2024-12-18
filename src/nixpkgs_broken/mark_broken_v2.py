import filecmp
import json
import os
import re
import shutil
import subprocess
import sys

from collections.abc import Iterable

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

platformsAndBrokenText = {
    "aarch64-linux": "stdenv.hostPlatform.isLinux && stdenv.hostPlatform.isAarch64",
    "x86_64-linux": "stdenv.hostPlatform.isLinux && stdenv.hostPlatform.isx86_64",
    "aarch64-darwin": "stdenv.hostPlatform.isDarwin && stdenv.hostPlatform.isAarch64",
    "x86_64-darwin": "stdenv.hostPlatform.isDarwin && stdenv.hostPlatform.isx86_64",
}

supportedPlatforms = list(platformsAndBrokenText.keys())

shortPlatforms = {
    "stdenv.hostPlatform.isLinux": [ "x86_64-linux", "aarch64-linux" ],
    "stdenv.hostPlatform.isDarwin": [ "x86_64-darwin", "aarch64-darwin" ],
}

def numLeadingSpaces(input_str):
    count = 0
    for c in input_str:
        if c != ' ':
            return count
        count += 1

    return count

def insertBrokenMark(attr, file, brokenText, comment):
    prev_line = None
    shutil.copyfile(file, f'{file}.bak', follow_symlinks=False)
    with open(file, "r") as input_file:
        input_data = input_file.read()

    move_broken_to_meta_bottom = True

    output_lines = []

    in_meta = False
    meta_end = False
    meta_end_marker = '};'
    lines = input_data.splitlines()
    broken_counter = 0
    for linenr in range(len(lines)):
        line = lines[linenr].rstrip()
        # TODO(Mindavi): Decide if we want to replace the current line or move it to the bottom.
        brokenline = re.search(r'broken\s+=', line)
        if brokenline:
            broken_counter += 1
            if broken_counter > 1:
                failMark(attr, f"the file {file} contains multiple broken lines, unclear which to mark")
                return
            # Assume this broken line terminates on the same line.
            if not ';' in line:
                failMark(attr, "broken line unterminated on this line, cannot handle multiline broken marks")
                return
            # TODO(Mindavi): It should be easier to filter than doing it like this...
            if 'Static' in line or 'targetPlatform' in line or 'is32bit' in line or 'kernel' in line or 'with' in line or 'version' in line or 'meta' in line or 'python' in line or 'Support' in line:
                failMark(attr, "broken line contains special information, cannot handle anything other than a platform")
                return
            # It's not really nice to move the broken line if an explanation of the brokenness is provided above it.
            # Detect if the next line is the meta closing line '};'. In that case this is ok.
            next_line = lines[min(linenr+1, len(lines))]
            prev_line_is_comment = '#' in prev_line
            next_line_is_meta_end = meta_end_marker in next_line
            if not next_line_is_meta_end and prev_line_is_comment:
                failMark(attr, "broken line is preceded by comment, should be moved manually together with comment")
                return
            continue
        if meta_end:
            meta_end = False
        if 'meta =' in line:
            in_meta = True
        elif in_meta and meta_end_marker in line:
            meta_end = True
            in_meta = False
        elif in_meta:
            meta_indent = numLeadingSpaces(line)
        if not meta_end and prev_line != None:
            output_lines.append(prev_line)
        elif meta_end:
            output_lines.append(prev_line)
            if comment:
                output_lines.append(f"{' ' * meta_indent}# {comment}")
            output_lines.append(f"{' ' * meta_indent}broken = {brokenText};")
        prev_line = line
    output_lines.append(prev_line)

    with open(file, 'w') as output_file:
        for line in output_lines:
            print(line, file=output_file)

def failMark(attr, message):
    print(f"{attr}: {message}", file=sys.stderr)
    #with open("failed-marks.txt", "a+") as err_file:
    #    print(attr, file=err_file)

def attemptToMarkBroken(attr: str, platforms: Iterable[str], extraText = ""):
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

    alreadyMarkedPlatforms = []
    for platform in supportedPlatforms:
        # We'll already mark it broken for this platform.
        #if platform in platforms:
        #    continue
        alreadyMarked = subprocess.run([ "nix-instantiate", "--eval", "--json",
                                         "-E", f"with import ./. {{ localSystem = \"{platform}\"; }}; {attr}.meta.broken" ], capture_output=True)
        # assertion (stdenv).hostPlatform.isLinux failed can sometimes occur when checking for Darwin.
        # TODO(Mindavi): handle that situation better.
        if alreadyMarked.returncode != 0:
            failMark(attr, "Couldn't check meta.broken: {alreadyMarked.stderr.decode('utf-8').split()[0]}")
            return

        isMarkedBrokenForPlatform = json.loads(alreadyMarked.stdout.decode('utf-8'))
        if isMarkedBrokenForPlatform:
            #print(f"Package {attr} is already marked broken for {platform}")
            alreadyMarkedPlatforms.append(platform)

    alreadyMarkedPlatforms.sort()
    extraPlatforms = list(set(platforms) - set(alreadyMarkedPlatforms))
    if alreadyMarkedPlatforms == platforms or len(extraPlatforms) == 0:
        print(f"Package {attr} is already marked broken for all platforms listed {alreadyMarkedPlatforms}, not doing anything")
        return

    platforms = list(set(platforms + alreadyMarkedPlatforms))
    platforms.sort()

    assert(len(platforms) <= len(supportedPlatforms))

    brokenText = ""
    for [short, combinablePlatforms] in shortPlatforms.items():
        platformsWithoutCombinablePlatforms = set(platforms) - set(combinablePlatforms)
        if (len(platforms) - 2 == len(platformsWithoutCombinablePlatforms)):
            if len(brokenText) > 0:
                brokenText += " || "
            brokenText += short
            # Remove the platforms from the list of platforms to be considered.
            platforms = list(filter(lambda item: item not in combinablePlatforms, platforms))
    multiplePlatforms = len(platforms) > 1 or len(brokenText) > 0
    for platform in platforms:
        if len(brokenText) > 0:
            brokenText += " || "
        if multiplePlatforms:
            brokenText += "("
        brokenText += platformsAndBrokenText[platform]
        if multiplePlatforms:
            brokenText += ")"

    if platforms == supportedPlatforms:
        brokenText = "true"

    assert(brokenText != "")
    assert(not "#" in extraText and not "/" in extraText)

    # insert broken attribute
    insertBrokenMark(attr, nixFile, brokenText, extraText)

    if filecmp.cmp(nixFile, f"{nixFile}.bak", shallow=False):
        shutil.move(f"{nixFile}.bak", nixFile)
        failMark(attr, "Does it have a meta attribute?")
        return

    # broken should evaluate to true now (for the given platform(s))
    for platform in platforms:
        nixMarkedCheck = subprocess.run([ "nix-instantiate", "--eval", "--json", "-E", f"with import ./. {{ localSystem = \"{platform}\"; }}; {attr}.meta.broken" ], capture_output=True)
        if nixMarkedCheck.returncode != 0:
            shutil.move(f"{nixFile}.bak", nixFile)
            failMark(attr, f"Failed to check {attr}.meta.broken for platform {platform}: {nixMarkedCheck.stderr.decode('utf-8').split()[0]}")
            return
        markedSuccessfully = json.loads(nixMarkedCheck.stdout.decode('utf-8'))
        if not markedSuccessfully:
            shutil.move(f"{nixFile}.bak", nixFile)
            failMark(attr, f"{attr}.meta.broken doesn't evaluate to true for {platform}.")
            return

    os.remove(f"{nixFile}.bak")

if __name__ == "__main__":
    if len(sys.argv) <= 2:
        print("Invalid arguments, expected PKGNAME PLATFORMS")
        sys.exit(1)
    pkgname = sys.argv[1]
    platforms = sys.argv[2:]
    print(f"mark package {pkgname} as broken for {platforms}")
    for platform in platforms:
        if platform not in supportedPlatforms:
            print(f"platform {platform} is not supported, supported platforms {supportedPlatforms}")
            sys.exit(1)
    attemptToMarkBroken(pkgname, platforms)

