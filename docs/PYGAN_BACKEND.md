# Optional PyGan Backend

PyGan support is optional. The production converter still uses the built-in
pure Python ASCII LCM writer by default. PyGan can also be selected as an
alternate writer backend when you want the DRAGON/DONJON Python bindings to
perform the final LCM serialization step.

## What PyGan Is Used For

Use PyGan when you want to:

- check whether `lcm`, `lifo`, and `cle2000` are importable from Python;
- write the same openmc2donjon LCM tree through PyGan's native ASCII exporter;
- read a DRAGON/DONJON LCM ASCII COMPO or MULTICOMPO export through the
  official LCM bindings;
- compare PyGan's view of a reference COMPO tree with openmc2donjon's ASCII LCM
  reader in future validation tools;
- run CLE-2000 procedures from Python in local developer workflows.

Do not treat PyGan as a required dependency for the normal HDF5-to-ASCII
conversion path. This command still uses the default ASCII writer:

```sh
openmc2donjon mgxs_library.h5 -o out.mcompo.txt --check
```

Select the optional PyGan writer explicitly:

```sh
openmc2donjon mgxs_library.h5 \
  --writer-backend pygan \
  --format multicompo \
  -o out.mcompo.txt \
  --check
```

Both backends share the same physics builders. In other words, PyGan does not
change how cross sections, scatter triplets, ADF, SPH, or branch metadata are
computed. It only replaces the final ASCII serialization layer.

Compare the built-in writer and PyGan writer semantically:

```sh
openmc2donjon compare-writers mgxs_library.h5 --format multicompo \
  --summary-json writer_compare.json
```

This writes two temporary files, reads them back as LCM ASCII, and compares the
LCM tree rather than whitespace or associative-table ordering. Real payloads use
a tolerance because PyGan's native type-2 real export is single precision.

## Recommended Demonstration Path

For a meeting or local validation demo, use this order:

1. Confirm the Python environment can import PyGan:

   ```sh
   openmc2donjon pygan-doctor
   ```

2. Convert an OpenMC MGXS handoff with the optional PyGan writer:

   ```sh
   openmc2donjon mgxs_library.h5 \
     --writer-backend pygan \
     --format multicompo \
     -o out.mcompo.txt \
     --check
   ```

3. Validate that PyGan serialization is semantically aligned with the default
   ASCII writer:

   ```sh
   openmc2donjon compare-writers mgxs_library.h5 \
     --format multicompo \
     --summary-json writer_compare.json \
     --keep-dir writer_compare_files
   ```

   A successful report should show `decision: PASS`. The comparison is semantic:
   it ignores whitespace and associative-table ordering, but checks integer,
   string, and real payloads within tolerance.

4. Inspect a DRAGON/DONJON LCM ASCII COMPO or MULTICOMPO through PyGan:

   ```sh
   openmc2donjon pygan-inspect-compo FUEL30.COMPO \
     --summary-json fuel30.pygan.json
   ```

This path demonstrates the intended PyGan role clearly: optional environment
diagnostics, optional writer backend, writer equivalence validation, and
DRAGON/DONJON LCM ASCII inspection.

In the localhost Web UI, the same story is exposed in two places:

- `/convert` reports PyGan availability for the running backend Python
  environment and enables the PyGan writer only when it is importable.
- After a successful PyGan conversion, `/convert` shows a `Validate PyGan`
  action that opens the runnable `/pygan` comparison page with paths prefilled.

## Install PyGan

PyGan is built from the DRAGON/DONJON source tree. A typical local install is:

```sh
cd "$DRAGON_ROOT/PyGan"
FORTRANPATH="$(command -v gfortran)" make pip=1 openmp=1 donjon
```

If your shell has multiple Python installations, build PyGan and run the checks
with the same Python environment that will run `openmc2donjon`.

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

Use `pygan-inspect-compo` to inspect a DRAGON/DONJON LCM ASCII file. Binary or
direct-access LCM files must first be exported to the supported ASCII form:

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
- `--writer-backend pygan` for direct HDF5 conversion to `L_MULTICOMPO` and
  `L_MACROLIB`
- `compare-writers` semantic comparison between the built-in ASCII writer and
  the PyGan writer
- Web `/convert` writer-backend status: the PyGan option reports whether the
  running backend Python environment can import PyGan
- Web `/pygan` doctor and semantic writer-comparison report
- Web command catalog entries for the PyGan diagnostics and comparison path
- Local release-smoke coverage via `scripts/run_pygan_backend_smoke.sh`

Not implemented yet:

- CLE-2000 execution wrappers for production conversion

Local smoke:

```sh
bash scripts/run_pygan_backend_smoke.sh
```

The smoke uses the bundled C5G7 production HDF5 fixture, runs `pygan-doctor`,
compares the built-in ASCII and PyGan writer outputs for both `L_MULTICOMPO`
and `L_MACROLIB`, then inspects the PyGan `L_MULTICOMPO` output. If a DONJON
runner is available, it also generates a small CLE-2000 deck that:

1. reads both PyGan ASCII outputs through DONJON `SEQ_ASCII`;
2. runs `NCR:` on the PyGan `L_MULTICOMPO`;
3. writes the NCR-extracted `L_MACROLIB`; and
4. compares the extracted macrolib against the PyGan direct `L_MACROLIB` for
   the core MGXS payloads.

Artifacts are written under
`${TMPDIR:-/tmp}/openmc2donjon_pygan_backend_smoke` by default.

If PyGan is not importable, the smoke reports a clear skip and exits
successfully, so it can remain in the default release check without requiring
every machine to have PyGan installed. If PyGan is available but DONJON is not,
the writer comparison still runs and the DONJON ingest step is skipped.

Later useful work: extend the optional DONJON/CLE-2000 smoke from
`NCR:`-extraction to a minimal keff deck.
