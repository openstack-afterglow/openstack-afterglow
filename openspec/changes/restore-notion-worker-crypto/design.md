## Context

The DMSLab Kolla deployment runs `ghcr.io/openstack-afterglow/afterglow-worker:v1.21.0` on the controller group. The process and database connection are healthy, but every synchronization cycle fails at `app.services.k3s_crypto` because the final worker environment does not contain `afterglow_crypto`. `Dockerfile` copies `services/afterglow-crypto` into the builder, but `uv sync --only-group worker` installs only dependencies named in the worker group, where the package is absent. The backend environment currently resolves the same package from a separate Git repository revision, so the repository-owned copy is not authoritative.

The relevant Notion worker code is unchanged between the production v1.21.0 release commit and current `dev`; later model additions are unrelated to the worker synchronization path. Production recovery must nevertheless deploy only the worker image by immutable digest and leave backend/frontend image references unchanged.

## Goals / Non-Goals

**Goals:**

- Make `services/afterglow-crypto` the single source for the backend and worker crypto package.
- Install that package as a regular, non-editable distribution so the final images do not depend on build-context source paths.
- Catch future worker dependency omissions against the final image rather than only the developer environment.
- Publish a Linux amd64 worker image from the verified `dev` commit and pin Kolla to its immutable manifest digest.
- Prove recovery through per-node running-image evidence, clean worker logs, successful target completion, and a newer database synchronization timestamp.

**Non-Goals:**

- Change AES-GCM/HKDF algorithms, key domains, ciphertext formats, or stored data.
- Change Notion target schemas, API credentials, schedules, or the global runtime gate.
- Upgrade production backend/frontend images or perform unrelated database migrations.
- Change the existing controller placement model for the Notion worker.

## Decisions

### Repository-owned path dependency

Declare `afterglow-crypto` by name in both the main project dependencies and the `worker` dependency group, with `[tool.uv.sources]` mapping the name to `../services/afterglow-crypto`. uv path dependencies are regular non-editable installs by default, so `/app/.venv` remains self-contained after the builder source directory is omitted from the runtime image.

Alternatives rejected:

- Repeating the Git URL in the worker group would restore the import but retain two sources of truth and make the copied local package dead build input.
- Copying the package directly into the final image would bypass package metadata and dependency locking.
- Installing it with an extra Docker `pip install` step would create an untracked second resolver path.

### Final-image behavioral smoke

Add a reusable image smoke script that runs the final worker image with its normal Python environment, imports `app.services.k3s_crypto`, and performs a Notion configuration encrypt/decrypt round trip using disposable keys. This fails on the production defect and verifies more than source-text membership.

The smoke is an explicit image command rather than part of the ordinary unit gate because it requires a built image. The repository gate continues to cover crypto behavior in the normal environment; container verification covers packaging.

### Immutable worker-only production rollout

Push the verified `dev` commit through the existing Docker Build & Push workflow, resolve the resulting `afterglow-worker:dev` manifest to its immutable digest, and set only `afterglow_worker_image_ref` in Kolla operator configuration to that digest. Run Kolla prechecks and service-scoped reconfiguration from `/etc/kolla` as `pieroot` with its virtual environment activated.

A mutable `:dev` reference is never left in production. Backend and frontend remain on their existing refs. Rollback is the previous worker digest and the same service-scoped Kolla path.

### Recovery success criteria

Deployment succeeds only when:

1. every reachable intended controller reports the expected running image ID/digest and no restart loop;
2. worker startup reaches DB connection and scheduler registration without `ModuleNotFoundError`;
3. an enabled Notion target logs a completed synchronization;
4. `notion_targets.last_sync` advances beyond `2026-09-15T11:26:43Z`; and
5. the public admin surface reflects the newer timestamp.

Container `running` state alone is insufficient.

## Risks / Trade-offs

- **Risk: current `dev` worker contains unrelated source changes.** Relevant Notion worker and sync code are unchanged from v1.21.0; deploy only the worker digest and verify startup/database behavior before accepting the rollout. Roll back immediately on schema or runtime incompatibility.
- **Risk: local path dependencies become editable or leak build paths.** Keep the uv source non-editable and inspect the final image metadata/import path during smoke verification.
- **Risk: Kolla host-key drift blocks a complete rollout.** Do not disable host verification. Validate the current controller host key through a trusted controller or console before updating the deployment host trust record.
- **Risk: repeated Notion writes during multi-controller restart.** Use the existing placement and interval contract; verify completion and timestamps without changing scheduling semantics in this recovery.
- **Trade-off: CI publishes the standard dev image set.** The production change remains worker-only by digest even if CI also rebuilds backend/frontend artifacts.
