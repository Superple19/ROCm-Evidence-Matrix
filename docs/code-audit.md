# Code Audit and Hardening

This report records the full-repository audit performed on 2026-08-10. The
project remains an unofficial evidence collector; the audit does not turn
package availability into a compatibility guarantee.

## Baseline

- 133 offline unit tests pass.
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

### CI and catalog coverage

GitHub Actions collection uses bounded pagination and fails explicitly when a
configured limit is exceeded. CI promotion follows the latest observed state
for each execution attempt; configured coverage remains separate from observed
execution results.

The catalog now includes tracked CI, status, and source-manifest artifacts.
Profiles resolve `source:<id>` references against collected source records, and
reviewed community JSON is validated when present.

## Remaining limitations

- Resolver results still prove dependency resolution only; they do not prove
  imports or physical GPU execution.
- Runtime and hardware evidence is local by default and remains ignored by Git.
- CI evidence is intentionally scoped to GFX/platform execution and is not an
  exact package-build proof unless a consumer adds that binding.
- Historical releases with missing archives remain distinct from explicit
  unsupported claims.
- The repository does not provide an installer UI or perform exhaustive matrix
  backtesting.

## Reproduction commands

```powershell
python -m unittest discover -s tests -v
rocm-matrix check
```

Both commands are offline and do not modify a target ROCm or ComfyUI
environment.
