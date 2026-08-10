# Official Data Sources

This document lists the primary sources used by ROCm Evidence Matrix. It describes what each source can establish, which platform it covers, and where GPU architecture affects the result.

The project is unofficial and community-maintained. A linked artifact or package is evidence of availability, not proof that it works on physical hardware.

The repository supports Windows and Linux package sources. Platform-specific
observations must retain their platform and distribution family rather than
being merged into one generic ROCm result.

## Source format policy

Collectors prefer authoritative machine-readable data or source markup over rendered pages. A rendered HTML parser remains available only when the configuration declares it as a fallback, and each observation records the URL that actually succeeded plus whether the fallback was used.

AMD's Python package repositories currently return the standardized HTML Simple API even when PEP 691 JSON is requested. Those indexes therefore remain the primary artifact source. TheRock publishes several different kinds of official evidence: roadmap status and release guidance are maintained in Markdown, the repository version is JSON, CI coverage is configured in Python source, and build artifact structure is TOML. Collectors must use each source only for the claim it owns instead of treating one source as a complete compatibility matrix.

## Compatibility and hardware documentation

### Current ROCm compatibility matrix

- URL: https://rocm.docs.amd.com/en/latest/compatibility/compatibility-matrix.html
- Authority: AMD ROCm documentation
- Use: Current ROCm, operating system, driver, GPU architecture, and framework compatibility.
- Evidence: `documented`
- Notes: The current matrix applies to Linux and Windows and should be the primary source for current released ROCm versions.

### AMD GPU specifications

- Preferred URL: https://raw.githubusercontent.com/ROCm/ROCm/develop/docs/reference/gpu-specs.rst
- Fallback URL: https://rocm.docs.amd.com/en/latest/reference/gpu-specs.html
- Authority: AMD ROCm documentation
- Use: Map a GPU or APU product name to its architecture and exact LLVM target, such as `gfx1201`, `gfx1100`, or `gfx1151`.
- Evidence: `documented`
- Notes: The official RST list-table source is preferred because its table identity explicitly supplies the product category. Rendered HTML is retained as a validated fallback. Product-to-target mapping does not by itself establish Windows or framework support.

### Legacy Windows compatibility matrices

- URL: https://rocm.docs.amd.com/projects/radeon-ryzen/en/latest/docs/compatibility/compatibilityrad/windows/windows_compatibility.html
- Authority: AMD Radeon and Ryzen ROCm documentation
- Use: Windows PyTorch support history through ROCm 7.2.1.
- Evidence: `documented`
- Notes: Starting with ROCm Core SDK 7.13.0, support documentation is unified in the current ROCm compatibility matrix.

### Legacy Windows system requirements

- URL: https://rocm.docs.amd.com/projects/radeon-ryzen/en/latest/docs/shared/hipsdk/reference/system-requirements.html
- Authority: AMD Radeon and Ryzen ROCm documentation
- Use: Historical GPU and APU mapping and the distinction between Runtime and HIP SDK support.
- Evidence: `documented`
- Notes: A GPU that is absent from the applicable versioned table is not officially supported for that release. Always preserve the documentation version when recording historical data.

## TheRock development and packaging sources

### GPU development status

- URL: https://github.com/ROCm/TheRock/blob/main/SUPPORTED_GPUS.md
- Authority: ROCm TheRock repository
- Use: Architecture-specific Build Passing, Sanity Tested, and Release Ready status for Windows and Linux.
- Evidence: `artifact_available` for Build Passing; stronger test claims must remain separate.
- Notes: This is TheRock's prioritized roadmap and the authoritative source for these three declared readiness fields. Build Passing means an artifact was produced. It does not prove device enumeration, library loading, or kernel execution on the target GPU. Configured CI coverage and observed CI results are separate evidence and must not overwrite these fields.

### Repository version

- URL: https://github.com/ROCm/TheRock/blob/main/version.json
- Authority: ROCm TheRock repository
- Use: Current ROCm version declared by the TheRock source tree.
- Evidence: `documented`
- Notes: Use the `rocm-version` value directly. Do not infer the repository version from a wheel filename, documentation heading, or branch name.

### CI GPU family configuration

- URL: https://github.com/ROCm/TheRock/blob/main/build_tools/github_actions/amdgpu_family_matrix.py
- Authority: ROCm TheRock repository
- Use: Configured presubmit, postsubmit, and nightly GPU families, operating systems, runner labels, fetched GFX targets, build variants, and test scope modifiers.
- Evidence: `ci_configured`
- Notes: The file identifies itself as the source of truth for GitHub workflows. A configured Windows runner or GFX target proves intended CI coverage only; it does not prove that the latest job passed and must not be converted into Build Passing, Sanity Tested, or Release Ready.

