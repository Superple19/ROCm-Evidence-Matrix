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
