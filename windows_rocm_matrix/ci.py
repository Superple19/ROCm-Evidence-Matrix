import ast
import hashlib
import json
import re
from datetime import datetime, timezone


CI_STATES = {"queued", "in_progress", "success", "failure", "cancelled", "skipped", "timed_out", "unknown"}
TEST_KINDS = {"build", "sanity", "framework", "full", "unknown"}


def utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _json(text):
    value = json.loads(text)
    return value


def _state(status, conclusion):
    if status in {"queued", "in_progress"}:
        return status
    return conclusion if conclusion in CI_STATES else "unknown"


def _platform(name, labels=()):
    text = " ".join([name or "", *[str(label) for label in labels]]).lower()
    if "windows" in text:
        return "windows"
    if "linux" in text or "ubuntu" in text:
        return "linux"
    return "unknown"


def _targets(text):
    return sorted(set(re.findall(r"gfx[0-9]+[0-9a-zA-ZxX-]*", text or "")))


def _test_kind(name):
    text = (name or "").lower()
    if "full" in text:
        return "full"
    if "sanity" in text or "quick" in text:
        return "sanity"
    if "pytorch" in text or "torch" in text or "framework" in text or "python" in text:
        return "framework"
    if "build" in text or "compile" in text or "artifact" in text:
        return "build"
    return "unknown"


def parse_matrix(source, observed_at):
    tree = ast.parse(source)
    entries = []
    names = {
        "amdgpu_family_info_matrix_presubmit": "presubmit",
        "amdgpu_family_info_matrix_postsubmit": "postsubmit",
        "amdgpu_family_info_matrix_nightly": "nightly",
    }
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        name = next((item.id for item in targets if isinstance(item, ast.Name) and item.id in names), None)
        if not name:
            continue
        value = ast.literal_eval(node.value)
        for key, family in value.items():
            if not isinstance(family, dict) or "windows" not in family:
                continue
            item = family["windows"]
            runner = item.get("test-runs-on", "")
            entries.append({
                "id": f"{names[name]}:{key}:windows",
                "trigger": names[name],
                "family_key": key,
                "platform": "windows",
                "family": item.get("family"),
                "runner": runner,
                "runner_labels": item.get("test-runs-on-labels", []),
                "configured_targets": _targets(" ".join([str(key), str(item.get("family", "")), *item.get("fetch-gfx-targets", [])])),
                "fetch_gfx_targets": item.get("fetch-gfx-targets", []),
                "build_variants": item.get("build_variants", []),
                "flags": {key: item.get(key) for key in ("bypass_tests_for_releases", "sanity_check_only_for_family", "run-full-tests-only", "nightly_check_only_for_family") if key in item},
                "observed_at": observed_at,
            })
    return {"schema_version": 1, "source": {"id": "therock-ci-matrix", "url": "https://raw.githubusercontent.com/ROCm/TheRock/main/build_tools/github_actions/amdgpu_family_matrix.py"}, "generated_at": observed_at, "entries": sorted(entries, key=lambda row: row["id"])}


def _github_record(run, job, observed_at, workflow):
    name = job.get("name") or ""
    labels = job.get("labels") or []
    target_text = " ".join([name, *[str(label) for label in labels], run.get("display_title", "")])
    execution_id = f"github:{run.get('workflow_id')}:{run.get('id')}:{run.get('run_attempt', 1)}:{job.get('id')}"
    observation = {
        "state": _state(job.get("status"), job.get("conclusion")),
        "run_status": run.get("status"),
        "conclusion": job.get("conclusion"),
        "created_at": run.get("created_at"),
        "run_started_at": run.get("run_started_at"),
        "started_at": job.get("started_at"),
        "completed_at": job.get("completed_at"),
        "observed_at": observed_at,
    }
    return {
        "id": execution_id,
        "source": "github_actions",
        "workflow_id": run.get("workflow_id"),
        "workflow_name": workflow.get("name") or run.get("name"),
        "run_id": run.get("id"),
        "run_attempt": run.get("run_attempt", 1),
        "job_id": job.get("id"),
        "job_name": name,
        "head_sha": run.get("head_sha") or job.get("head_sha"),
        "platform": _platform(name, labels),
        "targets": _targets(target_text),
        "test_kind": _test_kind(name),
        "url": job.get("html_url") or run.get("html_url"),
        "observations": [observation],
    }


