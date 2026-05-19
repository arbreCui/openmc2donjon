# Changelog

## 2026-05-19

- Cleaned the DONJON handoff workspace around the accepted C5G7 validation line.
- Removed obsolete exploratory hex validation artifacts from this workspace.
- Updated the top-level scripts so acceptance and handoff smoke are C5G7-only.
- Rewrote status, baseline, artifact, and runbook documents to match the current scope.
- Added a separate experimental `BURN`-axis DONJON `NCR:` consumer smoke.
- Extended MGXS input preflight to validate experimental `BURN`-axis HDF5 state
  layouts.
- Wired the `BURN`-axis DONJON smoke to run HDF5 preflight before conversion.
- Rejected unsupported multi-parameter branch axes instead of silently ignoring
  them.
