# From-OpenMC Summary JSON

`openmc2donjon-from-openmc --summary-json run_summary.json` writes a
machine-readable manifest for one recipe/statepoint export and DONJON ASCII
conversion.

The summary is meant for workflow automation and handoff records. It records
what was run, which intermediate HDF5 was used, what DONJON ASCII file was
written, and the compact physics-shape metadata needed for quick checks.

## Schema Id

```text
openmc2donjon.from-openmc-summary.v5
```

The schema id is stored in the top-level `schema` field.
The validator still accepts legacy v1/v2/v3/v4 summaries. v5 binds the final
HDF5 and ASCII bytes with SHA256 and embeds the same OpenMC fine-reference
provenance record stored in the HDF5 handoff. v4 added the
`zero_flux_fill_*` fields; each older payload still validates against its own
schema.

## Example

```json
{
  "burnup_axis": {
    "present": false
  },
  "check_passed": true,
  "check_summary_json": "check_summary.json",
  "checked": true,
  "energy_groups": 7,
  "format": "multicompo",
  "h_factor_default": null,
  "hdf5": "mgxs_library.h5",
  "hdf5_sha256": "...64 hex characters...",
  "hdf5_kept": true,
  "legendre_order": 1,
  "loaded_statepoint": true,
  "mixture_count": 2,
  "mixture_names": [
    "ASM_Y01_X01",
    "ASM_Y01_X02"
  ],
  "output": "out.mcompo.txt",
  "output_sha256": "...64 hex characters...",
  "openmc_provenance": {
    "schema": "openmc2donjon.openmc-provenance.v1",
    "status": "complete",
    "capabilities": {
      "reference_bound": true,
      "export_replayable": true,
      "transport_reproducible": true
    },
    "input_closure": {
      "attested_complete": true,
      "method": "recipe-provenance-files"
    },
    "handoff": {
      "algorithm": "openmc2donjon-hdf5-payload-sha256-v1",
      "payload_sha256": "...64 hex characters..."
    },
    "digest_sha256": "...64 hex characters..."
  },
  "package_version": "0.1.2",
  "recipe": "/case/export_recipe.py",
  "root_name": "CPO",
  "schema": "openmc2donjon.from-openmc-summary.v5",
  "selected_mixtures": null,
  "single_point_burnup": null,
  "state_points": 1,
  "statepoint": "/case/statepoint.120.h5",
  "std_dev_dataset_count": 0,
  "zero_flux_fill_macrolib": null,
  "zero_flux_fill_total_bins": null,
  "std_dev_expected_dataset_count": 11
}
```

## Fields

| Field | Type | Meaning |
| --- | --- | --- |
| `schema` | string | Literal schema id. |
| `package_version` | string | `openmc2donjon` package version that wrote the file. |
| `recipe` | string | Python recipe path loaded by the OpenMC exporter. |
| `statepoint` | string or null | OpenMC statepoint path, or null when no statepoint was provided. |
| `loaded_statepoint` | boolean | False only when `--no-load-statepoint` was used. |
| `hdf5` | string | Intermediate MGXS HDF5 handoff path used by the conversion. |
| `hdf5_sha256` | string | SHA256 of the final HDF5 bytes after any requested correction/fill. |
| `hdf5_kept` | boolean | True when the HDF5 handoff was kept with `--keep-hdf5` or `--run-dir`. |
| `output` | string | DONJON ASCII output path. |
| `output_sha256` | string | SHA256 of the generated DONJON ASCII bytes. |
| `openmc_provenance` | object | Exact fine-reference provenance record also embedded at `/provenance/openmc/record_json`. `reference_bound` plus a verified `handoff.payload_sha256` is sufficient to consume the frozen MGXS reference; `transport_reproducible` additionally requires an attested complete input manifest and is the stricter academic replay claim. |
| `format` | string | `multicompo` or `macrolib`. |
| `energy_groups` | integer | Number of energy groups exported to HDF5. |
| `legendre_order` | integer | Highest Legendre scattering order exported. |
| `std_dev_dataset_count` | integer | Number of OpenMC MGXS `*_std_dev` uncertainty datasets written to the HDF5 handoff. |
| `zero_flux_fill_macrolib` | string or null | MG macrolib used by `--fill-macrolib` to fill zero-flux/nonpositive-transport bins before checks and conversion; null when the fill was not requested. |
| `zero_flux_fill_total_bins` | integer or null | Total (mixture, group) bins substituted by the fill; null when the fill was not requested. |
| `std_dev_expected_dataset_count` | integer | Number of mean MGXS datasets whose source MGXS could have supplied a matching `*_std_dev` dataset. Synthetic zero fission fields for non-fissionable mixtures are not counted. |
| `mixture_count` | integer | Number of mixtures seen in the HDF5 handoff before optional output filtering. |
| `mixture_names` | array of strings | Mixture names in HDF5 order. |
| `state_points` | integer | Number of calculation states per mixture. One for the default production path. |
| `burnup_axis` | object | Burnup-axis summary. See below. |
| `checked` | boolean | True when `--check` ran before conversion. |
| `check_passed` | boolean or null | True when a requested preflight check passed. Null when `checked` is false. |
| `check_summary_json` | string or null | Path passed with `--check-summary-json`, when `--check` was used. Null when `checked` is false or no check summary was requested. |
| `selected_mixtures` | array of strings or null | Values passed with `--mixture`, or null when all mixtures were requested. |
| `root_name` | string or null | Root `L_MULTICOMPO` directory name, or null for root `L_MACROLIB` output. |
| `single_point_burnup` | number or null | Value passed with `--burnup`, when present. |
| `h_factor_default` | number or null | Value passed with `--h-factor-default`, when present. |

## Burnup Axis

When the HDF5 handoff has no `/state_points/burnup` axis:

```json
{
  "present": false
}
```

When a one-dimensional burnup history is present:

```json
{
  "count": 3,
  "present": true,
  "values": [0.0, 5.0, 10.0]
}
```

## Path Notes

Treat path strings as provenance fields. `recipe` and `statepoint` are recorded
from the recipe loader, while `hdf5` and `output` reflect the paths used by the
one-step CLI.

If `hdf5_kept` is false, the `hdf5` value points to a temporary handoff file
that is deleted when `openmc2donjon-from-openmc` exits. Use `--keep-hdf5` when a
reproducible handoff artifact is required. Use `--run-dir` for the standard
production layout; it sets `hdf5`, `output`, and summary paths inside the run
directory and writes a separate `manifest.json`.

## Minimal Consumer Check

```python
import json
from pathlib import Path

summary = json.loads(Path("run_summary.json").read_text())
assert summary["schema"] == "openmc2donjon.from-openmc-summary.v5"
assert summary["format"] in {"multicompo", "macrolib"}
assert summary["mixture_count"] == len(summary["mixture_names"])
assert summary["energy_groups"] > 0
assert summary["state_points"] > 0
assert summary["std_dev_dataset_count"] <= summary["std_dev_expected_dataset_count"]
assert len(summary["hdf5_sha256"]) == 64
assert len(summary["output_sha256"]) == 64
assert summary["openmc_provenance"]["capabilities"]["reference_bound"] in {True, False}
if summary["checked"]:
    assert summary["check_passed"] is True
```
