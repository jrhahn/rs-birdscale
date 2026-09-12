# The service as a Nix package.
#
# Kept out of the flake file so the NixOS module can `callPackage` it directly:
# a home server that imports the module should not also have to wire up the
# flake's `packages` output to get the binary.
{ lib, rustPlatform, stdenv }:

rustPlatform.buildRustPackage {
  pname = "smarthome-timeseries";
  version = "0.1.0";

  # Only this directory, and not its build output: `target` is gigabytes of
  # incremental artefacts that would be copied into the store on every change
  # and invalidate the hash each time.
  src = lib.cleanSourceWith {
    src = ./..;
    filter = path: type:
      let base = baseNameOf (toString path);
      in !(type == "directory" && base == "target");
  };
  cargoLock.lockFile = ../Cargo.lock;

  # `.cargo/config.toml` in this directory hard-codes x86_64, because it has to
  # override the firmware's riscv32 default and cargo has no way to say "just
  # the host". The environment variable wins over the file, so this is what
  # makes the package build on a Raspberry Pi home server as well.
  CARGO_BUILD_TARGET = stdenv.hostPlatform.rust.rustcTargetSpec;

  meta = {
    description = "MQTT to QuestDB archiver and dashboard for the smart-home sensor fleet";
    mainProgram = "smarthome-timeseries";
    license = lib.licenses.mit;
    platforms = lib.platforms.linux;
  };
}
