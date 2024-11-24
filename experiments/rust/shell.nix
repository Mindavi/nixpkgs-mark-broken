{ pkgs ? import <nixpkgs> {} }:

pkgs.mkShell {
  name = "nixpkgs-broken Rust shell";

  nativeBuildInputs = with pkgs; [
    cargo
    openssl
    pkg-config
    rustc
  ];

  shellHook = ''
    export PATH="$PATH:$PWD/target/debug"
  '';
}
