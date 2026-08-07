# Consumer contract

Third-party tools should start with [`data/catalog.json`](../data/catalog.json)
instead of assuming a fixed list of files. Regenerate it with:

```powershell
rocm-matrix catalog
```

The catalog lists each machine-readable artifact, its schema, and its schema
version. Consumers must reject an unknown `schema_version` or ignore fields
they do not understand. Generated Markdown is presentation output and is not a
stable API.

## Stable dimensions

Every package and historical candidate is classified independently by:

- `distribution_family`: `therock` or `legacy`
- `platform`: `windows`, `linux`, `macos`, or `unknown`
- `channel`: `stable`, `nightly`, or `staging`

Do not infer channel from a version string or URL. Use the recorded source
metadata. Do not treat artifact availability as resolver, runtime, or hardware
compatibility.

Legacy direct-wheel candidates use the same history record but include
`wheel_urls`. Consumers must use those URLs with `--no-index`; they must not
apply TheRock's device-extra installation syntax to a `legacy` candidate.

Some legacy Linux releases have package artifacts but no authoritative GFX
mapping. Those candidates use `gfx_support: "unknown"` and may be listed with
`rocm-resolve --platform linux` without `--gfx`; they must not be presented as
hardware-compatible for a specific GPU.

## Stable identities

- GFX targets use lowercase `gfx` identifiers such as `gfx1201`.
- Source IDs are configuration IDs and are stable within the repository.
- Historical package candidate IDs are immutable observations. Windows IDs
  retain their existing format for compatibility; non-Windows candidates
  include their platform to avoid collisions.
- Evidence records are append-only where their schema says so. A generated
  view may be replaced without changing the underlying observation identity.

## Compatibility policy

Schema files under `schemas/` are the normative contracts. A minor additive
field change keeps the schema version; a changed meaning, removed field, or
identity change requires a new schema version and migration notes.

The legacy `windows_*` version-history fields are compatibility aliases. New
consumers should read `platform_evidence.windows` instead.
