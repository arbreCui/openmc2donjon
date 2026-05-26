# Optional PyGan Backend

PyGan support is optional. The production converter still uses the built-in
pure Python ASCII LCM writer by default. PyGan is used as a DRAGON/DONJON-side
validation and integration backend.

## What PyGan Is Used For

Use PyGan when you want to:

- check whether `lcm`, `lifo`, and `cle2000` are importable from Python;
- read a native DRAGON/DONJON COMPO or MULTICOMPO file through the official LCM
  bindings;
- compare PyGan's view of a reference COMPO tree with openmc2donjon's ASCII LCM
  reader in future validation tools;
- run CLE-2000 procedures from Python in local developer workflows.

Do not treat PyGan as a required dependency for the normal HDF5-to-ASCII
conversion path. This command still uses the default ASCII writer:

```sh
openmc2donjon mgxs_library.h5 -o out.mcompo.txt --check
```

## Install PyGan

PyGan is built from the DRAGON/DONJON source tree. A typical local install is:

```sh
cd "$DRAGON_ROOT/PyGan"
FORTRANPATH="$(command -v gfortran)" make pip=1 openmp=1 donjon
```

On the development machine used for this project, PyGan is installed in the
`openmc-dev` Python environment. If your shell has multiple Python
installations, run the checks with the same Python environment that will run
`openmc2donjon`.

## Check Availability

```sh
openmc2donjon pygan-doctor
```

Expected successful output looks like:

```text
pygan_backend=available
role=optional DRAGON/DONJON validation and integration backend; the default converter writer remains pure Python ASCII
lcm=available (.../lcm.cpython-312-darwin.so)
lifo=available (.../lifo.cpython-312-darwin.so)
cle2000=available (.../cle2000.cpython-312-darwin.so)
```

If PyGan is missing, this command exits non-zero and reports which modules are
not importable. The default converter still works without PyGan.

## Inspect A DRAGON/DONJON COMPO

Use `pygan-inspect-compo` to inspect a native DRAGON/DONJON LCM ASCII file:

```sh
openmc2donjon pygan-inspect-compo FUEL30.COMPO \
  --summary-json fuel30.pygan.json
```

The command reports a structural summary:

```text
PyGan COMPO inspection
  schema: openmc2donjon.pygan-compo-inspect.v1
  path: FUEL30.COMPO
  object_name: FUEL30.COMPO
  signature: L_MULTICOMPO
  top_keys: SIGNATURE, FUEL30
  root_name: FUEL30
  root_keys: STATE-VECTOR, MIXTURES, COMMENT, GLOBAL
  state_vector_head: 1, 2, 896, 900, 4, 0, 1, 2, 0, 1, 0, 2006
  mixtures: 1
  calculations: 896
```

The JSON output uses schema `openmc2donjon.pygan-compo-inspect.v1`.

## Path Handling Note

PyGan's `LCM_INP` loader has an old GANLIB convention: when asked to open
`FUEL30.COMPO`, it actually reads a file named `_FUEL30.COMPO` in the current
working directory. `openmc2donjon pygan-inspect-compo` hides this detail by
staging a temporary `_basename` link to the file you pass on the command line.

You can therefore pass normal absolute or relative paths:

```sh
openmc2donjon pygan-inspect-compo /path/to/FUEL30.COMPO
```

## Current Scope

Implemented:

- `pygan-doctor`
- `pygan-inspect-compo`
- Web command catalog entries for both commands

Not implemented yet:

- PyGan writer backend for OpenMC HDF5 conversion
- PyGan-vs-ASCII semantic diff
- CLE-2000 execution wrappers for production conversion

The next useful step is a comparison command that reads the same COMPO with
PyGan and with `openmc2donjon.lcm_ascii`, then checks that both readers see the
same structural tree.
