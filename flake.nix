{
  description = "nixpkgs-broken";

  outputs = { self, nixpkgs }: {
    packages.x86_64-linux = import ./default.nix { pkgs = import nixpkgs { system = "x86_64-linux"; }; };
  };
}