def _merge_execution(existing, records):
    by_id = {item["id"]: item for item in existing.get("executions", [])}
    for record in records:
        current = by_id.get(record["id"])
        if current is None:
            by_id[record["id"]] = record
            continue
        known = {(item.get("state"), item.get("conclusion"), item.get("started_at"), item.get("completed_at"), item.get("run_status")) for item in current.get("observations", [])}
        for observation in record["observations"]:
            key = (observation.get("state"), observation.get("conclusion"), observation.get("started_at"), observation.get("completed_at"), observation.get("run_status"))
            if key not in known:
                current.setdefault("observations", []).append(observation)
        current["observations"] = sorted(current.get("observations", []), key=lambda item: (item.get("observed_at") or "", item.get("state") or ""))
    return sorted(by_id.values(), key=lambda item: item["id"])


def build_evidence(github_records, hud_records, existing=None, observed_at=None, failures=None):
    existing = existing or {"schema_version": 1, "generated_at": observed_at or utc_now(), "executions": [], "adapter_failures": []}
    document = {
        "schema_version": 1,
        "generated_at": observed_at or utc_now(),
        "executions": _merge_execution(existing, github_records + hud_records),
        "adapter_failures": list(existing.get("adapter_failures", [])),
    }
    for failure in failures or []:
        if failure not in document["adapter_failures"]:
            document["adapter_failures"].append(failure)
    return document


def collect_github(source_config, reader, observed_at):
    workflows = _json(reader(source_config["workflows"]["url"])).get("workflows", [])
    records = []
    selected_workflows = [workflow for workflow in workflows if ("windows" in workflow.get("path", "").lower() or "multi_arch" in workflow.get("path", "").lower() or "pytorch" in workflow.get("path", "").lower() or "rocm_wheels" in workflow.get("path", "").lower() or "artifacts" in workflow.get("path", "").lower())]
    for workflow in selected_workflows[:20]:
        path = workflow.get("path", "")
        if not ("windows" in path.lower() or "multi_arch" in path.lower() or "pytorch" in path.lower() or "rocm_wheels" in path.lower() or "artifacts" in path.lower()):
            continue
        runs_url = source_config["runs_api"].format(workflow_id=workflow["id"])
        runs = _json(reader(runs_url)).get("workflow_runs", [])
        for run in runs[:20]:
            jobs = _json(reader(source_config["jobs_api"].format(run_id=run["id"]))).get("jobs", [])
            records.extend(_github_record(run, job, observed_at, workflow) for job in jobs if _platform(job.get("name"), job.get("labels")) == "windows")
    return records


def collect_hud(source_config, reader, observed_at):
    payload = _json(reader(source_config["url"]))
    records = []
    for commit in payload.get("commits", []):
        for category_name, category in commit.get("categories", {}).items():
            for item in category.get("items", {}).values():
                if not isinstance(item, dict) or "Windows" not in category_name:
                    continue
                url = item.get("url") or commit.get("ciUrl")
                run_match = re.search(r"/actions/runs/(\d+)", url or "")
                job_match = re.search(r"/job/(\d+)", url or "")
                records.append({"id": f"hud:{url}", "source": "therock_hud", "workflow_id": None, "workflow_name": "TheRock HUD", "run_id": int(run_match.group(1)) if run_match else None, "run_attempt": 1, "job_id": int(job_match.group(1)) if job_match else None, "job_name": item.get("name", ""), "head_sha": commit.get("sha"), "platform": "windows", "targets": _targets(item.get("name", "")), "test_kind": _test_kind(item.get("name", "")), "url": url, "observations": [{"state": _state(item.get("status"), item.get("conclusion")), "run_status": item.get("status"), "conclusion": item.get("conclusion"), "created_at": commit.get("timestamp"), "run_started_at": None, "started_at": item.get("startedAt"), "completed_at": item.get("completedAt"), "observed_at": observed_at}]})
    return records
