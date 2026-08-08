import json
from pathlib import Path


PROFILE_KINDS = {"framework", "runtime", "application"}
CONSTRAINT_KINDS = {"framework", "runtime", "extension", "option"}
RELATIONSHIPS = {"required", "optional", "conflicting"}
CLAIM_STATUSES = {"verified", "documented", "unverified", "conflicting"}


def validate_profile(profile):
    if profile.get("schema_version") != 1:
        raise ValueError("Unsupported profile schema")
    if not profile.get("id") or not profile.get("name"):
        raise ValueError("Profile requires id and name")
    if profile.get("profile_kind") not in PROFILE_KINDS:
        raise ValueError(f"Unsupported profile kind: {profile.get('profile_kind')}")
    evidence_refs = profile.get("evidence_refs")
    if not isinstance(evidence_refs, list) or len(evidence_refs) != len(set(evidence_refs)):
        raise ValueError("Profile evidence_refs must be a unique list")
    constraint_ids = set()
    for constraint in profile.get("constraints", []):
        constraint_id = constraint.get("id")
        if not constraint_id or constraint_id in constraint_ids:
            raise ValueError(f"Duplicate profile constraint: {constraint_id}")
        constraint_ids.add(constraint_id)
        if constraint.get("kind") not in CONSTRAINT_KINDS:
            raise ValueError(f"Unsupported constraint kind: {constraint_id}")
        if constraint.get("relationship") not in RELATIONSHIPS:
            raise ValueError(f"Unsupported constraint relationship: {constraint_id}")
        if constraint.get("claim_status") not in CLAIM_STATUSES:
            raise ValueError(f"Unsupported claim status: {constraint_id}")
        refs = constraint.get("evidence_refs")
        if not isinstance(refs, list) or len(refs) != len(set(refs)):
            raise ValueError(f"Constraint evidence_refs must be unique: {constraint_id}")
        if constraint["claim_status"] == "verified" and not refs:
            raise ValueError(f"Verified constraint lacks evidence: {constraint_id}")
    return profile


def load_profile(path):
    profile = json.loads(Path(path).read_text(encoding="utf-8"))
    return validate_profile(profile)


def compatible_extensions(profiles):
    """Return only extensions with evidence strong enough for compatibility use."""
    return [profile for profile in profiles if profile.get("metadata", {}).get("domain") != "extension" or all(item.get("claim_status") in {"verified", "documented"} for item in profile.get("constraints", []))]


def validate_extension_selection(profiles):
    selected = {constraint["id"]: (profile, constraint) for profile in profiles for constraint in profile.get("constraints", []) if constraint.get("kind") == "extension"}
    for profile, constraint in selected.values():
        if constraint.get("claim_status") == "unverified":
            raise ValueError(f"Unverified extension cannot be selected as compatible: {constraint['id']}")
        conflicts = constraint.get("value", {}).get("conflicts_with", []) if isinstance(constraint.get("value"), dict) else []
        conflict = set(conflicts) & set(selected)
        if conflict:
            raise ValueError(f"Conflicting extensions selected: {constraint['id']} and {sorted(conflict)[0]}")
    return profiles


def separate_profile_results(core_result, extension_results):
    """Keep extension failures from changing the ComfyUI core result."""
    return {"core": core_result, "extensions": list(extension_results)}
