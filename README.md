# ROCm Evidence Matrix

ROCm Evidence Matrix is an unofficial, community-maintained evidence catalog for ROCm package availability across platforms. It integrates official documentation, observed artifacts, and historical source observations into machine-readable package candidates. TheRock is the actively supported distribution family. Legacy ROCm and HIP SDK records remain available as historical archive evidence.

The Python package namespace is `rocm_evidence_matrix`.

The repository keeps machine-readable observations separate from generated documentation. A candidate is an observed package combination, not an automatic compatibility claim. Package availability does not imply that a package resolves, imports, or works on physical hardware.

## Current scope

The collector reads official AMD and TheRock stable, nightly, and staging sources. It:

- Discovers exact `gfx` targets from `rocm-sdk-device-{gfx}` packages.
- Records platform-specific wheel filenames, versions, Python tags, ABI tags, platform tags, URLs, and observation times.
- Records ROCm-specific framework and extension artifacts, including Triton, JAX ROCm PJRT/plugin wheels, and Apex.
- Checks whether ROCm, PyTorch, and TorchVision device packages exist for each target.
- Reports device-package aliases without matching complete targets as separate observed artifacts.
- Keeps every platform ABI variant for the latest observed version of each package.
- Collects released platform support and product-to-GFX mappings from AMD documentation.
- Collects TheRock Build Passing, Sanity Tested, and Release Ready status by platform.
- Integrates the evidence by exact GFX target without promoting availability to compatibility.
- Classifies each source independently by distribution family, platform, and configured channel.
- Preserves observed package sets in an append-only historical catalog.
- Preserves legacy Windows HIP SDK release support, versioned GPU support, and pre-multi-arch Windows PyTorch artifacts as archive data.
- Preserves legacy Linux manylinux wheel artifacts without treating them as an actively maintained resolver path.
- Validates consumer profiles and keeps ComfyUI extension policy separate from core package evidence.
- Collects extension package artifacts independently from PyPI, simple indexes, or explicitly configured release APIs.
- Keeps local runtime and hardware diagnostics outside the published catalog.
- Generates a Markdown availability summary from the JSON snapshots.

## Privacy and sharing boundary

The Matrix collector reads only the public upstream sources explicitly listed
in its configuration. It does not inspect a user's machine, run probes on a
user's GPU, collect telemetry, or receive local runtime results automatically.
Runtime and hardware commands operate on a user-selected local environment and
write results locally. The Matrix has no upload client, submission endpoint, or
local-diagnostic intake, and those records are never added to the shared catalog.

Official documentation sources and their evidence boundaries are listed in [docs/sources.md](docs/sources.md). The data boundaries and processing layers are documented in [docs/architecture.md](docs/architecture.md), the machine-readable consumer contract is in [docs/consumer-contract.md](docs/consumer-contract.md), and the ComfyUI Manager boundary is in [docs/manager-boundary.md](docs/manager-boundary.md). Schema changes follow [docs/schema-versioning.md](docs/schema-versioning.md).
The latest repository audit and hardening notes are in [docs/code-audit.md](docs/code-audit.md).

Current generated views:

- [Integrated compatibility matrix](docs/generated/compatibility-matrix.md)
- [Package availability](docs/generated/package-availability.md)
- [Historical package candidates](docs/generated/history.md)
- [JAX framework artifact history](docs/generated/framework-history.md)
- [Optional extension artifact history](docs/generated/extension-history.md)
- [Extension artifact catalog](docs/generated/extension-catalog.md)
- [ROCm SDK component evidence](docs/generated/sdk-components.md)
- [Legacy platform ROCm support](docs/generated/legacy/legacy-windows.md)
- [Legacy Linux ROCm artifacts](docs/generated/legacy/legacy-linux.md)

## Development environment

Install `uv`, then synchronize the repository environment from `pyproject.toml`
and the committed `uv.lock`:

```powershell
uv sync
uv run rocm-matrix --help
```

For Python development and the full quality toolset:

```powershell
uv sync --extra dev
```

`uv` manages the repository-local `.venv` and keeps dependency resolution in
`uv.lock`. The collector does not install ROCm, PyTorch, or other
target-environment packages into the project environment.

## Immutable catalog bundles

Build and verify the versioned catalog bundle used by external consumers:

```powershell
uv run --locked rocm-matrix bundle `
  --output dist/rocm-matrix-catalog-2026.09.07.zip `
  --bundle-version 2026.09.07
uv run --locked rocm-matrix verify-bundle `
  dist/rocm-matrix-catalog-2026.09.07.zip
