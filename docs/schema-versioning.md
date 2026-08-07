# Schema versioning policy

Every committed machine-readable document has a top-level integer
`schema_version`. The schema file is the normative contract for that document.

## Compatible changes

Keep the existing schema version for additive changes that do not change the
meaning of existing fields. Consumers must ignore unknown fields and continue
to reject missing required fields.

## Breaking changes

Increment the schema version when a field is removed, its meaning or type
changes, an identity format changes, or a required relationship changes. Keep
the previous schema and provide a migration path for committed data.

## Platform evidence

New platform-specific evidence belongs under `platform_evidence` or
`platforms`. The existing `windows_*` fields are compatibility aliases for
older consumers and must remain value-equivalent until a future schema version
removes them.

Generated Markdown is not versioned as an API. Consumers should use the JSON
files listed by `data/catalog.json` and validate them against the referenced
schema before consuming them.
