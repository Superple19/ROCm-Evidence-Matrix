# ROCm Compatibility Matrix

ROCm Compatibility Matrix is an unofficial, community-maintained project that collects evidence about ROCm availability and compatibility across platforms. Windows and Linux package sources are supported through platform-specific adapters.

The repository keeps machine-readable observations separate from generated documentation. Package availability does not imply that a package resolves, imports, or works on physical hardware.

## Current scope

The collector reads official AMD stable, nightly, and staging sources. It:

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
- Collects legacy Windows HIP SDK release support, versioned GPU support, and pre-multi-arch Windows PyTorch artifacts.
- Collects legacy Linux manylinux wheel artifacts without inventing GFX support.
- Validates consumer profiles and keeps ComfyUI extension policy separate from core package evidence.
- Prepares privacy-redacted community runtime and hardware submissions without uploading them.
- Generates a Markdown availability summary from the JSON snapshots.

Official documentation sources and their evidence boundaries are listed in [docs/sources.md](docs/sources.md). The data boundaries and processing layers are documented in [docs/architecture.md](docs/architecture.md), the machine-readable consumer contract is in [docs/consumer-contract.md](docs/consumer-contract.md), and schema changes follow [docs/schema-versioning.md](docs/schema-versioning.md).

Current generated views:

- [Integrated compatibility matrix](docs/generated/compatibility-matrix.md)
- [Package availability](docs/generated/package-availability.md)
- [Historical package candidates](docs/generated/history.md)
- [JAX framework artifact history](docs/generated/framework-history.md)
- [Optional extension artifact history](docs/generated/extension-history.md)
- [ROCm SDK component evidence](docs/generated/sdk-components.md)
- [Legacy platform ROCm support](docs/generated/legacy-windows.md)
- [Legacy Linux ROCm artifacts](docs/generated/legacy-linux.md)

## Development environment

