# Handoff Runbook

Run the C5G7 acceptance:

```bash
bash /Users/wen/dragon-5.1/Donjon/data/openmc2donjon/run_acceptance.sh
```

Run only the DONJON handoff smoke:

```bash
bash /Users/wen/dragon-5.1/Donjon/data/openmc2donjon/run_handoff_smoke.sh
```

Regenerate fresh C5G7 outputs and rerun DONJON:

```bash
bash /Users/wen/dragon-5.1/Donjon/data/openmc2donjon/run_production_pipeline_smoke.sh
```

Validate the handoff manifest:

```bash
/opt/homebrew/bin/python3.14 /Users/wen/dragon-5.1/Donjon/data/openmc2donjon/validate_handoff_case_manifests.py --check
```

Validate the accepted baseline manifest:

```bash
/opt/homebrew/bin/python3.14 /Users/wen/dragon-5.1/Donjon/data/openmc2donjon/validate_accepted_baseline.py --check
```