### Build artifact topology

- URL: https://github.com/ROCm/TheRock/blob/main/BUILD_TOPOLOGY.toml
- Authority: ROCm TheRock repository
- Use: Artifact groups, target-specific and target-neutral outputs, dependencies, platform exclusions, and build stages.
- Evidence: `documented`
- Notes: This is the source of truth for build artifact structure, not GPU readiness or runtime compatibility.

### Release and package documentation

- URL: https://github.com/ROCm/TheRock/blob/main/RELEASES.md
- Authority: ROCm TheRock repository
- Use: Multi-architecture packaging, device extras, package relationships, supported GPU targets, and framework package combinations.
- Evidence: `documented`
- Notes: This document defines the relationship between architecture-neutral packages and GPU-specific device packages.

### PyTorch version compatibility

- URL: https://github.com/pytorch/pytorch/wiki/PyTorch-Versions
- Authority: PyTorch repository wiki
- Use: Historical Torch, TorchVision, and TorchAudio release-series compatibility.
- Evidence: `documented`
- Notes: This source establishes framework release relationships only. ROCm build suffixes and Windows wheel availability must still be observed in AMD package indexes.

### TheRock HUD

- URL: https://therock-hud.amd.com/
- Authority: AMD TheRock CI status service
- Use: Current build and test status.
- Evidence: Depends on the reported job and result.
- Notes: Preserve the job identity, target, commit or build identifier, result, and observation time. This is observed CI execution evidence, unlike the configured coverage in the GPU family matrix. Do not reduce all HUD results to a single supported flag or use them to rewrite TheRock's declared roadmap fields.

### TheRock releases

- URL: https://github.com/ROCm/TheRock/releases
- Authority: ROCm TheRock repository
- Use: Tagged TheRock release history and release metadata.

### GitHub API access

- API sources: `api.github.com` endpoints declared in `config/sources.json`
- Authentication: optional `GITHUB_TOKEN` environment variable
- Behavior: 403/429 responses use bounded backoff; a failed adapter is recorded
  and prior evidence remains preserved.
- Credentials are never stored in source manifests or committed data.
- Evidence: `documented` or `artifact_available`, depending on the recorded claim.
- Notes: The collector uses the official GitHub Releases API and reads tagged `SUPPORTED_GPUS.md` files to preserve versioned readiness observations. A release whose tagged support document is absent is recorded as `archive_missing`, not unsupported.

### ROCm releases

- URL: https://rocm.docs.amd.com/en/latest/release/versions.html
- Authority: AMD ROCm documentation
- Use: Discover released ROCm versions, release dates, and versioned documentation links.
- Evidence: `documented`

### Versioned Windows documentation branches

- URL: https://github.com/ROCm/rocm-install-on-windows/branches
- Authority: ROCm Windows installation documentation repository
- Use: Discover archived `docs/{version}` documentation versions without guessing URLs.
- Evidence: `documented`
- Notes: AMD documents Windows by major.minor release series while Linux patch versions may differ. The collector prefers an exact branch and otherwise selects the newest branch in the same major.minor series. Missing branches remain distinct from explicit unsupported status.

## Stable artifact sources

### Stable multi-architecture Python packages

- URL: https://repo.amd.com/rocm/whl-multi-arch/
- Authority: AMD package repository
- Use: Released ROCm and framework Python package availability.
- Evidence: `artifact_available`
- Required checks: Package version, Python ABI tag, platform tag matching the selected adapter, and every required device package for the selected exact `gfx` target.

### Stable multi-architecture tarballs

- URL: https://repo.amd.com/rocm/tarball-multi-arch/
- Authority: AMD package repository
- Use: Released ROCm SDK tarball availability for Windows and Linux.
- Evidence: `artifact_available`
- Required checks: ROCm version, operating system, architecture scope, exact target or target family, filename, and download URL.

### Legacy Windows ROCm releases

- URL: https://repo.radeon.com/rocm/windows/
- Authority: AMD Radeon package repository
- Use: Historical Windows ROCm release directories and HIP SDK artifacts.
- Evidence: `artifact_available`
- Notes: Keep this source separate from the newer multi-architecture Python package repository.

### HIP SDK release versioning

- URL: https://rocm.docs.amd.com/projects/install-on-windows/en/latest/conceptual/release-versioning.html
- Authority: AMD HIP SDK for Windows documentation
- Use: Identify joint Windows HIP SDK releases and Linux-only skipped release series.
- Evidence: `documented`
- Notes: A joint HIP SDK release does not imply that PyTorch on Windows was available for that release.

