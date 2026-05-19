# C5G7 MGXS Health Audit

- Input HDF5: `/Users/wen/dragon-5.1/Donjon/data/openmc2donjon/c5g7_assembly_p1_adf_production.h5`
- Floor: `1.000e-10`
- Mixtures: `9`
- Energy groups: `7`
- Zero-total mixtures: `0`
- Bad group entries: `0`
- Negative-removal entries: `0`
- Row-balance bad entries: `0`
- Non-finite entries: `0`
- Total XS range: `1.592060e-01` to `2.650380e+00`
- Removal range: `5.977259e-02` to `5.838888e-01`
- Max row-balance residual: `2.664535e-15`

## By COMPO

| COMPO | Count | Zero-total mixtures | Bad group entries | Negative-removal entries |
| --- | ---: | ---: | ---: | ---: |
| `` | 9 | 0 | 0 | 0 |

## By Code

| Code | Count | Zero-total mixtures | Bad group entries | Negative-removal entries |
| --- | ---: | ---: | ---: | ---: |
| `` | 9 | 0 | 0 | 0 |

## By Axial Layer

| Layer | Count | Zero-total mixtures | Bad group entries | Negative-removal entries |
| --- | ---: | ---: | ---: | ---: |
| `0` | 9 | 0 | 0 | 0 |

## First Bad Entries

| Mixture | Code | COMPO | Layer | Group | Total | Self scatter | Removal |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |

## First Row-Balance Bad Entries

| Mixture | Code | COMPO | Layer | Group | Total | Absorption | Scatter row sum | Residual |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |

Bad group entries include non-finite totals/scatter, total below the requested floor, or total minus P0 self-scatter below the requested floor. Row-balance entries separately test total - absorption - sum(P0 scatter row), which controls whether DONJON removal is consistent with independently tallied absorption.
