#! /usr/bin/env nix-shell
#! nix-shell -i bash --pure -p ripgrep gawk

tail +6 pkgs-with-status.txt | rg "status 1," | cut -d' ' -f6- | sort | awk '{ print "- [ ] " $0 }'

