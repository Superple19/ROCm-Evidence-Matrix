# ROCm Evidence Matrix and ComfyUI ROCm Manager Boundary

This document defines the responsibility boundary between the ROCm Evidence
Matrix repository and a separate ComfyUI ROCm Manager. The matrix repository provides
shared compatibility evidence. The manager consumes that evidence to make a
local ComfyUI environment usable.

## Responsibility split

```text
ROCm and TheRock sources
        ↓
ROCm Evidence Matrix: collect → normalize → integrate → publish
        ↓ catalog, profiles, evidence references
ComfyUI ROCm Manager: detect → select → dry-run → install → verify
```

The matrix is the source of shared evidence-backed candidates. The manager is
an application-specific consumer and installer; it must not turn a local result
into a universal compatibility claim or read a moving `main` branch directly.

## Catalog bundle contract

The Matrix bundle contains `manifest.json`, `data/catalog.json`, generated
evidence, ComfyUI profiles, and the schemas required to validate them. The
manifest pins `contract_version`, the full Matrix commit, generation time,
manager compatibility, and a SHA-256 digest for every artifact. A Manager
consumer must verify the manifest and every digest before using the embedded
catalog.

`contract_version` is the bundle contract boundary. An unsupported version,
missing artifact, path traversal entry, or digest mismatch must be rejected
explicitly. The existing `--catalog` path remains the offline escape hatch for
an already extracted `data/catalog.json`; release and mirror URLs are selected
by the Manager in a later consumer implementation.

## What the Matrix should do

- Collect official TheRock and legacy package and documentation sources.
- Preserve source URLs, content hashes, timestamps, and historical observations.
- Normalize ROCm, HIP, Torch, TorchVision, TorchAudio, Python, OS, and GFX data.
- Connect related packages into stable candidate identities.
- Publish stable, nightly, staging, and historical candidates without silently
  treating artifact availability as installation or runtime success.
- Keep resolver, runtime, and hardware evidence as separate states.
- Provide immutable catalog bundles containing the schemas and generated catalog
  consumed by external tools.
- Maintain portable application profiles such as `profiles/comfyui/` without
  changing core package evidence.
- Mark claims as documented, artifact-available, verified, unverified, unsupported,
  or not collected according to their evidence.
- Preserve the distinction between `artifact_available`, `artifact_stale`, and
  `not_collected`; absence from a later source observation is not the same as
  never having collected the source.

## What the Matrix should not do

- Do not install or modify a user's ComfyUI environment.
- Do not assume that one user's GPU or runtime result proves global compatibility.
- Do not scrape ComfyUI-specific repositories as if they were core ROCm evidence.
- Do not put UI state, backup paths, installer options, or local environment state
  into the core matrix schema.
- Do not run every historical GFX × Python × candidate combination by default.
- Do not promote an artifact to `resolver_verified`, `runtime_verified`, or
  `hardware_verified` without the corresponding evidence.
- Do not duplicate the same candidate and compatibility rules in a manager-only
  catalog.
- Do not make generated documents the only source of truth; retain the structured
  catalog and evidence references.

## What the Manager should do

- Detect the selected ComfyUI directory, interpreter, operating system, GPU, and
  GFX target locally.
- Read a pinned or explicitly selected Matrix catalog version.
- Filter candidates by platform, Python tag, GFX target, distribution family, and
  channel.
- Explain why a candidate is selectable, unavailable, unverified, or incompatible.
- Run a targeted `pip --dry-run` before changing the environment.
- Back up the current package state and provide recoverable restore behavior.
- Install only the user-selected ROCm/Torch package set.
- Run local import, device-detection, and optional tensor smoke tests.
- Apply the ComfyUI profile, including extension constraints and required versus
  performance-recommended options.
- Keep installer logs, local results, and user choices separate from shared Matrix
  evidence.

## What the Manager should not do

- Do not rewrite or silently fork the Matrix catalog.
- Do not claim that a local success applies to every GPU, OS, or Python version.
- Do not run exhaustive historical verification as part of a normal installation.
- Do not install optional or unverified extensions as if they were ComfyUI core
  requirements.
- Do not make performance recommendations look like required compatibility fixes.
- Do not change ComfyUI source code to work around an installer decision.
- Keep local paths, tokens, environment details, and hardware results local.
  The Matrix and Manager provide no upload, telemetry, community intake, or
  maintainer review path.
- Do not mix Ollama, llama.cpp, or other native LLM runtime requirements into the
  Torch package resolver.

## Profile ownership

The Matrix owns the portable ComfyUI profile and its evidence references:

```text
profiles/comfyui/profile.json
profiles/comfyui/extensions/*.json
```

The profile describes constraints and confidence. The Manager interprets those
constraints for one local installation. Manager-specific preferences, backups,
logs, and UI state stay outside the Matrix profile.

## Evidence and result flow

```text
Matrix catalog candidate
        ↓
Manager local filtering
        ↓
Targeted resolver dry-run
        ↓
Optional local runtime/hardware checks
        ↓
Install or restore decision
```

`artifact_available`, `resolver_verified`, `runtime_verified`, and
`hardware_verified` remain distinct. A Manager result is local-only by default
and may later be shared as an explicitly identified observation only through a
local export; it must not rewrite the shared historical record automatically.

Package candidates may have `hip_version: null` because HIP is often exposed by
the installed runtime rather than by the package index. The Manager must not
derive a HIP version from the ROCm version string.

## Minimum consumer contract

The Manager should consume:

- the catalog schema version;
- candidate ID and candidate hash;
- distribution family and channel;
- platform, Python tags, and available GFX targets;
- package versions and wheel URLs or index identifiers;
- evidence states and evidence references;
- profile constraints and claim status.

The Matrix must keep these fields stable or publish a schema migration before
changing them. The Manager must reject unknown incompatible schema versions rather
than guessing.

## Recommended implementation order

1. Finish the Matrix catalog, schema, and evidence contract.
2. Build a Manager CLI that only reads the catalog and prints candidates.
3. Add targeted dry-run, backup, install, and restore operations.
4. Add local runtime and hardware verification.
5. Add the PySide6 UI on top of the same CLI/service layer.
6. Add optional extension installation only after ComfyUI core handling is stable.
