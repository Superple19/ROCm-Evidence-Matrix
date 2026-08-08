# Community evidence submissions

Community runtime and hardware results are self-reported evidence. They are
not treated as official AMD support and do not replace resolver or CI evidence.

Prepare a privacy-redacted submission from a local verification result:

```text
rocm-evidence --input data/verifications/runtime.json --kind runtime
rocm-evidence --input data/verifications/hardware.json --kind hardware
```

Review the generated JSON before opening a pull request. Do not include user
names, hostnames, absolute paths, tokens, or other private data. The command
does not upload anything automatically.
