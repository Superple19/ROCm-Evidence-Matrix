# Local diagnostic evidence

Runtime and hardware results are local diagnostic records. They are not treated
as official AMD support and do not replace resolver, CI, or hardware evidence.

Prepare a privacy-redacted local report from a verification result:

```text
rocm-evidence --input data/verifications/runtime.json --kind runtime
rocm-evidence --input data/verifications/hardware.json --kind hardware
```

Review the generated JSON locally. Do not include user names, hostnames,
absolute paths, tokens, or other private data. The command does not upload,
submit, or add anything to the shared catalog, and this directory is not an
intake path for user reports.
