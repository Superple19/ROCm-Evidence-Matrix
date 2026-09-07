# ROCm Evidence Matrix architecture

ROCm Evidence Matrix separates evidence by two independent dimensions:

- `distribution_family`: `therock` or `legacy`
- `platform`: `windows`, `linux`, `macos`, or `unknown`
- `channel`: `stable`, `nightly`, or `staging`
- `evidence_kind`: documentation, package, or extension

Extension artifact observations may use `distribution_family=external` and
`channel=external`; they remain outside the core ROCm release dimensions.

The distribution family describes how an artifact or release is produced. The
platform describes where the artifact or observation applies. TheRock and
legacy both have platform-specific adapters; legacy Linux package artifacts
remain separate from legacy Windows HIP SDK evidence.

These dimensions are independent. For example, a nightly wheel is identified
by its configured source channel, not by parsing a version string, and a
legacy Linux package observation remains `distribution_family=legacy` with
`platform=linux`.

TheRock source configuration also records the stream host and repository
layout separately. `stream` identifies Stable, Nightly, Staging, or Dev;
`layout` identifies `whl-next` or `whl-multi-arch`; and `historical` marks
disabled archive sources that may be selected explicitly for backfill. The
layout name is not a release channel.

## Data flow

```text
source adapters
  -> cached observations (.cache/, ignored)
  -> normalized TheRock and legacy snapshots
  -> extension artifact snapshots and catalog (data/extensions/*.json)
  -> integrated evidence and candidate catalog (data/*.json)
  -> immutable catalog bundle
  -> generated documentation (docs/generated/)
```

Source adapters own network formats and parser fallbacks. Normalization owns
platform, distribution, package, and GFX metadata. Integration combines independent evidence
without promoting package availability to compatibility. Renderers only read
normalized data and never fetch from the network.

Package boundaries are exposed under `rocm_evidence_matrix/sources/` and the
flat modules that implement the active pipeline.

Documentation and matrix records expose platform evidence under `platforms`.
The current Windows fields remain optional compatibility aliases for existing
consumers; Linux-only and other platform-only targets omit them. New platform
integrations must use the grouped representation.

## Ownership

- `config/sources.json`: upstream source declarations and platform metadata
- `rocm_evidence_matrix/simple_index.py`: package index parsing
- `rocm_evidence_matrix/documentation.py`: shared GPU/framework documentation plus Windows-specific tables
- `rocm_evidence_matrix/legacy.py` and `legacy_linux.py`: legacy platform adapters
- `rocm_evidence_matrix/frameworks.py`: JAX framework and ROCm SDK component evidence
- `rocm_evidence_matrix/extensions.py`: optional compiled-extension artifact history
- `rocm_evidence_matrix/extension_sources.py`: explicit PyPI, Simple API, and GitHub extension artifact adapters
- `rocm_evidence_matrix/extension_catalog.py`: append-only extension catalog/history and human-readable rendering
- `rocm_evidence_matrix/check.py`: offline evidence and generated-document validation
- `rocm_evidence_matrix/profile.py`: consumer profile validation and selection policy
- `rocm_evidence_matrix/integration.py`: evidence integration by exact GFX target
- `schemas/`: contracts for each persisted evidence type
- `data/`: committed normalized evidence and generated views
- `docs/generated/`: rebuildable Markdown views
- `profiles/`: application, runtime, framework, extension, and option profiles

The public package namespace is `rocm_evidence_matrix`.
The primary and only Matrix command is `rocm-matrix`. Candidate execution and
local diagnostics belong to Manager.
