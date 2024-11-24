{ stdenv
, lib
, python3Packages
}:

python3Packages.buildPythonPackage {
  pname = "nixpkgs-broken";
  version = "0.0.1";
  format = "pyproject";

  src = ./.;

  doCheck = true;

  propagatedBuildInputs = with python3Packages; [ pytest requests setuptools ];
}
