# Repository architecture

ROCm Compatibility Matrix separates evidence by two independent dimensions:

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
  -> normalized TheRock snapshots (data/therock/snapshots/)
  -> integrated evidence (data/*.json)
  -> profiles and community submission contracts
  -> generated documentation (docs/generated/)
```

Source adapters own network formats and parser fallbacks. Normalization owns
platform and distribution metadata. Integration combines independent evidence
without promoting package availability to compatibility. Renderers only read
normalized data and never fetch from the network.

Documentation and matrix records expose platform evidence under `platforms`.
The current Windows fields remain as compatibility aliases for existing
consumers; new platform integrations must use the grouped representation.

## Ownership

- `config/sources.json`: upstream source declarations and platform metadata
- `windows_rocm_matrix/simple_index.py`: package index parsing
- `windows_rocm_matrix/documentation.py`: shared GPU/framework documentation plus Windows-specific tables
- `windows_rocm_matrix/legacy.py`: legacy Windows adapter
- `windows_rocm_matrix/ci.py`: TheRock CI configuration and execution evidence
- `windows_rocm_matrix/frameworks.py`: JAX framework and ROCm SDK component evidence
- `windows_rocm_matrix/extensions.py`: optional compiled-extension artifact history
- `windows_rocm_matrix/check.py`: offline evidence and generated-document validation
- `windows_rocm_matrix/profile.py`: consumer profile validation and selection policy
- `windows_rocm_matrix/community.py`: privacy-redacted community evidence export
- `windows_rocm_matrix/integration.py`: evidence integration by exact GFX target
- `schemas/`: contracts for each persisted evidence type
- `data/`: committed normalized evidence and generated views
- `docs/generated/`: rebuildable Markdown views
- `profiles/`: application, runtime, framework, extension, and option profiles
- `contributions/`: manually reviewed community evidence submissions

The Python package keeps its historical import name for compatibility, while
the public project and command names use `rocm-matrix`.
