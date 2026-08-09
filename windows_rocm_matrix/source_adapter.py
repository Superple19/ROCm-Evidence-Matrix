from datetime import datetime, timezone


def utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def monotonic_generated_at(existing, observed_at):
    values = [value for value in (existing.get("generated_at") if existing else None, observed_at) if value]
    return max(values) if values else utc_now()


def run_source_adapter(source, collect, observed_at=None):
    observed_at = observed_at or utc_now()
    try:
        value = collect()
    except (OSError, ValueError) as error:
        return None, {
            "source_id": source["id"],
            "url": source["url"],
            "status": "failed",
            "observed_at": observed_at,
            "error": f"{type(error).__name__}: {error}",
        }
    return value, {
        "source_id": source["id"],
        "url": source["url"],
        "status": "passed",
        "observed_at": observed_at,
        "error": None,
    }


def collection_status(family, started_at, results):
    return {
        "schema_version": 1,
        "distribution_family": family,
        "started_at": started_at,
        "completed_at": utc_now(),
        "results": sorted(results, key=lambda item: item["source_id"]),
    }
