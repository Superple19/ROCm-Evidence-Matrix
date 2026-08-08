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

Option constraints distinguish execution policy from performance advice. A
`required` relationship describes the profile policy, while `claim_status`
still controls whether that policy has verified evidence. An `optional`
constraint must never be applied as a prerequisite by a consumer.

Consumers should call the profile selection checks before presenting an
extension as compatible. Unverified extensions are excluded, conflicting
extensions are rejected, and extension failures remain separate from the core
ComfyUI result.
