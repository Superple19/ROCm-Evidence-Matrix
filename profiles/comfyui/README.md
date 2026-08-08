# ComfyUI profile

This profile describes the core ROCm/PyTorch environment that a ComfyUI
consumer may select. It does not claim that every candidate imports or runs on
physical hardware.

The resolver must select a candidate for the requested platform, Python tag,
channel, and GFX target. A candidate with unknown GFX support is not treated as
compatible automatically. Runtime and hardware verification remain separate
evidence kinds.

Extension requirements and performance recommendations belong under
`extensions/` and must not be added to the core profile.
