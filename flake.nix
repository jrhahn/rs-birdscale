{
  description = "Async no_std ESP32-C3 smart-home sensor node firmware (Embassy); started as a bird-feeder scale";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    # espflash 4.x refuses to flash an image without an ESP-IDF app descriptor,
    # which esp-hal 0.22 does not emit (`esp_app_desc!` arrived in 0.23).
    # Forcing it through with `--ignore-app-descriptor` writes garbage into the
    # image header's min-efuse-revision fields, and the second-stage bootloader
    # then rejects the app on every boot:
    #   Image requires efuse blk rev >= v145.58, but chip is v1.3
    #   No bootable app partitions in the partition table
    # So pin the flasher to the 3.x line until esp-hal is bumped.
    nixpkgs-espflash.url = "github:NixOS/nixpkgs/nixos-24.11";
    fenix = {
      url = "github:nix-community/fenix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, nixpkgs-espflash, fenix, flake-utils }:
    # `nixosModules` is not per-system, so it sits outside `eachDefaultSystem`
    # -- the home server imports it and picks its own `pkgs`.
    {
      nixosModules.smarthome-timeseries = import ./timeseries/nix/module.nix;
      nixosModules.default = self.nixosModules.smarthome-timeseries;
    }
    // flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs { inherit system; };
        pkgsEspflash = import nixpkgs-espflash { inherit system; };

        # Reuse the existing rust-toolchain.toml as the single source of
        # truth: it pins Rust 1.83.0 (required for esp-wifi 0.11's c_char
        # bindings) plus the riscv32imc-unknown-none-elf target.
        rustToolchain = fenix.packages.${system}.fromToolchainFile {
          file = ./rust-toolchain.toml;
          sha256 = "sha256-s1RPtyvDGJaX/BisLT+ifVfuhDT1nZkZ1NcK8sbwELM=";
        };

        # CadQuery is not in nixpkgs -- only the `opencascade-occt` kernel is,
        # without the Python bindings. So the enclosure shell pins the wheels
        # instead and installs them into a venv on first entry. The wheels are
        # manylinux builds, which do not find a loader on NixOS by themselves;
        # `cadLibs` is what they link against.
        cadPython = pkgs.python311;
        cadLibs = pkgs.lib.makeLibraryPath (with pkgs; [
          stdenv.cc.cc.lib # libstdc++, the one OCP actually fails without
          expat
          zlib
          libGL
          glib
          fontconfig
          freetype
          libx11
          libxext
          libxrender
        ]);
        cadVenv = ".venv-cad";
      in
      {
        # The host-side archiver. Not built by the firmware shell: it shares no
        # dependency with the image and does not even use the same toolchain.
        packages.smarthome-timeseries = pkgs.callPackage ./timeseries/nix/package.nix { };
        packages.default = self.packages.${system}.smarthome-timeseries;

        devShells.default = pkgs.mkShell {
          packages = [
            rustToolchain
            pkgsEspflash.espflash # flash + serial monitor over USB-C (3.x, see above)
            pkgs.gitleaks # secret scanning (see .githooks/pre-commit)
          ];

          # Route git at the tracked hooks so the gitleaks secret scan runs on
          # every commit made from inside the dev shell. `core.hooksPath` is a
          # local setting, so this (re)applies it on shell entry.
          shellHook = ''
            if [ -d .git ]; then
              git config --local core.hooksPath .githooks
            fi
          '';
        };

        # The archiver's own shell. The firmware's 1.83.0 pin exists for
        # esp-wifi's C bindings and is older than what tokio, axum and rumqttc
        # ask for, so this one takes nixpkgs' rustc instead -- see
        # `timeseries/rust-toolchain.toml`.
        #
        #   nix develop .#timeseries
        #   cd timeseries && cargo test
        devShells.timeseries = pkgs.mkShell {
          packages = [
            pkgs.cargo
            pkgs.rustc
            pkgs.clippy
            pkgs.rustfmt
            pkgs.rust-analyzer
            pkgs.gitleaks
            # For the end-to-end smoke test in timeseries/README.md.
            pkgs.questdb
            pkgs.mosquitto
          ];

          shellHook = ''
            if [ -d .git ]; then
              git config --local core.hooksPath .githooks
            fi
          '';
        };

        # Enclosure CAD. Separate from the firmware shell because it drags in
        # a few hundred MB of OpenCASCADE that a `cargo build` has no use for.
        #
        #   nix develop .#cad          # or `use flake .#cad` in .envrc
        #   python models.py           # writes cad-models/*.stl and *.step
        devShells.cad = pkgs.mkShell {
          packages = [ cadPython pkgs.gitleaks ];

          # The wheels are manylinux, so they need to be told where the
          # system libraries live -- see `cadLibs` above.
          LD_LIBRARY_PATH = cadLibs;

          shellHook = ''
            if [ -d .git ]; then
              git config --local core.hooksPath .githooks
            fi
            if [ ! -x "${cadVenv}/bin/python" ]; then
              echo "creating ${cadVenv} (one-off, pulls ~500 MB of OpenCASCADE)..."
              ${cadPython}/bin/python -m venv "${cadVenv}"
              "${cadVenv}/bin/pip" install --quiet --upgrade pip
              # Pinned: CadQuery moves its API around between minor releases,
              # and models.py is written against this one.
              "${cadVenv}/bin/pip" install --quiet \
                'cadquery==2.8.0' 'cadquery-ocp==7.9.3.1.1' 'numpy>=2.0'
            fi
            export PATH="$PWD/${cadVenv}/bin:$PATH"
          '';
        };
      });
}
