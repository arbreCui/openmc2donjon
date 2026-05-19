# Accepted Baseline

The accepted baseline is C5G7 assembly-wise OpenMC homogenization consumed by
DONJON.

| Quantity | Value |
| --- | ---: |
| OpenMC reference k-effective | `1.18798` |
| DONJON diffusion k-effective | `1.1896194220` |
| DONJON SPN3 k-effective | `1.1912802458` |
| DONJON SPN3 SCAT1 k-effective | `1.1912822723` |
| 2-group ADF smoke k-effective | `1.18533289` |
| 2-group NODF smoke k-effective | `1.20179343` |

Accepted artifacts:

- `c5g7_assembly_p1_adf_production.h5`
- `c5g7pa.mco`
- `c5g7_validation/c5g7pa_diffusion_keff.x2m`
- `c5g7_validation/c5g7pa_spn3_keff.x2m`
- `c5g7_validation/c5g7pa_spn3_scat1_keff.x2m`
- `c5g7_validation/c5g7pa_2g_nssf_adf_effect.x2m`

Hex is currently capability-only in this workspace. It needs a suitable accepted
benchmark before it becomes a validation line.
