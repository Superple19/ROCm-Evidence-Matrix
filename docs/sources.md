# Official Data Sources

This document lists the primary sources used by Windows ROCm Compatibility Matrix. It describes what each source can establish and where GPU architecture affects the result.

The project is unofficial and community-maintained. A linked artifact or package is evidence of availability, not proof that it works on physical hardware.

## Compatibility and hardware documentation

### Current ROCm compatibility matrix

- URL: https://rocm.docs.amd.com/en/latest/compatibility/compatibility-matrix.html
- Authority: AMD ROCm documentation
- Use: Current ROCm, operating system, driver, GPU architecture, and framework compatibility.
- Evidence: `documented`
- Notes: The current matrix applies to Linux and Windows and should be the primary source for current released ROCm versions.

### AMD GPU specifications

- URL: https://rocm.docs.amd.com/en/latest/reference/gpu-specs.html
- Authority: AMD ROCm documentation
- Use: Map a GPU or APU product name to its architecture and exact LLVM target, such as `gfx1201`, `gfx1100`, or `gfx1151`.
- Evidence: `documented`
- Notes: Product-to-target mapping does not by itself establish Windows or framework support.

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
- Notes: Build Passing means an artifact was produced. It does not prove device enumeration, library loading, or kernel execution on the target GPU.

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
- Notes: Preserve the job identity, target, commit or build identifier, result, and observation time. Do not reduce all HUD results to a single supported flag.

### TheRock releases

- URL: https://github.com/ROCm/TheRock/releases
- Authority: ROCm TheRock repository
- Use: Tagged TheRock release history and release metadata.
- Evidence: `documented` or `artifact_available`, depending on the recorded claim.

### ROCm releases

- URL: https://github.com/ROCm/ROCm/releases
- Authority: ROCm repository
- Use: ROCm release history, release notes, and tags.
- Evidence: `documented`

## Stable artifact sources

### Stable multi-architecture Python packages

- URL: https://repo.amd.com/rocm/whl-multi-arch/
- Authority: AMD package repository
- Use: Released ROCm and framework Python package availability.
- Evidence: `artifact_available`
- Required checks: Package version, Python ABI tag, Windows platform tag, and every required device package for the selected exact `gfx` target.

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