Create and activate a repository-local virtual environment before running project commands:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --editable .
```

The project currently has no third-party runtime dependencies. Future collector and documentation dependencies will be declared in `pyproject.toml` and installed only into `.venv`.

## Collect data

Collect TheRock and legacy evidence independently, then build integrated data and documentation:

```powershell
rocm-matrix collect therock
rocm-matrix collect legacy
rocm-matrix build
```

Each `collect` command fetches source responses and normalizes that distribution family. After changing a parser, rebuild every downstream stage from the local cache without network access:

```powershell
rocm-matrix normalize therock
rocm-matrix normalize legacy
rocm-matrix integrate
rocm-matrix render
```

`integrate` writes the machine-readable matrix, while `render` writes Markdown from normalized and integrated data. `build` remains a convenience command that runs both stages.

Run the offline quality gate after collection or parser changes:

```powershell
rocm-matrix check
```

It validates every catalog artifact, profile, standalone evidence file, and generated Markdown view without making network requests.

Each collection command writes its source results to `data/status/therock.json` or `data/status/legacy.json`. A failed source does not stop unrelated adapters, and its previously collected evidence is retained. The command exits unsuccessfully after all adapters finish if any source failed.

Raw responses are stored by SHA-256 under the ignored `.cache/sources/` directory. `data/observations/source-manifest.json` records each URL, content hash, validator headers, encoding, and observation time. Later collections send conditional requests when an `ETag` or `Last-Modified` value is available and reuse the cached body when the source has not changed.

Source adapters prefer official machine-readable data or source markup when available. Declared rendered-page fallbacks remain independently validated, and normalized source records identify the URL that succeeded and whether fallback was required.

Package snapshots are written to `data/snapshots/` with explicit platform metadata. Documentation evidence is written to `data/documentation.json`, legacy Windows evidence to `data/legacy-windows.json`, legacy Linux evidence to `data/legacy-linux.json`, discovered release history to `data/version-history.json`, the append-only package catalog to `data/history.json`, and the integrated view to `data/matrix.json`. Generated Markdown is stored under `docs/generated/`.

Each collection replaces the current snapshots and merges every observed compatible package set into the history catalog. A candidate remains in the catalog if its upstream artifact later disappears, while its current availability is updated separately.

Historical candidates retain an immutable `distribution_family` (`therock` or `legacy`). The generated history view computes `lifecycle` as `current` for the newest known ROCm build within each distribution family and channel, and `historical` for older builds. Lifecycle is derived state and is not part of the source observation identity.

Version discovery combines TheRock releases and `version.json` with the official ROCm release list and versioned Windows documentation branches. The resulting view keeps declared Windows support separate from documentation availability: `archive_missing` means that no matching archived document was discovered, while `unsupported` requires an explicit Windows support statement.

Limit collection to one or more channels or GPU targets when developing a parser:

```powershell
rocm-matrix collect therock --source nightly --gfx gfx1201 --output-dir .tmp/snapshots
```

## Resolve a package candidate

Query the historical catalog for a specific environment:

```powershell
rocm-resolve --platform windows --gfx gfx1201 --channel stable --rocm 7.13.0 --python 3.12
```

The resolver selects the newest matching candidate by default and prints a pinned `pip` command. Add `--torch 2.9` to request a Torch series, or `--all` to list every match. Legacy candidates print direct wheel URLs with `--no-index`; TheRock candidates use their configured package index and device extras. The resolver does not install packages or claim that dependency resolution, imports, or execution have been verified.

## Verify dependency resolution

Verify one candidate with `pip --dry-run` in a disposable virtual environment:

```powershell
rocm-verify --gfx gfx1201 --channel stable --rocm 7.14.0
```

The result is appended to `data/verifications/resolver.json` with the exact candidate, interpreter, command, resolved packages, artifact hashes when reported by pip, timestamp, and pass or fail result. The verifier does not install or import ROCm packages. Package indexes without separate metadata may require pip to download wheel archives, and source-only metadata packages may run their build backend inside the disposable environment. Its pip cache is also contained in that environment and deleted afterward.

A passing record establishes only `resolver_verified`. Runtime imports and physical GPU execution require separate isolated tests and must be recorded as `runtime_verified` or `hardware_verified` evidence.

Triton is an optional extension and is tracked in [extension history](docs/generated/extension-history.md), not multiplied into every core Torch candidate. The core resolver command installs the Torch package set only; install or verify Triton separately when the selected workflow requires it.

For Linux TheRock candidates, `rocm-verify-matrix` runs the resolver across stable and nightly channels by default, available representative GFX targets, and each candidate Python tag. Add `--channel staging` when staging evidence is needed. Use `--limit` while developing and override the target wheel tag when needed:

```text
rocm-verify-matrix --platform linux --gfx gfx1201 --python cp312 --limit 1
```

Resolver, runtime, and hardware outputs under `data/verifications/` are local machine evidence and are ignored by Git.

Collect local runtime and hardware evidence against an exact candidate when the matching environment is available:

```powershell
rocm-matrix runtime --candidate-id <candidate-id> --gfx gfx1201
rocm-matrix hardware --candidate-id <candidate-id> --gfx gfx1201
```

Both commands append timestamped records locally. Use `rocm-evidence` to create a privacy-redacted submission for manual review; no evidence is uploaded automatically.

GitHub Actions collection uses `GITHUB_TOKEN` when present. GitHub API 403/429 responses are retried with bounded backoff; if collection still fails, the previous CI executions remain in the evidence file and the failed adapter is recorded separately.

Compatibility profiles use `schemas/profile.schema.json`. They keep framework, runtime, extension, and option constraints separate from core evidence, classify each constraint as `required`, `optional`, or `conflicting`, and link claims to evidence IDs. A `verified` claim must include at least one evidence reference.

The current ComfyUI profile is under `profiles/comfyui/`. Its extension profiles
are optional and remain unverified until explicit resolver, runtime, or hardware
evidence is linked. Prepare a manually reviewed community submission with:

```text
rocm-evidence --input data/verifications/runtime.json --kind runtime
rocm-evidence --input data/verifications/hardware.json --kind hardware
```

The command redacts local identity and paths, adds a content hash, and writes
no network requests. Community evidence is self-reported and never replaces
official or hardware verification evidence.

## Run tests

```powershell
python -m unittest discover -s tests -v
```