```

The bundle contains the catalog, generated evidence, application profiles, and
schemas. Its manifest records the Matrix commit, contract version, manager
compatibility, and SHA-256 for every artifact. Consumers should select a
specific bundle rather than treating the `main` branch as a data API.

## Development quality checks

Install and enable the `prek` commit-message hook once per checkout:

```powershell
uv sync --extra dev
uv run prek install --force
```

Commit messages require a Conventional Commit subject, one blank separator
line, and consecutive `-` body bullets.

Run the required lint check and the advisory analyses separately:

```powershell
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run deptry .
uv run vulture rocm_evidence_matrix tests --min-confidence 100
```

`ruff check` and `pyright` are required CI gates. Pyright stays in basic mode;
the only remaining Matrix warnings are for optional Torch imports used by
target-environment probes. Formatting, dependency analysis, and dead-code
analysis remain advisory. Do not
run `ruff format --fix` across the repository as part of a functional change;
formatting cleanup must be reviewed as a separate diff. Vulture findings may
be false positives for CLI entry points, dynamic adapters, and data-driven
imports, so they require manual review before deleting code. These tools are
development-only and are not installed for users who install the runtime
package without the `dev` extra. Import Linter remains intentionally deferred;
it can be added later without changing runtime code.

## Collect data

Collect actively supported TheRock evidence, then build integrated data and documentation:

```powershell
uv run rocm-matrix collect therock
uv run rocm-matrix collect extensions  # Explicit PyPI/simple-index/GitHub extension artifact refresh
uv run rocm-matrix collect legacy  # Explicit archive refresh; not part of the active default workflow
uv run rocm-matrix build
```

Each `collect` command fetches source responses and normalizes that distribution family. TheRock collection is the active workflow; legacy collection is an explicit archive maintenance command. After changing a parser, rebuild every downstream stage from the local cache without network access:

```powershell
uv run rocm-matrix normalize therock
uv run rocm-matrix normalize extensions
uv run rocm-matrix normalize legacy
uv run rocm-matrix integrate
uv run rocm-matrix render
```

`integrate` writes the machine-readable matrix, while `render` writes Markdown from normalized and integrated data. `build` remains a convenience command that runs both stages.

Run the offline quality gate after collection or parser changes:

```powershell
uv run rocm-matrix check
```

It validates every catalog artifact, profile, standalone evidence file, and generated Markdown view without making network requests.

Each collection command writes its source results to `data/therock/status.json` or `data/legacy/archive/status.json`. A failed source does not stop unrelated adapters, and its previously collected evidence is retained. The command exits unsuccessfully after all adapters finish if any source failed.

Raw responses are stored by SHA-256 under the ignored `.cache/sources/` directory. `data/observations/source-manifest.json` records each URL, content hash, validator headers, encoding, and observation time. Later collections send conditional requests when an `ETag` or `Last-Modified` value is available and reuse the cached body when the source has not changed.

Source adapters prefer official machine-readable data or source markup when available. Declared rendered-page fallbacks remain independently validated, and normalized source records identify the URL that succeeded and whether fallback was required.

TheRock package snapshots are written to `data/therock/snapshots/` with explicit platform metadata. Legacy Windows and Linux evidence is archived under `data/legacy/archive/`. Shared documentation, version history, the live package catalog, and the integrated view remain under `data/`. Generated Markdown is stored under `docs/generated/`, with legacy documents under `docs/generated/legacy/`.

ComfyUI extension artifacts are collected separately with explicit source configuration. They are stored in `data/extensions/snapshots/` and normalized into `data/extensions/catalog.json`. Each exact wheel or source artifact receives a deterministic extension candidate ID and records its build tag, dependency metadata, SHA-256 when the upstream provides one, URL, source ID, and observation time. The catalog does not claim Torch/ROCm/HIP/GFX ABI compatibility. Use it to show what exists, and require separate resolver or runtime evidence before allowing installation. Optional GitHub release adapters are disabled by default and must be selected explicitly.

Each collection replaces the current snapshots and merges every observed compatible package set into the history catalog. A candidate remains in the catalog if its upstream artifact later disappears, while its current availability is updated separately.

Historical candidates retain an immutable `distribution_family` (`therock` or `legacy`). The generated history view computes `lifecycle` as `current` for the newest known ROCm build within each distribution family and channel, and `historical` for older builds. Lifecycle is derived state and is not part of the source observation identity.

Version discovery combines TheRock releases and `version.json` with the official ROCm release list and versioned Windows documentation branches. The resulting view keeps declared Windows support separate from documentation availability: `archive_missing` means that no matching archived document was discovered, while `unsupported` requires an explicit Windows support statement.

Limit collection to one or more channels or GPU targets when developing a parser:

```powershell
uv run rocm-matrix collect therock --source nightly --gfx gfx1201 --output-dir .tmp/snapshots
```

## Resolve a package candidate

Query the historical catalog for a specific environment:

```powershell
uv run rocm-resolve --platform windows --gfx gfx1201 --channel stable --rocm 7.13.0 --python 3.12
```

The resolver selects the newest matching candidate by default and prints a pinned `pip` command. Add `--torch 2.9` to request a Torch series, or `--all` to list every match. Legacy candidates print official direct wheel URLs with the PyPI index for ordinary dependencies; TheRock candidates use their configured package index and device extras. The resolver does not install packages or claim that dependency resolution, imports, or execution have been verified.

Use `--count` to inspect the number of distinct candidates after applying the same filters without selecting or verifying a package:

```powershell
uv run rocm-resolve --platform windows --gfx gfx1201 --all --include-unavailable --include-failed --count
```

Use `--distribution-family legacy` to select archive candidates explicitly;
the legacy candidate still uses its recorded direct wheel URLs.

## Verify dependency resolution

Optionally verify one candidate with `pip --dry-run` in a disposable virtual environment. This is environment-specific evidence, not part of the default catalog collection:

```powershell
uv run rocm-verify --gfx gfx1201 --channel stable --rocm 7.14.0
```

The same verifier can run a legacy candidate with
`--distribution-family legacy`; removing the historical package aliases does
not remove legacy package resolution or dry-run verification.

Each result is first appended to the local `data/verifications/resolver.jsonl` evidence log. At the end of a run, the log is merged into `data/verifications/resolver.json` and tracked candidate history is written once. The record includes the exact candidate, candidate hash, interpreter, command, resolved packages, artifact hashes when reported by pip, timestamp, and pass or fail result. The verifier does not install or import ROCm packages. Legacy candidates pin their official direct wheel URLs while resolving ordinary third-party dependencies from PyPI. Package indexes without separate metadata may require pip to download wheel archives, and source-only metadata packages may run their build backend inside the disposable environment.

A passing record establishes only `resolver_verified`. Runtime imports and physical GPU execution require separate isolated tests and must be recorded as `runtime_verified` or `hardware_verified` evidence.

Triton is an optional extension and is tracked in [extension history](docs/generated/extension-history.md), not multiplied into every core Torch candidate. The core resolver command installs the Torch package set only; install or verify Triton separately when the selected workflow requires it.

The extension artifact catalog also covers bitsandbytes, Flash Attention, AITER, SageAttention, and Triton when their configured upstream sources expose artifacts. An absent record means `not_collected`, not unsupported. The Manager must keep these observations separate from the ComfyUI profile's compatibility claims.

`rocm-verify-matrix` is an auxiliary, opt-in batch form of `rocm-verify`. It runs the resolver across selected channels, representative GFX targets, and candidate Python tags. It is intended for controlled investigations, not exhaustive historical backtesting or normal catalog generation. `--all-candidates` and `--all-gfx` require an explicit `--exhaustive` opt-in. Use `--resume` to skip combinations already recorded in the JSONL log, merged output, or tracked history. Matrix jobs reuse a host-local cache (`%LOCALAPPDATA%\rocm-matrix\pip` on Windows or `~/.cache/rocm-matrix/pip` on Linux) while each resolver still runs in a disposable environment; override it with `--cache-dir` when needed. Use `--workers` to run independent resolver subprocesses concurrently; evidence is appended by the coordinator and history is merged once per run. The record separates the target platform from the verifier host; this is dependency-resolution evidence only and does not establish runtime or hardware support. Use `--limit` while developing and override the target wheel tag when needed:

```text
uv run rocm-verify-matrix --platform linux --gfx gfx1201 --python cp312 --limit 1
```

Resolver, runtime, and hardware outputs under `data/verifications/` are local machine evidence and are ignored by Git.

Collect local runtime and hardware evidence against an exact candidate when the matching environment is available:

```powershell
uv run rocm-matrix runtime --candidate-id <candidate-id> --gfx gfx1201
uv run rocm-matrix hardware --candidate-id <candidate-id> --gfx gfx1201
```

Compatibility profiles use `schemas/profile.schema.json`. They keep framework, runtime, extension, and option constraints separate from core evidence, classify each constraint as `required`, `optional`, or `conflicting`, and link claims to evidence IDs. A `verified` claim must include at least one evidence reference.

The current ComfyUI profile is under `profiles/comfyui/`. Its extension profiles
are optional and remain unverified until explicit resolver, runtime, or hardware
evidence is linked. Local diagnostics are outside the published Matrix catalog.

## Run tests

```powershell
uv run python -m unittest discover -s tests -v
```
