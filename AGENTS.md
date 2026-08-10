# AGENTS.md

## Project Scope

- Build an unofficial, community-maintained compatibility matrix for ROCm across Windows and Linux.
- TheRock is the actively supported distribution family for collection, resolution, and runtime or hardware verification.
- Legacy ROCm and HIP SDK records are historical archive data. Preserve them, but do not expand active legacy collection or verification unless explicitly requested.
- Keep the core dataset application-agnostic. ComfyUI, Ollama, and other consumers belong in separate framework, runtime, or application profiles.
- Keep profile policy separate from core evidence. Profiles may describe consumers, extensions, and options, but must link claims to evidence IDs.
- Treat the matrix as evidence-based compatibility data, not as an official AMD support statement or a universal compatibility guarantee.
- Prefer machine-readable data that can also generate human-readable documentation.

## Language

- Write all source code, documentation, schemas, data labels, comments, user-facing text, issue templates, pull request text, and commit messages in English.
- Do not add translated duplicates to the repository unless localization becomes an explicit project feature.

## Evidence and Compatibility Levels

- Never infer support solely from a package name, version number, or nearby release.
- Record the authoritative source URL and observation time for every automatically collected claim.
- Keep these evidence levels distinct:
  - `documented`: an authoritative source explicitly states support.
  - `artifact_available`: the required package or wheel exists for the stated platform and interpreter.
  - `resolver_verified`: dependency resolution succeeds without changing an environment.
  - `runtime_verified`: imports and a minimal software-level smoke test succeed.
  - `hardware_verified`: the workload succeeds on the stated physical GPU.
- Never promote an entry to a stronger level without evidence for that level.
- Distinguish missing data from unsupported configurations. Absence of evidence is not evidence of incompatibility.
- Preserve exact version strings, build dates, Python ABI tags, platform tags, GPU architectures, and source identifiers.
- Record ROCm platform and HIP runtime versions separately. Do not assume their version numbers match.

## Source Policy

- Prefer primary sources in this order:
  1. AMD ROCm and TheRock documentation, indexes, repositories, and release metadata.
  2. Official framework or runtime documentation, package indexes, repositories, and releases.
  3. Official application documentation and releases.
  4. Reproducible community test reports.
- Community reports must include enough environment and test detail to reproduce the result.
- Community runtime and hardware reports are `source=community`, `provenance=self-reported`, and must be privacy-redacted before submission.
- Do not silently replace an authoritative value with a community claim. Store conflicting evidence explicitly.
- Do not scrape rendered pages when a stable API, package index, or machine-readable source is available.

## Data Model

- Keep shared platform facts separate from consumer-specific profiles.
- Model at least these dimensions explicitly when applicable:
  - Operating system and version.
  - Python version and ABI.
  - GPU model and `gfx` architecture.
  - ROCm platform version.
  - HIP runtime version.
  - Framework, runtime, and application versions.
  - Package artifact, platform, and device tags.
  - Verification level, test result, source, and observation time.
- Use stable identifiers and deterministic ordering so generated diffs remain reviewable.
- Version schemas deliberately and document breaking schema changes.
- Validate all committed machine-readable data against its schema.

## Automation

- Collection scripts must be deterministic, idempotent, and safe to rerun.
- Network collection must be read-only and limited to documented project sources.
- Use explicit timeouts, a descriptive user agent, bounded concurrency, and actionable errors.
- Respect API rate limits and avoid unnecessary requests.
- Cache only reproducible source responses, and record enough metadata to identify stale data.
- Do not execute downloaded artifacts during collection.
- Resolver and runtime tests must run in isolated disposable environments.
- Hardware verification must report the exact machine, driver, GPU, package set, command, and result.
- Public community submissions must redact usernames, hostnames, tokens, and absolute paths while retaining reproducibility-relevant environment fields.
- Generated files must identify their generator and must not be edited manually.
- `rocm-evidence` prepares a local, reviewable community submission; collection and evidence export must never upload credentials or results automatically.

## Engineering Style

- Keep changes small, direct, and easy to audit.
- Prefer the Python standard library unless a dependency materially improves correctness or maintainability.
- Pin development and automation dependencies when reproducibility requires it.
- Separate source collection, normalization, validation, rendering, and verification concerns.
- Do not mix application-specific policy into the shared compatibility dataset.
- Fail clearly on malformed or ambiguous source data instead of guessing.
- Add tests for parsers, version ordering, artifact filtering, schema validation, and status promotion rules.
- Use fixtures for remote data in unit tests. Live-network checks must be separate and optional.
- Never commit credentials, API tokens, machine-specific paths, virtual environments, caches, or generated temporary files.

## Documentation

- State prominently that the project is unofficial and community-maintained.
- Explain what each verification level proves and does not prove.
- Link claims to their direct sources.
- Include a `last_observed_at` value for time-sensitive data rather than describing it as permanently current.
- Keep examples factual and reproducible. Do not publish estimated compatibility as verified compatibility.

## Commit Messages

- Use Conventional Commits with `type: description` or `type(scope): description`.
- Use a short imperative subject, for example: `docs: define compatibility evidence levels`.
- Use one of these project types when applicable: `build`, `chore`, `ci`, `data`, `docs`, `feat`, `fix`, `perf`, `refactor`, `revert`, `style`, or `test`.
- When a body is useful, leave exactly one blank line after the subject, then write consecutive `-` bullet lines with no blank lines between bullets.
- Pass the body as one multiline message or use the editor; do not pass separate `-m` options for individual bullets because Git inserts paragraph breaks.
- Keep one coherent change per commit.
- Example:

  ```text
  docs: add contributor instructions

  - Define source and evidence requirements
  - Document English-only repository content
  - Standardize Conventional Commit messages
  ```

## Pull Requests

- Describe the problem, the evidence or source change, the resulting behavior or data change, and the validation performed.
- Call out schema changes and regenerated files explicitly.
- Do not combine unrelated source additions, schema redesigns, and broad generated-data updates in one pull request.
