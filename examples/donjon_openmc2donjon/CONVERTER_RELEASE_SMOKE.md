# Converter Release Smoke

This record captures the current minimal code-side smoke for the
`/Users/wen/openmc-workspace/openmc2donjon` package without writing release
artifacts into the package tree.

## Scope

- Package source: `/Users/wen/openmc-workspace/openmc2donjon`
- Test input: `/Users/wen/openmc-workspace/c5g7_converter_test/mgxs_library.h5`
- Temporary outputs:
  - `/private/tmp/openmc2donjon_cli_smoke.mco`
  - `/private/tmp/openmc2donjon_cli_smoke.macrolib.txt`

## Commands

CLI help:

```sh
PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH=/Users/wen/openmc-workspace/openmc2donjon/src \
  /opt/homebrew/bin/python3.14 -m openmc2donjon.cli --help
```

CLI version:

```sh
PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH=/Users/wen/openmc-workspace/openmc2donjon/src \
  /opt/homebrew/bin/python3.14 -m openmc2donjon.cli --version
```

Unit tests, with pytest cache redirected away from the package tree:

```sh
PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH=/Users/wen/openmc-workspace/openmc2donjon/src \
  /Users/wen/miniforge3/envs/openmc-dev/bin/python -m pytest -q \
  -o cache_dir=/private/tmp/openmc2donjon_pytest_cache \
  /Users/wen/openmc-workspace/openmc2donjon/tests
```

MULTICOMPO CLI smoke:

```sh
PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH=/Users/wen/openmc-workspace/openmc2donjon/src \
  /opt/homebrew/bin/python3.14 -m openmc2donjon.cli \
  /Users/wen/openmc-workspace/c5g7_converter_test/mgxs_library.h5 \
  -o /private/tmp/openmc2donjon_cli_smoke.mco
```

Root `L_MACROLIB` CLI smoke:

```sh
PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH=/Users/wen/openmc-workspace/openmc2donjon/src \
  /opt/homebrew/bin/python3.14 -m openmc2donjon.cli \
  --format macrolib \
  /Users/wen/openmc-workspace/c5g7_converter_test/mgxs_library.h5 \
  -o /private/tmp/openmc2donjon_cli_smoke.macrolib.txt
```

Read-back smoke:

```sh
PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH=/Users/wen/openmc-workspace/openmc2donjon/src \
  /opt/homebrew/bin/python3.14 -c 'from pathlib import Path; from openmc2donjon import lcm_ascii as lcm; files=[Path("/private/tmp/openmc2donjon_cli_smoke.mco"), Path("/private/tmp/openmc2donjon_cli_smoke.macrolib.txt")]; [print(p.name, "blocks", len(lcm.read_lcm_ascii(p))) for p in files]'
```

## Current Result

- CLI help prints the expected options, including `--format {multicompo,macrolib}`.
- CLI version prints `openmc2donjon 0.1.0`.
- Unit tests: `21 passed`.
- MULTICOMPO CLI smoke:
  - size: about `58K`
  - read-back blocks: `303`
  - first block names: `SIGNATURE`, `CPO`, `COMMENT`, `GLOBAL`, `PARCAD`,
    `PARPAD`, `STATE-VECTOR`, `MIXTURES`
- Root `L_MACROLIB` CLI smoke:
  - size: about `26K`
  - read-back blocks: `106`
  - first block names: `SIGNATURE`, `STATE-VECTOR`, `ENERGY`, `VOLUME`,
    `GROUP`, `FLUX-INTG`, `NTOT0`, `OVERV`
- No `__pycache__` or `.pytest_cache` was left in the package tree.

Status: PASS.
