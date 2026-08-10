# Consumer contract

Third-party tools should start with [`data/catalog.json`](../data/catalog.json)
instead of assuming a fixed list of files. Regenerate it with:

```powershell
rocm-matrix catalog
```

The catalog lists each committed core artifact, standalone CI/status evidence,
its schema, and its schema version. Local runtime, hardware, and resolver
outputs remain machine-local evidence and are listed only when a reviewed copy
is intentionally committed. Consumers must reject an unknown `schema_version`
or ignore fields they do not understand. Generated Markdown is presentation
output and is not a stable API.

## Stable dimensions

Every package and historical candidate is classified independently by:

- `distribution_family`: `therock` or `legacy`
- `platform`: `windows`, `linux`, `macos`, or `unknown`
- `channel`: `stable`, `nightly`, or `staging`

Do not infer channel from a version string or URL. Use the recorded source
metadata. Do not treat artifact availability as resolver, runtime, or hardware
compatibility.

`artifact_available` means that the package set was observed in the latest
collection for its source. `artifact_stale` means the candidate was observed in
an earlier collection but was absent when that source was checked again.
`not_collected` means that no current artifact observation exists; it is not a
statement of support or non-support.

Legacy direct-wheel candidates use the same history record but include
`wheel_urls`. Consumers must pass those URLs directly while using PyPI only for
ordinary third-party dependencies; they must not
apply TheRock's device-extra installation syntax to a `legacy` candidate.

Some legacy Linux releases have package artifacts but no authoritative GFX
mapping. Those candidates use `gfx_support: "unknown"` and may be listed with
`rocm-resolve --platform linux` without `--gfx`; they must not be presented as
hardware-compatible for a specific GPU.

Framework and SDK artifacts are separate machine-readable evidence. Use
`framework_history` for JAX PJRT/plugin pairs and `sdk_components` for ROCm SDK
and exact-GFX device packages. An observed alias or extension artifact is not a
complete Torch candidate unless it appears in `package_history`.

Optional compiled extensions use `extension_history`. Triton records in that
artifact are not part of core Torch candidate identity and must not be treated
as installed or compatible without separate resolver, runtime, or hardware
evidence.

## Stable identities

- GFX targets use lowercase `gfx` identifiers such as `gfx1201`.
- Source IDs are configuration IDs and are stable within the repository.
- Historical package candidate IDs are immutable observations. Windows IDs
  retain their existing format for compatibility; non-Windows candidates
  include their platform to avoid collisions.
- Evidence records are append-only where their schema says so. A generated
  view may be replaced without changing the underlying observation identity.
- Runtime and hardware records linked to a candidate include a candidate hash,
  target platform tag, Python tag, Torch/ROCm identity, and observed GFX. A
  record missing those bindings must not promote candidate status.
- Runtime and hardware records use the same normalized `os` values: `windows`,
  `linux`, `macos`, or `unknown`.
- Candidate `hip_version` may be `null` when package metadata does not expose
  the runtime HIP build. Consumers must not infer HIP from the ROCm package
  version; use runtime or hardware evidence when an observed HIP version is
  required.

## Compatibility policy

Schema files under `schemas/` are the normative contracts. A minor additive
field change keeps the schema version; a changed meaning, removed field, or
identity change requires a new schema version and migration notes.

The legacy `windows_*` version-history fields are compatibility aliases. New
consumers should read the evidence object under the release's `platform` key
(for example, `platform_evidence.windows` or `platform_evidence.linux`).

## Profiles and community evidence

Profiles under `profiles/` are policy consumed by applications; they do not
modify core package or platform evidence. Validate them against
`schemas/profile.schema.json`. A `verified` profile claim must reference at
least one evidence ID. `optional` constraints are recommendations or optional
extensions, not installation prerequisites, and `conflicting` constraints must
not be selected together.

ComfyUI extension profiles currently use `unverified` status unless resolver,
runtime, or hardware evidence is explicitly linked. Consumers must not present
an unverified extension as compatible automatically, and extension failures
must remain separate from the ComfyUI core result.

Community submissions use `schemas/community-evidence.schema.json`. They are
`source=community` and `provenance=self-reported`, not official AMD support.
Prepare them with `rocm-evidence`, review the redaction, and submit them
manually; the command performs no upload.
