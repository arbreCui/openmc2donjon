# Release Gates

`openmc2donjon` has two different release signals. Keep them separate when
reviewing a commit or presenting validation evidence.

## GitHub CI

GitHub Actions is the software gate. It runs on a clean hosted runner and
checks that the repository installs, unit tests pass, the frontend builds, and
the core converter helpers remain lint/type-check clean.

CI intentionally does **not** prove a physics benchmark:

- it does not run OpenMC continuous-energy transport;
- it does not require a DRAGON/DONJON checkout;
- it does not require PyGan;
- it does not compare downstream k-effective values.

CI answers: "Did the package and web UI remain mechanically healthy?"

## Portable Release Smoke

`scripts/portable_release_smoke.sh` is the CI-friendly release smoke. It uses
only repository fixtures and deterministic tiny inputs:

- CLI entrypoint smoke;
- energy-mesh contract smoke;
- recipe export smoke;
- OpenMC CE/MG SPH sidecar mechanics using deterministic fixture fluxes;
- external SPH handoff smoke;
- external face-flux / ADF adapter smoke;
- C5G7 fixture conversion and LCM ASCII readback.

It answers: "Can a fresh checkout exercise the converter-facing handoff
mechanics without local reactor-code installations?"

Run it locally with:

```sh
bash scripts/portable_release_smoke.sh
```

Add `--with-tests` when you want this script to run unit tests too.

## Local Physics Release Gate

`scripts/release_check.sh` is the broader local release gate. It runs the
portable-style checks plus case-specific and optional local checks:

- accepted C5G7 fixture checks;
- OpenMC production/full-core/hex capability smokes when OpenMC is available;
- optional PyGan writer-comparison and native LCM inspection;
- optional DONJON/CLE-2000 downstream consumption and k-effective response
  checks when a local DRAGON/DONJON checkout is available.

It answers: "On this validation machine, do the converter outputs still work
with the local physics toolchain and accepted handoff artifacts?"

Run:

```sh
bash scripts/release_check.sh
bash scripts/release_check.sh --run-donjon
```

## Sign-Off Ladder

For ordinary code changes:

1. GitHub CI green.
2. `bash scripts/portable_release_smoke.sh` green when the change touches the
   converter, HDF5 contract, SPH/ADF sidecars, or web execution paths.

For physics-facing releases or claims:

1. GitHub CI green.
2. Portable release smoke green.
3. Local `scripts/release_check.sh` green on the validation machine.
4. Local `scripts/release_check.sh --run-donjon` green when the release claim
   includes downstream DONJON behavior.
