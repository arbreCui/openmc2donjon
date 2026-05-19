# Project Status

## Accepted

C5G7 assembly-wise validation is locked as the current project baseline.

- OpenMC reference: `k = 1.18798`.
- DONJON diffusion: `k = 1.1896194220`, about `+164 pcm`.
- DONJON SPN3: `k = 1.1912802458`, about `+330 pcm`.
- DONJON SPN3 with first-order scattering retained: `k = 1.1912822723`.
- Two-group ADF smoke: `ADF k = 1.18533289`, `NODF k = 1.20179343`.

The accepted production HDF5 is
`/Users/wen/dragon-5.1/Donjon/data/openmc2donjon/c5g7_assembly_p1_adf_production.h5`.

## Converter

The converter path is in place:

- LCM ASCII reader/writer.
- MULTICOMPO writer.
- MACROLIB writer.
- dense Legendre scatter to DRAGON sparse scatter conversion.
- CLI preflight checks for required transport, volume, and ADF payload fields.
- manifest-driven handoff runner for DONJON deck replacement and k-effective checks.
- experimental two-state `BURN`-axis serializer smoke through DONJON `NCR:`.

## Hex

Hex support has been done as capability work, but this directory no longer treats
the exploratory hex material as an accepted benchmark. The next hex milestone is
to choose or build a benchmark with complete material/profile/control-rod inputs
and a defensible reference solution.

## Next Work

The main line should stay on C5G7 until it is boring and reproducible:

1. Keep the C5G7 acceptance runner green.
2. Keep the manifest handoff smoke green.
3. Keep the experimental `BURN`-axis smoke separate from accepted validation.
4. Add the next benchmark only when its source cards and reference solution are
   complete enough to be a real physics comparison.
