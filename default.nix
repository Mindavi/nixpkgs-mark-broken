{ pkgs ? import <nixpkgs> {} }:

{
  nixpkgs-broken = pkgs.callPackage ./nixpkgs-broken.nix {};
}

