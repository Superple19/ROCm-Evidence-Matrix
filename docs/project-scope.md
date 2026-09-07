# Project Scope

ROCm Evidence Matrix is a machine-readable, historical evidence catalog for
official ROCm/TheRock package availability. It integrates source observations
into installable package candidates and keeps optional verification evidence
separate. It is not an AMD support statement, an installer, or an exhaustive
historical backtesting service.

## Active distribution family

TheRock is the actively supported distribution family. Active collection covers:

- Official stable and nightly package indexes, plus explicit legacy archive refreshes.
- ROCm, Torch, TorchVision, TorchAudio, SDK, and GFX-specific package links.
- TheRock documentation and release metadata.

Platform coverage is source-scoped. A Linux package observation does not imply
that the corresponding Linux documentation, runtime, or hardware evidence has
been collected.

## Historical archive

Legacy ROCm and HIP SDK records remain part of the repository because they are
useful for historical lookup and reproducibility. They are archive evidence:

- Existing observations and generated documents are preserved.
- Legacy collection is explicit and never part of the default TheRock workflow.
- New local execution coverage is not promised for legacy data; Manager owns it.
- Legacy `distribution_family` values remain in the data model for provenance.

## Out of scope

- Exhaustive installation or GPU execution of every historical combination.
- A guarantee that package availability implies runtime functionality.
- ComfyUI, Ollama, or other application installers.
- Automatic compatibility claims for third-party compiled extensions.

## Evidence interpretation

Consumers must distinguish `documented` and `artifact_available` from any
Manager-local execution result. A package index observation is not a runtime or
hardware guarantee. Every time-sensitive claim is tied to its source and
`last_observed_at` value.
