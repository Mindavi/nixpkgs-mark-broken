{ pkgs ? import <nixpkgs>{} }:

pkgs.mkShell {
  name = "zhf-mark-broken";
  buildInputs = [
    (pkgs.python3.withPackages(ps: [ ps.requests ] ))
  ];
}
