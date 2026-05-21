# Production Pipeline

The current production pipeline is C5G7 assembly-wise:

1. OpenMC produces an MGXS/ADF HDF5.
2. `openmc2donjon` converts it to LCM ASCII.
3. DONJON consumes the generated file through the locked C5G7 decks.
4. The validation scripts compare k-effective against the accepted baseline.

The config-driven SPH loop example is:

```bash
bash examples/donjon_openmc2donjon/c5g7_sph_loop/run.sh
```

Main smoke:

```bash
bash /Users/wen/dragon-5.1/Donjon/data/openmc2donjon/run_production_pipeline_smoke.sh
```

Hex support is not removed as a capability, but it is not part of the accepted
production validation pipeline until a proper benchmark is available.
