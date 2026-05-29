# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

For narrative release notes (rationale, validation status, migration tips),
see [`RELEASE_NOTES.md`](RELEASE_NOTES.md). This file is a chronological
machine-readable index; cross-reference the release notes for context.

## [Unreleased]

See [`RELEASE_NOTES.md`](RELEASE_NOTES.md#unreleased) for the in-progress
change list (SPH sidecar/augmentation, external face-flux contracts,
`check-face-flux`, and related additions).

## [0.1.2] - 2026-05-22

OpenMC end-to-end workflow release. Adds the recipe-based statepoint
exporter, the one-step `openmc2donjon-from-openmc` entry point, ADF and
SPH equivalence carry-through, and
the accepted C5G7 production handoff with flux-ratio ADF and SPH factors.

See [`RELEASE_NOTES.md`](RELEASE_NOTES.md) for the full narrative.

## [0.1.1] - C5G7 handoff snapshot

Tagged as `v0.1.1-c5g7-handoff`. Mid-stream snapshot used to publish the
accepted C5G7 ADF + SPH handoff artifact before the OpenMC workflow
release.

## [0.1.0] - C5G7 accepted baseline

Tagged as `v0.1.0-c5g7-accepted`. First accepted C5G7 assembly-wise
DONJON/DRAGON validation: diffusion and SPN3 k-effective against an
OpenMC reference, with documented bias margins.

[Unreleased]: https://github.com/arbreCui/openmc2donjon/compare/v0.1.2-openmc-workflow...HEAD
[0.1.2]: https://github.com/arbreCui/openmc2donjon/releases/tag/v0.1.2-openmc-workflow
[0.1.1]: https://github.com/arbreCui/openmc2donjon/releases/tag/v0.1.1-c5g7-handoff
[0.1.0]: https://github.com/arbreCui/openmc2donjon/releases/tag/v0.1.0-c5g7-accepted
