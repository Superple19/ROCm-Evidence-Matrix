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
- Generates a Markdown availability summary from the JSON snapshots.

Official documentation sources and their evidence boundaries are listed in [docs/sources.md](docs/sources.md).

Current generated views:

- [Integrated compatibility matrix](docs/generated/compatibility-matrix.md)
- [Package availability](docs/generated/package-availability.md)

## Development environment

Create and activate a repository-local virtual environment before running project commands:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --editable .
```

The project currently has no third-party runtime dependencies. Future collector and documentation dependencies will be declared in `pyproject.toml` and installed only into `.venv`.

## Collect data

Run the collector from the activated virtual environment:

```powershell
windows-rocm-matrix
```

Package snapshots are written to `data/snapshots/`. Documentation evidence is written to `data/documentation.json`, and the integrated view is written to `data/matrix.json`. Generated Markdown is stored under `docs/generated/`.

Each collection replaces the current snapshot. Git history preserves earlier observations without mirroring every historical wheel still present in an upstream index.

Limit collection to one or more channels or GPU targets when developing a parser:

```powershell
windows-rocm-matrix --source nightly --gfx gfx1201 --output-dir .tmp/snapshots --docs-output .tmp/package-availability.md --skip-documentation
```

## Run tests

```powershell
python -m unittest discover -s tests -v
```
