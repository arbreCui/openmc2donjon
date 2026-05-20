# Hex Minicase

This is a small hex-domain converter example. It builds a synthetic
OpenMC-style MGXS HDF5 handoff with seven hexagonal cell domains:

```text
HEX_C
HEX_E
HEX_NE
HEX_NW
HEX_W
HEX_SW
HEX_SE
```

Each domain maps to one DONJON mixture. The file includes 3 energy groups, P1
scattering, explicit `transport_total`, volumes, and six-face ADF data:

```text
FD_E, FD_NE, FD_NW, FD_W, FD_SW, FD_SE
```

This example is a capability smoke, not a physics benchmark. It does not use a
hex reference solution and should not be promoted to accepted validation without
an OpenMC-sourced heterogeneous reference and a reproducible DONJON comparison.

## Run

```sh
bash examples/hex_minicase/run_smoke.sh
```

The smoke writes a fresh HDF5 file under `/private/tmp`, runs the input-contract
preflight, converts to `out.mcompo.txt` and `out.macrolib.txt`, and reads both
LCM ASCII files back.
