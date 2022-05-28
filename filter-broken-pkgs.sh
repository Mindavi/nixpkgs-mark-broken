#! /usr/bin/env nix-shell
#! nix-shell -i bash --pure -p ripgrep gawk

if [[ $# -ne 1 ]]; then
  echo "Invalid number of arguments"
  echo "Usage: filter-broken-pkgs.sh <packages-with-status>"
  exit 1
fi

file=$1
tail +6 "$1" | rg "status 1," | cut -d' ' -f6- | sort

