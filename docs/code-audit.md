# Code Audit and Hardening

This report records the full-repository audit performed on 2026-08-11. The
project remains an unofficial evidence collector; the audit does not turn
package availability into a compatibility guarantee.

## Baseline

- 179 offline unit tests pass.
- `rocm-matrix check` validates schemas, catalog entries, standalone evidence,
  profiles, and generated documents.
- No exhaustive historical resolver or physical-GPU backtest is performed by
  default.

## Findings addressed

### Evidence identity and status consistency

Historical candidates could report `artifact_available: true` while their
artifact evidence status was `not_collected`. History migration now normalizes
that contradiction and validation rejects new contradictions.

Runtime and hardware promotion now requires a candidate hash, target platform
tag, Python tag, observed GFX, exact Torch version, and an observable ROCm
version. HIP is retained as a separate runtime field and successful evidence
without an observed HIP version is not promoted.

### Persistence and source integrity

Generated JSON, Markdown, manifests, and cache bodies are written atomically.
Cached source bodies are hash-checked both for offline reads and conditional
HTTP `304` responses. A tampered cache fails closed instead of becoming source
evidence.

Runtime, hardware, community, framework, SDK, and extension evidence preserves
monotonic generation times and does not append duplicate record identities.

### Catalog coverage

The catalog contains package snapshots, normalized candidates, source metadata,
profiles, and bundle schemas. CI polling and local machine diagnostics are not
part of the Matrix collection pipeline.

The catalog also records SHA-256 digests for every tracked artifact. Consumers
must verify those bytes before using a cached snapshot. Package candidates now
carry TorchAudio through integration, identity, rendering, and downstream
installation planning. Version-history validation is platform-aware;
the Windows fields in version history are compatibility aliases rather than
the canonical evidence for Linux or macOS records.

Manager-side backups keep requirement files beside their metadata and verify a
recorded digest before restore. The Manager candidate CLI defaults to exact
installable candidates; artifact-only history remains available only through an
explicit kind filter.

The Manager's read-only `plan` path now uses the same command builder as
`install`, so the user sees the target Python, index, and complete Torch,
TorchVision, and TorchAudio package command before any apply step. Manager CI
also runs the offline suite on both Linux and Windows.

### Follow-up audit

- The current offline suite contains 181 tests. Pyright reports no code errors;
  its only remaining warnings are optional Torch imports used by local probes.
- The current local runtime and hardware records are one Windows `gfx1201`
  environment. They are ignored local evidence and do not establish support
  for Linux, other GFX targets, or other Python environments.

## Remaining limitations

- Resolver results still prove dependency resolution only; they do not prove
  imports or physical GPU execution.
- Runtime and hardware evidence is local by default and remains ignored by Git.
- Historical releases with missing archives remain distinct from explicit
  unsupported claims.
- Linux documentation and local runtime or hardware evidence
  may remain `not_collected`; package or wheel availability never fills those
  gaps by inference.
- Legacy patch-release candidates preserve whether their GFX evidence came from
  an exact release table or a documented HIP SDK series fallback.
- The repository does not provide an installer UI or perform exhaustive matrix
  backtesting.

## Reproduction commands

```powershell
python -m unittest discover -s tests -v
rocm-matrix check
```

Both commands are offline and do not modify a target ROCm or ComfyUI
environment.
