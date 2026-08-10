# ROCm Evidence Matrix architecture

ROCm Evidence Matrix separates evidence by two independent dimensions:

- `distribution_family`: `therock` or `legacy`
- `platform`: `windows`, `linux`, `macos`, or `unknown`
- `channel`: `stable`, `nightly`, or `staging`
- `evidence_kind`: documentation, package, CI, resolver, runtime, or hardware

The distribution family describes how an artifact or release is produced. The
platform describes where the artifact or observation applies. TheRock and
legacy both have platform-specific adapters; legacy Linux package artifacts
remain separate from legacy Windows HIP SDK evidence.

These dimensions are independent. For example, a nightly wheel is identified
by its configured source channel, not by parsing a version string, and a
future Linux legacy source would remain `distribution_family=legacy` with
`platform=linux`.

## Data flow

```text
source adapters
  -> cached observations (.cache/, ignored)
  -> normalized TheRock and legacy snapshots
  -> integrated evidence and candidate catalog (data/*.json)
  -> optional verification evidence
  -> generated documentation (docs/generated/)
```

Source adapters own network formats and parser fallbacks. Normalization owns
platform, distribution, package, and GFX metadata. Integration combines independent evidence
without promoting package availability to compatibility. Renderers only read
normalized data and never fetch from the network.

Package boundaries are exposed under `rocm_evidence_matrix/sources/`,
`rocm_evidence_matrix/pipeline/`, `rocm_evidence_matrix/verification/`, and
`rocm_evidence_matrix/storage/`. Existing flat module paths remain as
compatibility imports while the migration proceeds.

Documentation and matrix records expose platform evidence under `platforms`.
The current Windows fields remain as compatibility aliases for existing
consumers; new platform integrations must use the grouped representation.

## Ownership

- `config/sources.json`: upstream source declarations and platform metadata
- `rocm_evidence_matrix/simple_index.py`: package index parsing
- `rocm_evidence_matrix/documentation.py`: shared GPU/framework documentation plus Windows-specific tables
- `rocm_evidence_matrix/legacy.py`: legacy Windows adapter
- `rocm_evidence_matrix/ci.py`: TheRock CI configuration and execution evidence
- `rocm_evidence_matrix/frameworks.py`: JAX framework and ROCm SDK component evidence
- `rocm_evidence_matrix/extensions.py`: optional compiled-extension artifact history
- `rocm_evidence_matrix/check.py`: offline evidence and generated-document validation
- `rocm_evidence_matrix/profile.py`: consumer profile validation and selection policy
- `rocm_evidence_matrix/community.py`: privacy-redacted community evidence export
- `rocm_evidence_matrix/integration.py`: evidence integration by exact GFX target
- `schemas/`: contracts for each persisted evidence type
- `data/`: committed normalized evidence and generated views
- `docs/generated/`: rebuildable Markdown views
- `profiles/`: application, runtime, framework, extension, and option profiles
- `contributions/`: manually reviewed community evidence submissions

The public package namespace is `rocm_evidence_matrix`.
The primary command names are `rocm-matrix`, `rocm-resolve`, and `rocm-verify`.
Batch verification and privacy-redacted evidence export remain auxiliary
commands.
