# Windows ROCm Compatibility Matrix

Windows ROCm Compatibility Matrix is an unofficial, community-maintained project that collects evidence about ROCm availability and compatibility on Windows.

The repository keeps machine-readable observations separate from generated documentation. Package availability does not imply that a package resolves, imports, or works on physical hardware.

## Current scope

The initial collector reads the official AMD stable, nightly, and staging Python package indexes. It:

- Discovers exact `gfx` targets from `rocm-sdk-device-{gfx}` packages.
- Records Windows wheel filenames, versions, Python tags, ABI tags, platform tags, URLs, and observation times.
- Checks whether ROCm, PyTorch, and TorchVision device packages exist for each target.
- Keeps every Windows ABI variant for the latest observed version of each package.
- Collects current released Windows support and product-to-GFX mappings from AMD documentation.
- Collects TheRock Build Passing, Sanity Tested, and Release Ready status for Windows.
- Integrates the evidence by exact GFX target without promoting availability to compatibility.
- Preserves observed package sets in an append-only historical catalog.
- Collects legacy Windows HIP SDK release support, versioned GPU support, and pre-multi-arch PyTorch artifacts.
- Generates a Markdown availability summary from the JSON snapshots.

Official documentation sources and their evidence boundaries are listed in [docs/sources.md](docs/sources.md).

Current generated views:

- [Integrated compatibility matrix](docs/generated/compatibility-matrix.md)
- [Package availability](docs/generated/package-availability.md)
- [Historical package candidates](docs/generated/history.md)
- [Legacy Windows ROCm support](docs/generated/legacy-windows.md)

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
windows-rocm-matrix collect therock
windows-rocm-matrix collect legacy
windows-rocm-matrix build
```

Each `collect` command fetches source responses and normalizes that distribution family. After changing a parser, rebuild every downstream stage from the local cache without network access:

```powershell
windows-rocm-matrix normalize therock
windows-rocm-matrix normalize legacy
windows-rocm-matrix integrate
windows-rocm-matrix render
```

`integrate` writes the machine-readable matrix, while `render` writes Markdown from normalized and integrated data. `build` remains a convenience command that runs both stages.

Each collection command writes its source results to `data/status/therock.json` or `data/status/legacy.json`. A failed source does not stop unrelated adapters, and its previously collected evidence is retained. The command exits unsuccessfully after all adapters finish if any source failed.

Raw responses are stored by SHA-256 under the ignored `.cache/sources/` directory. `data/observations/source-manifest.json` records each URL, content hash, validator headers, encoding, and observation time. Later collections send conditional requests when an `ETag` or `Last-Modified` value is available and reuse the cached body when the source has not changed.

Source adapters prefer official machine-readable data or source markup when available. Declared rendered-page fallbacks remain independently validated, and normalized source records identify the URL that succeeded and whether fallback was required.

Package snapshots are written to `data/snapshots/`. Documentation evidence is written to `data/documentation.json`, legacy Windows evidence to `data/legacy-windows.json`, the append-only package catalog to `data/history.json`, and the integrated view to `data/matrix.json`. Generated Markdown is stored under `docs/generated/`.

Each collection replaces the current snapshots and merges every observed compatible package set into the history catalog. A candidate remains in the catalog if its upstream artifact later disappears, while its current availability is updated separately.

Limit collection to one or more channels or GPU targets when developing a parser:

```powershell
windows-rocm-matrix collect therock --source nightly --gfx gfx1201 --output-dir .tmp/snapshots
```

## Resolve a package candidate

Query the historical catalog for a specific environment:

```powershell
windows-rocm-resolve --gfx gfx1201 --channel stable --rocm 7.13.0 --python 3.12
```

The resolver selects the newest matching candidate by default and prints a pinned `pip` command. Add `--torch 2.9` to request a Torch series, or `--all` to list every match. It does not install packages or claim that dependency resolution, imports, or execution have been verified.

## Verify dependency resolution

Verify one candidate with `pip --dry-run` in a disposable virtual environment:

```powershell
windows-rocm-verify --gfx gfx1201 --channel stable --rocm 7.14.0
```

The result is appended to `data/verifications/resolver.json` with the exact candidate, interpreter, command, resolved packages, artifact hashes when reported by pip, timestamp, and pass or fail result. The verifier does not install or import ROCm packages. Package indexes without separate metadata may require pip to download wheel archives, and source-only metadata packages may run their build backend inside the disposable environment. Its pip cache is also contained in that environment and deleted afterward.

A passing record establishes only `resolver_verified`. Runtime imports and physical GPU execution require separate isolated tests and must be recorded as `runtime_verified` or `hardware_verified` evidence.

## Run tests

```powershell
python -m unittest discover -s tests -v
```
