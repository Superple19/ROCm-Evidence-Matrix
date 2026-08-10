# Legacy compatibility names

The public project and package names are ROCm Evidence Matrix,
`rocm_evidence_matrix`, and `rocm-matrix`.

For existing checkouts and scripts, the following historical names remain
available as compatibility aliases:

- `windows_rocm_matrix` Python imports
- `windows-rocm-matrix` collection CLI
- `windows-rocm-resolve`, `windows-rocm-verify`,
  `windows-rocm-verify-matrix`, `windows-rocm-runtime`, and
  `windows-rocm-hardware`

New code and documentation must use the cross-platform names. The aliases may
be removed in a future major release after a deprecation period.

The schema `$id` values still use the original repository URL. They are stable
schema identifiers for existing consumers; changing them requires a schema
version and migration notice, even though the repository URL redirects to the
current project.