### Versioned HIP SDK system requirements

- URL pattern: `https://rocm.docs.amd.com/projects/install-on-windows/en/docs-{version}/reference/system-requirements.html`
- Authority: AMD HIP SDK for Windows documentation
- Use: Preserve product, architecture, exact GFX target, Runtime status, and HIP SDK status for a documented release series.
- Evidence: `documented`
- Notes: Runtime and HIP SDK status are separate fields. Missing archived documentation remains unknown rather than unsupported.

The current collector has versioned GPU tables for ROCm 6.1, 6.4, and 7.1. ROCm 5.5, 5.7, and 6.2 are retained as documented Windows release series, but their GPU-level history remains incomplete until a stable official archive is identified.

## Development artifact sources

### Multi-architecture nightly Python packages

- URL: https://rocm.nightlies.amd.com/whl-multi-arch/
- Authority: AMD ROCm nightly repository
- Channel: `nightly`
- Use: Unified development packages for ROCm, PyTorch, TorchVision, TorchAudio, Triton, and GPU-specific device code.
- Evidence: `artifact_available`

For an exact target such as `gfx1201`, a complete PyTorch candidate must include compatible versions of at least:

- `torch`
- `torchvision`
- `torchaudio`
- `rocm-sdk-core`
- `rocm-sdk-libraries`
- `rocm-sdk-device-gfx1201`
- `amd-torch-device-gfx1201`
- `amd-torchvision-device-gfx1201`

The package names above are an example for `gfx1201`. Collectors must substitute the detected target and must not hard-code that architecture.

## ComfyUI extension artifact sources

Extension collection is explicit and independent from core ROCm candidate
collection. The configured sources in `config/sources.json` currently use the
official PyPI JSON API for bitsandbytes, Flash Attention, AITER, SageAttention,
and Triton. The collector preserves wheel/source filenames, versions, Python
ABI tags, platform tags, URLs, and observation times in
`data/extensions/snapshots/` and `data/extensions/catalog.json`.

An extension artifact source establishes only `artifact_available`. It does
not establish compatibility with a selected Torch, ROCm, HIP, GFX, or target
runtime. The source adapter also supports explicit Simple API and GitHub
release-asset entries for future sources; those entries must be added to the
configuration rather than inferred from arbitrary URLs.

### Multi-architecture staging Python packages

- URL: https://rocm.nightlies.amd.com/whl-staging-multi-arch/
- Authority: AMD ROCm nightly repository
- Channel: `staging`
- Use: Staging packages produced before or alongside nightly publication.
- Evidence: `artifact_available`
- Notes: Staging and nightly observations must never be merged into one channel.

### Legacy per-family nightly packages

- Example URL: https://rocm.nightlies.amd.com/v2/gfx120X-all/
- Authority: AMD ROCm nightly repository
- Channel: `nightly`
- Use: Legacy packages grouped by GPU family instead of exact device packages.
- Evidence: `artifact_available`
- Notes: Index paths vary by target family. Discover available family indexes instead of assuming that every family follows from string substitution.

## GPU target rules

GPU identity must be represented at multiple levels:

- Product: `AMD Radeon RX 9070 XT`
- Architecture: `RDNA4`
- Exact LLVM target: `gfx1201`
- Package family when applicable: `gfx120X-all`

These values are related but not interchangeable. An artifact built for `gfx120X-all` can cover multiple exact targets, while a package named `rocm-sdk-device-gfx1201` applies to one exact target.

For multi-architecture Python packages, base package availability is insufficient. A version is available for a target only when all required architecture-neutral and target-specific packages form a compatible set for the requested operating system and Python ABI.

## Evidence boundaries

Sources establish different facts and must not be collapsed into a single compatibility claim:

- Compatibility documentation establishes `documented` support.
- A package index or release asset establishes `artifact_available`.
- A successful dependency dry run establishes `resolver_verified`.
- A successful import and software smoke test establishes `runtime_verified`.
- A successful test on identified physical hardware establishes `hardware_verified`.

Every collected observation should retain its source URL and `last_observed_at` timestamp. Historical records should retain their original URLs and exact version strings even after a source stops publishing the artifact.

## Profiles and community observations

Consumer profiles are maintained separately from upstream source authority.
`profiles/comfyui/` currently describes ComfyUI core and extension policy;
profile claims remain documented or unverified until linked to stronger evidence.

Runtime and hardware results generated on a user's physical machine are
community observations, not official support claims. `rocm-evidence` creates a
privacy-redacted, hashed submission with `source=community` and
`provenance=self-reported`. Users must review and submit it manually.
