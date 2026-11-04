"""Worker runtime deployment template regression tests."""

import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

_WORKER_RUNTIME_LABEL = "afterglow.worker-runtime"
_RBAC_KINDS = {"ServiceAccount", "Role", "RoleBinding"}


def _render_helm_template(*args: str) -> list[dict]:
    helm = shutil.which("helm")
    if helm is None:
        pytest.skip("helm not available locally")

    command = [
        helm,
        "template",
        "afterglow",
        str(ROOT / "helm/afterglow"),
        "--namespace",
        "afterglow",
        *args,
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr or result.stdout
    return [doc for doc in yaml.safe_load_all(result.stdout) if doc]


def _render_worker_runtime_overlay() -> list[dict]:
    kubectl = shutil.which("kubectl")
    if kubectl is None:
        pytest.skip("kubectl not available locally")

    command = [kubectl, "kustomize", str(ROOT / "deploy/k8s-template/overlays/worker-runtime")]
    result = subprocess.run(command, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        output = f"{result.stdout}\n{result.stderr}".lower()
        if 'unknown command "kustomize"' in output or "invalid subcommand" in output:
            pytest.skip("kubectl kustomize is not supported by this kubectl build")
        raise AssertionError(result.stderr or result.stdout)
    return [doc for doc in yaml.safe_load_all(result.stdout) if doc]


def _find_doc(docs: list[dict], kind: str, name: str) -> dict:
    for doc in docs:
        metadata = doc.get("metadata", {})
        if doc.get("kind") == kind and metadata.get("name") == name:
            return doc
    raise AssertionError(f"missing {kind} {name}")


def _worker_runtime_rbac_docs(
    docs: list[dict], service_account_name: str = "afterglow-backend-worker-runtime"
) -> list[dict]:
    expected_names = {
        service_account_name,
        f"{service_account_name}-role",
        f"{service_account_name}-binding",
    }
    matched = []
    for doc in docs:
        if doc.get("kind") not in _RBAC_KINDS:
            continue
        metadata = doc.get("metadata", {})
        labels = metadata.get("labels", {})
        if labels.get(_WORKER_RUNTIME_LABEL) == "true" or metadata.get("name") in expected_names:
            matched.append(doc)
    return matched


def _rule_for(role: dict, resources: list[str]) -> dict:
    for rule in role["rules"]:
        if rule.get("resources") == resources:
            return rule
    raise AssertionError(f"missing rule for {resources}")


def _assert_minimal_worker_rbac(role: dict) -> None:
    """최소권한 확인: deployment 조회 + /scale patch 만, 전체 deployment patch/update·pods 권한 없음.

    SA 토큰 유출 시 image/command 등 deployment 스펙 변경이나 pods 열람을 막기 위함.
    """
    assert _rule_for(role, ["deployments"])["verbs"] == ["get"]
    assert _rule_for(role, ["deployments/scale"])["verbs"] == ["patch"]
    all_resources = [rule.get("resources") for rule in role["rules"]]
    assert ["pods"] not in all_resources, "pods 권한은 어댑터 미사용 — 부여 금지"


def test_helm_static_render_has_no_worker_runtime_rbac_or_service_account_name():
    docs = _render_helm_template()

    backend = _find_doc(docs, "Deployment", "backend")

    assert "serviceAccountName" not in backend["spec"]["template"]["spec"]
    assert _worker_runtime_rbac_docs(docs) == []


def test_helm_kubernetes_mode_without_rbac_keeps_only_backend_service_account_name():
    docs = _render_helm_template(
        "--set",
        "workerRuntime.mode=kubernetes",
        "--set-string",
        "workerRuntime.kubernetes.serviceAccountName=custom-worker-runtime",
        "--set",
        "workerRuntime.kubernetes.rbac.create=false",
    )

    backend = _find_doc(docs, "Deployment", "backend")

    assert backend["spec"]["template"]["spec"]["serviceAccountName"] == "custom-worker-runtime"
    assert _worker_runtime_rbac_docs(docs, "custom-worker-runtime") == []


def test_helm_kubernetes_mode_with_rbac_renders_worker_runtime_permissions():
    docs = _render_helm_template(
        "--set",
        "workerRuntime.mode=kubernetes",
        "--set-string",
        "workerRuntime.kubernetes.serviceAccountName=custom-worker-runtime",
        "--set",
        "workerRuntime.kubernetes.rbac.create=true",
    )

    backend = _find_doc(docs, "Deployment", "backend")
    service_account = _find_doc(docs, "ServiceAccount", "custom-worker-runtime")
    role = _find_doc(docs, "Role", "custom-worker-runtime-role")
    role_binding = _find_doc(docs, "RoleBinding", "custom-worker-runtime-binding")

    assert backend["spec"]["template"]["spec"]["serviceAccountName"] == "custom-worker-runtime"
    assert service_account["metadata"]["labels"][_WORKER_RUNTIME_LABEL] == "true"
    _assert_minimal_worker_rbac(role)
    assert role_binding["subjects"] == [
        {
            "kind": "ServiceAccount",
            "name": "custom-worker-runtime",
            "namespace": "afterglow",
        }
    ]
    assert role_binding["roleRef"] == {
        "apiGroup": "rbac.authorization.k8s.io",
        "kind": "Role",
        "name": "custom-worker-runtime-role",
    }


def test_worker_runtime_kustomize_overlay_renders_rbac_and_backend_service_account_name():
    docs = _render_worker_runtime_overlay()

    backend = _find_doc(docs, "Deployment", "backend")
    service_account = _find_doc(docs, "ServiceAccount", "afterglow-backend-worker-runtime")
    role = _find_doc(docs, "Role", "afterglow-backend-worker-runtime-role")
    role_binding = _find_doc(docs, "RoleBinding", "afterglow-backend-worker-runtime-binding")

    assert backend["spec"]["template"]["spec"]["serviceAccountName"] == "afterglow-backend-worker-runtime"
    assert service_account["metadata"]["labels"][_WORKER_RUNTIME_LABEL] == "true"
    _assert_minimal_worker_rbac(role)
    assert role_binding["subjects"] == [
        {
            "kind": "ServiceAccount",
            "name": "afterglow-backend-worker-runtime",
            "namespace": "afterglow",
        }
    ]
    assert role_binding["roleRef"] == {
        "apiGroup": "rbac.authorization.k8s.io",
        "kind": "Role",
        "name": "afterglow-backend-worker-runtime-role",
    }


def _assert_schema_bootstrap(
    deployment: dict, *, schema_image: str | None = None, pull_policy: str | None = None
) -> dict:
    pod = deployment["spec"]["template"]["spec"]
    writer = pod["containers"][0]
    # A regular init container blocks both app startup and Pod readiness on failure.
    # Do not turn this into a restartable sidecar or a shell that swallows errors.
    assert len(pod["initContainers"]) == 1
    bootstrap = pod["initContainers"][0]
    assert bootstrap["name"] == "schema-bootstrap"
    assert bootstrap["command"] == ["python", "-m", "scripts.bootstrap_schema", "--if-configured", "--verify-only"]
    assert "args" not in bootstrap
    assert "restartPolicy" not in bootstrap
    assert all(key not in bootstrap for key in ("lifecycle", "startupProbe", "readinessProbe", "livenessProbe"))
    assert bootstrap["image"] == (schema_image or writer["image"])
    assert bootstrap["imagePullPolicy"] == (pull_policy or writer["imagePullPolicy"])
    assert bootstrap["resources"] == writer["resources"]
    environment = {entry["name"]: entry for entry in bootstrap["env"]}
    writer_environment = {entry["name"]: entry for entry in writer["env"]}
    assert environment["AFTERGLOW_ENV"] == writer_environment["AFTERGLOW_ENV"]
    assert environment["REDIS_URL"] == writer_environment["REDIS_URL"]
    # Import all of the same Secret, including database URL and provider secrets
    # needed while the canonical settings loader validates mounted configuration.
    secret = writer_environment["DATABASE_URL"]["valueFrom"]["secretKeyRef"]
    assert secret["key"] == "DATABASE_URL"
    assert bootstrap["envFrom"] == [{"secretRef": {"name": secret["name"]}}]
    assert "DATABASE_URL" not in environment
    mounts = {mount["mountPath"]: mount for mount in bootstrap["volumeMounts"]}
    writer_mounts = {mount["mountPath"]: mount for mount in writer["volumeMounts"]}
    for path, mount in mounts.items():
        assert mount["name"] == writer_mounts[path]["name"]
        assert mount["subPath"] == writer_mounts[path]["subPath"]
        assert mount["readOnly"] is True
    assert "/app/afterglow.conf" in mounts
    return bootstrap


def _assert_schema_job(job: dict, verifier: dict) -> None:
    assert job["spec"]["completions"] == 1
    assert job["spec"]["parallelism"] == 1
    assert job["spec"]["backoffLimit"] == 0
    assert "ttlSecondsAfterFinished" not in job["spec"]
    pod = job["spec"]["template"]["spec"]
    assert pod["restartPolicy"] == "Never"
    assert "initContainers" not in pod
    assert len(pod["containers"]) == 1
    bootstrap = pod["containers"][0]
    assert bootstrap["command"] == ["python", "-m", "scripts.bootstrap_schema", "--if-configured"]
    assert "args" not in bootstrap
    for key in ("image", "imagePullPolicy", "env", "envFrom", "volumeMounts", "resources"):
        assert bootstrap[key] == verifier[key]


@pytest.mark.parametrize("auto_create_tables", [True, False])
def test_helm_singleton_schema_job_and_read_only_gates_share_api_image_and_database_config(auto_create_tables):
    docs = _render_helm_template(
        "--set",
        f"database.autoCreateTables={str(auto_create_tables).lower()}",
        "--set",
        "database.connectTimeout=23,database.poolTimeout=31",
        "--set-string",
        "image.backend.repository=registry.example.test/api,image.backend.tag=schema108",
        "--set-string",
        "image.worker.repository=registry.example.test/worker,image.worker.tag=schema108",
        "--set",
        "image.backend.pullPolicy=IfNotPresent,image.worker.pullPolicy=Never",
        "--set-string",
        "auth.providerKeys[0]=example",
    )
    for workload in ("backend", "notion-worker"):
        bootstrap = _assert_schema_bootstrap(
            _find_doc(docs, "Deployment", workload),
            schema_image="registry.example.test/api:schema108",
            pull_policy="IfNotPresent",
        )
        assert {mount["mountPath"] for mount in bootstrap["volumeMounts"]} == {
            "/app/afterglow.conf",
            "/app/config.gpu.toml",
        }
    # Disabling opportunistic app create_all must not disable the canonical gate.
    config = tomllib.loads(_find_doc(docs, "ConfigMap", "afterglow-config")["data"]["afterglow.conf"])
    assert config["database"]["auto_create_tables"] is auto_create_tables
    assert config["database"]["connect_timeout"] == 23
    assert config["database"]["pool_timeout"] == 31
    backend = _find_doc(docs, "Deployment", "backend")
    job = next(document for document in docs if document["kind"] == "Job")
    assert job["metadata"]["name"].startswith("afterglow-schema-1-")
    _assert_schema_job(job, backend["spec"]["template"]["spec"]["initContainers"][0])


@pytest.mark.parametrize("auto_create_tables", [True, False])
def test_generated_kubernetes_schema_bootstrap_shares_the_configured_database_secret(auto_create_tables):
    from generate_k8s import render_artifacts

    database_url = "mysql+asyncmy://synthetic-user:synthetic-password@database.example.test/chosen_schema"
    artifacts = render_artifacts(
        {
            "app": {"secret_key": "synthetic-app-key-" + "a" * 40},
            "database": {
                "url": database_url,
                "auto_create_tables": auto_create_tables,
                "connect_timeout": 23,
                "pool_timeout": 31,
            },
        },
        "synthetic-namespace",
    )
    secret = yaml.safe_load(artifacts["secret.yaml"])
    assert secret["stringData"]["DATABASE_URL"] == database_url
    configmap = yaml.safe_load(artifacts["configmap.yaml"])
    config = tomllib.loads(configmap["data"]["afterglow.conf"])
    assert config["database"]["auto_create_tables"] is auto_create_tables
    assert config["database"]["connect_timeout"] == 23
    assert config["database"]["pool_timeout"] == 31
    assert database_url not in artifacts["configmap.yaml"]
    for path in ("base/backend/deployment.yaml", "base/worker/notion-deployment.yaml"):
        deployment = yaml.safe_load(artifacts[path])
        bootstrap = _assert_schema_bootstrap(
            deployment, schema_image="ghcr.io/openstack-afterglow/afterglow-api:latest"
        )
        assert database_url not in artifacts[path]
        assert bootstrap["envFrom"] == [{"secretRef": {"name": secret["metadata"]["name"]}}]
        volumes = {volume["name"]: volume for volume in deployment["spec"]["template"]["spec"]["volumes"]}
        assert volumes["afterglow-config-volume"]["configMap"]["name"] == configmap["metadata"]["name"]
    job = yaml.safe_load(artifacts["base/backend/schema-job.yaml"])
    backend = yaml.safe_load(artifacts["base/backend/deployment.yaml"])
    _assert_schema_job(job, backend["spec"]["template"]["spec"]["initContainers"][0])
    assert job["metadata"]["name"].startswith("schema-bootstrap-sql108-")


def test_worker_runtime_overlay_keeps_canonical_schema_gate_on_backend_and_notion_worker():
    docs = _render_worker_runtime_overlay()
    for workload in ("backend", "notion-worker"):
        _assert_schema_bootstrap(
            _find_doc(docs, "Deployment", workload), schema_image="ghcr.io/openstack-afterglow/afterglow-api:latest"
        )
    backend = _find_doc(docs, "Deployment", "backend")
    job = _find_doc(docs, "Job", "schema-bootstrap-sql108")
    _assert_schema_job(job, backend["spec"]["template"]["spec"]["initContainers"][0])


@pytest.mark.parametrize("changed_input", ["unchanged", "database", "configuration", "image"])
def test_generated_schema_job_gets_a_fresh_identity_for_every_generation(monkeypatch, changed_input):
    import generate_k8s

    cfg = {
        "app": {"secret_key": "synthetic-app-key-" + "a" * 40},
        "database": {"url": "mysql+asyncmy://synthetic:password@database.example.test/schema_one", "pool_timeout": 31},
    }
    first = generate_k8s.render_artifacts(cfg)
    if changed_input == "database":
        cfg["database"]["url"] = "mysql+asyncmy://synthetic:rotated@database.example.test/schema_two"
    elif changed_input == "configuration":
        cfg["database"]["pool_timeout"] = 47
    elif changed_input == "image":
        sources = generate_k8s._application_sources

        def pinned_api_sources(template):
            return {
                path: content.replace("afterglow-api:latest", "afterglow-api:schema108-qualified")
                for path, content in sources(template).items()
            }

        monkeypatch.setattr(generate_k8s, "_application_sources", pinned_api_sources)
    second = generate_k8s.render_artifacts(cfg)
    first_job = yaml.safe_load(first["base/backend/schema-job.yaml"])
    second_job = yaml.safe_load(second["base/backend/schema-job.yaml"])
    assert first_job["metadata"]["name"] != second_job["metadata"]["name"]
    backend = yaml.safe_load(second["base/backend/deployment.yaml"])
    _assert_schema_job(second_job, backend["spec"]["template"]["spec"]["initContainers"][0])


def test_generated_schema_job_name_is_independent_of_database_credentials(monkeypatch):
    from uuid import UUID

    import generate_k8s

    rollout_id = UUID("e540d746-8d72-42ee-8d32-070675cfcbac")
    monkeypatch.setattr(generate_k8s, "uuid4", lambda: rollout_id)
    names = []
    for password in ("short", "a-different-private-password"):
        artifacts = generate_k8s.render_artifacts(
            {
                "app": {"secret_key": "synthetic-app-key-" + "a" * 40},
                "database": {"url": f"mysql+asyncmy://synthetic:{password}@database.example.test/schema"},
            }
        )
        names.append(yaml.safe_load(artifacts["base/backend/schema-job.yaml"])["metadata"]["name"])
    assert names == [f"schema-bootstrap-sql108-{rollout_id.hex}"] * 2


@pytest.mark.parametrize(
    "changed_input",
    [
        "image.backend.tag=schema108-updated",
        "resources.backend.limits.cpu=5",
        "database.connectTimeout=27",
    ],
)
def test_helm_schema_job_identity_changes_with_immutable_inputs_without_argocd_render_drift(changed_input):
    initial = _render_helm_template("--set-string", "image.backend.tag=schema108-initial")
    repeated = _render_helm_template("--set-string", "image.backend.tag=schema108-initial")
    updated = _render_helm_template(
        "--set", "image.backend.tag=schema108-initial", "--set", changed_input
    )
    jobs = [next(document for document in docs if document["kind"] == "Job") for docs in (initial, repeated, updated)]
    # All these Helm-template calls have revision 1, as the ArgoCD source does.
    assert all(job["metadata"]["name"].startswith("afterglow-schema-1-") for job in jobs)
    assert jobs[0] == jobs[1]
    assert jobs[0]["metadata"]["name"] != jobs[2]["metadata"]["name"]
    backend = _find_doc(updated, "Deployment", "backend")
    _assert_schema_job(jobs[2], backend["spec"]["template"]["spec"]["initContainers"][0])
    if changed_input.startswith("image."):
        assert jobs[0]["spec"]["template"]["spec"]["containers"][0]["image"] != (
            jobs[2]["spec"]["template"]["spec"]["containers"][0]["image"]
        )


def test_helm_schema_job_identity_does_not_fingerprint_database_credentials():
    jobs = []
    for password in ("short", "a-different-private-password"):
        docs = _render_helm_template(
            "--set-string",
            f"secrets.databaseUrl=mysql+asyncmy://synthetic:{password}@database.example.test/schema",
        )
        jobs.append(next(document for document in docs if document["kind"] == "Job"))
    assert jobs[0] == jobs[1]


def test_helm_schema_job_reruns_as_argocd_sync_hook_without_ttl_cleanup_race():
    docs = _render_helm_template()
    job = next(document for document in docs if document["kind"] == "Job")
    assert job["metadata"]["annotations"] == {
        "argocd.argoproj.io/hook": "Sync",
        "argocd.argoproj.io/hook-delete-policy": "BeforeHookCreation",
    }
    assert "ttlSecondsAfterFinished" not in job["spec"]
