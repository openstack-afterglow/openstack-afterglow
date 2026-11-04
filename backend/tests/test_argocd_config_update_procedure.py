"""Execute the documented config-only Bash flow against isolated command doubles.

This proves ordering/failure handling, not Kubernetes scheduling or actual SQL DDL.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from generate_k8s import render_artifacts  # noqa: E402

_COMMAND_DOUBLE = r'''#!PYTHON
import json
import os
from pathlib import Path
import shutil
import sys
import yaml

args = sys.argv[1:]
events = Path(os.environ["EVENTS"])
def record(event):
    with events.open("a") as handle:
        handle.write(json.dumps(event) + "\n")

if Path(sys.argv[0]).name == "documented-python":
    if args and args[0] == "argocd/generate_helm_application.py":
        raise SystemExit("Config-only maintenance must not regenerate an auto-sync Application")
    if args and args[0] == "generate_k8s.py":
        target = Path(args[args.index("--output-dir") + 1])
        for source in Path(os.environ["FIXTURE_DIR"]).iterdir():
            shutil.copyfile(source, target / source.name)
        record({"action": "generation", "directory": str(target)})
        if os.environ.get("FAIL_AT") == "generation":
            print(os.environ["SECRET_CANARY"])
            print(os.environ["SECRET_CANARY"], file=sys.stderr)
            sys.exit(1)
        sys.exit(0)
    os.execv(sys.executable, [sys.executable, *args])

if args[:1] == ["-n"]:
    namespace, args = args[1], args[2:]
else:
    namespace = None

if args[0] == "kustomize":
    record({"action": "render"})
    if os.environ.get("FAIL_AT") == "render":
        sys.exit(1)
    print(Path(os.environ["RENDERED"]).read_text())
elif args[:2] == ["get", "deployment/backend"]:
    record({"action": "image-read", "namespace": namespace})
    reads = sum(json.loads(line)["action"] == "image-read" for line in events.read_text().splitlines())
    if os.environ.get("FAIL_AT") == "image-change" and reads > 1:
        print("ghcr.io/openstack-afterglow/afterglow-api@sha256:" + "b" * 64, end="")
    else:
        print(os.environ["BACKEND_IMAGE"], end="")
elif args[0] == "apply":
    name = Path(args[args.index("-f") + 1]).name
    if name.startswith("argocd-application-"):
        raise SystemExit("Config-only maintenance must not re-enable Application auto-sync")
    record({"action": "apply", "file": name})
    # API errors/output can contain configuration; the procedure must not echo it.
    print(os.environ["SECRET_CANARY"])
    print(os.environ["SECRET_CANARY"], file=sys.stderr)
    if os.environ.get("FAIL_AT") == name:
        sys.exit(1)
elif args[0] == "create":
    manifest = yaml.safe_load(Path(args[args.index("-f") + 1]).read_text())
    record({"action": "create", "job": manifest, "namespace": namespace})
    if os.environ.get("FAIL_AT") == "create":
        sys.exit(1)
elif args[0] == "wait":
    name = args[-1].removeprefix("job/")
    record({"action": "wait", "name": name, "args": args, "namespace": namespace})
    phase = "verify" if name.endswith("-verify") else "bootstrap"
    if os.environ.get("FAIL_AT") == phase:
        sys.exit(1)
elif args[:2] == ["rollout", "restart"]:
    record({"action": "restart", "args": args, "namespace": namespace})
elif args[:2] == ["rollout", "status"]:
    record({"action": "status", "args": args, "namespace": namespace})
else:
    raise SystemExit("Unexpected kubectl operation")
'''


def _documented_block():
    readme = (ROOT / "argocd/README.md").read_text()
    section = readme.split("### 관리자 ConfigMap/Secret 직접 반영", 1)[1]
    return re.search(r"```bash\n(.*?)\n```", section, re.DOTALL).group(1)


def _run_procedure(tmp_path, *, fail_at="", mutate=None, backend_image=None):
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    artifacts = render_artifacts(
        {"app": {"secret_key": "0123456789abcdef0123456789abcdef"}},
        "afterglow-dev",
    )
    job = yaml.safe_load(artifacts["base/backend/schema-job.yaml"])
    # This is Kustomize's namespace transformation, not a second generator.
    job["metadata"]["namespace"] = "afterglow-dev"
    if mutate:
        mutate(job)
    rendered = tmp_path / "rendered.yaml"
    rendered.write_text(yaml.safe_dump_all([
        yaml.safe_load(artifacts["secret.yaml"]),
        yaml.safe_load(artifacts["configmap.yaml"]),
        job,
    ]))
    for name in ("secret.yaml", "configmap.yaml"):
        (fixture / name).write_text(artifacts[name])
    binaries = tmp_path / "bin"
    binaries.mkdir()
    for name in ("kubectl", "documented-python"):
        executable = binaries / name
        executable.write_text(_COMMAND_DOUBLE.replace("#!PYTHON", f"#!{sys.executable}", 1))
        executable.chmod(0o700)
    events_path = tmp_path / "events.jsonl"
    canary = "synthetic-db-password-never-print"
    backend_image = backend_image or "ghcr.io/openstack-afterglow/afterglow-api:dev@sha256:" + "a" * 64
    env = {
        **os.environ,
        "PATH": f"{binaries}{os.pathsep}{os.environ['PATH']}",
        "PYTHON": str(binaries / "documented-python"),
        "ENV": "dev",
        "NAMESPACE": "afterglow-dev",
        "KUBECONFIG": str(tmp_path / "unused-kubeconfig"),
        "TMPDIR": str(tmp_path),
        "FIXTURE_DIR": str(fixture),
        "RENDERED": str(rendered),
        "EVENTS": str(events_path),
        "SECRET_CANARY": canary,
        "FAIL_AT": fail_at,
        "BACKEND_IMAGE": backend_image,
    }
    result = subprocess.run(
        ["bash", "-c", _documented_block()],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    events = [json.loads(line) for line in events_path.read_text().splitlines()]
    assert canary not in result.stdout + result.stderr
    # The selected rollout image is the only intentional change to generated bootstrap spec.
    job["spec"]["template"]["spec"]["containers"][0]["image"] = backend_image
    return result, events, job


def test_config_update_waits_for_exact_fresh_bootstrap_then_read_only_gate(tmp_path):
    result, events, generated = _run_procedure(tmp_path)
    assert result.returncode == 0, result.stderr
    name = generated["metadata"]["name"]
    assert re.fullmatch(r"schema-bootstrap-sql108-[0-9a-f]{32}", name)
    creates = [event for event in events if event["action"] == "create"]
    assert creates[0]["job"] == generated
    expected_verify = yaml.safe_load(yaml.safe_dump(generated))
    expected_verify["metadata"]["name"] += "-verify"
    expected_verify["spec"]["template"]["spec"]["containers"][0]["command"].append("--verify-only")
    assert creates[1]["job"] == expected_verify
    ordered = [event["action"] for event in events]
    assert ordered == [
        "generation", "render", "image-read", "apply", "apply",
        "create", "wait", "create", "wait", "image-read", "restart", "status", "status", "status",
    ]
    waits = [event for event in events if event["action"] == "wait"]
    assert [event["name"] for event in waits] == [name, name + "-verify"]
    assert all("--for=condition=complete" in event["args"] for event in waits)
    assert all("--timeout=600s" in event["args"] for event in waits)
    assert all(event["namespace"] == "afterglow-dev" for event in creates + waits)
    statuses = [event["args"][2] for event in events if event["action"] == "status"]
    assert statuses == ["deployment/backend", "deployment/frontend", "deployment/notion-worker"]
    restart = next(event for event in events if event["action"] == "restart")
    assert restart["args"] == ["rollout", "restart", "deployment", "backend", "frontend", "notion-worker"]
    directory = Path(next(event["directory"] for event in events if event["action"] == "generation"))
    assert directory.stat().st_mode & 0o077 == 0
    assert (directory / "rendered.yaml").stat().st_mode & 0o077 == 0


@pytest.mark.parametrize("fail_at", ["generation", "render", "secret.yaml", "configmap.yaml", "create", "bootstrap", "verify", "image-change"])
def test_config_update_never_restarts_after_pre_rollout_failure(tmp_path, fail_at):
    result, events, _ = _run_procedure(tmp_path, fail_at=fail_at)
    assert result.returncode != 0
    assert not any(event["action"] in {"restart", "status"} for event in events)
    if fail_at == "bootstrap":
        assert len([event for event in events if event["action"] == "create"]) == 1
    if fail_at == "generation":
        assert [event["action"] for event in events] == ["generation"]


@pytest.mark.parametrize("invalid", ["stale-name", "namespace", "parallelism", "command"])
def test_config_update_rejects_wrong_job_before_config_mutation(tmp_path, invalid):
    def mutate(job):
        if invalid == "stale-name":
            job["metadata"]["name"] = "schema-bootstrap-sql108"
        elif invalid == "namespace":
            job["metadata"]["namespace"] = "afterglow"
        elif invalid == "parallelism":
            job["spec"]["parallelism"] = 2
        else:
            job["spec"]["template"]["spec"]["containers"][0]["command"] = ["true"]

    result, events, _ = _run_procedure(tmp_path, mutate=mutate)
    assert result.returncode != 0
    assert not any(event["action"] in {"create", "wait", "restart", "status"} for event in events)
    assert not any(event["action"] == "apply" for event in events)


def test_config_update_rejects_mutable_backend_image_before_config_mutation(tmp_path):
    result, events, _ = _run_procedure(
        tmp_path, backend_image="ghcr.io/openstack-afterglow/afterglow-api:dev"
    )
    assert result.returncode != 0
    assert not any(event["action"] == "apply" for event in events)
    assert not any(event["action"] in {"create", "wait", "restart", "status"} for event in events)
