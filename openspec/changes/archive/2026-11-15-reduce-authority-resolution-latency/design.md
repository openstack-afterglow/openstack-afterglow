# Request-local authority resolution latency

## Boundaries

Baseline source: `06a804a9`. The external production report is `~/.local/share/afterglow-proofs/perf-20261114/REPORT.md`: quiet `/auth/me` 41–43 REST calls / 1083–1583 ms, capabilities 79–87 calls / 2889–2896 ms, conversations 122 calls / 4775 ms. Those are historical observations, not new acceptance. This change performs no production access or writes.

The local fixture runs the actual FastAPI routes, JWT/session validation, domain/provenance graph and service authorization. Keystone tokens/directory and Redis are synthetic. The benchmark user is a **non-administrator**. Eight distinct group grants span eight projects; the selected user also has direct legacy/personal grants. Each directory operation sleeps 10 ms. The chat transport is replaced only after running real `authorize_service_request`; native Lumen execution, its own authentication, endpoint discovery/token exchanges and remote policy HTTP are not timed. Existing auth fixtures fake token exchanges without adding their latency.

## Exact directory call map

`evidence/measurements.json` records every physical manager method, exact arguments/query, immediate source caller, count and all three timing samples. Calls passing through `domain_projects._call` are attributed below to their semantic origin. There is no independent `role_assignments` request per project in `_accessible_domains`: its one effective-user query discovers the project IDs.

| Native directory read | Semantic origin | non-admin `/auth/me` before/after | non-admin capabilities before/after | non-admin conversations before/after |
|---|---|---:|---:|---:|
| `users.get(user)` | `validate_session -> _access_info -> get_identity_user -> NativeOperation.get` | 1 / 1 | 2 / 1 | 1 / 1 |
| `domains.get(accounts, tenant-a, personal, tenant-b)` | `resolve_domain`, `_active_user`, `_accessible_domains` (one each) | 4 / 4 | 8 / 4 | 4 / 4 |
| `roles.list` | `NativeOperation.catalog`; standalone `get_project_access -> _trusted_catalog` in baseline chat | 1 / 1 | 2 / 1 | 2 / 1 |
| `inference_rules.list_inference_roles` | same catalog loaders | 1 / 1 | 2 / 1 | 2 / 1 |
| unfiltered `role_assignments.list()` | `domain_projects._raw` native provenance | 1 / 1 | 2 / 1 | 1 / 1 |
| `role_assignments.list(user=user, effective=True)` | `_accessible_domains` | 1 / 1 | 2 / 1 | 1 / 1 |
| `projects.get` for 12 distinct project IDs | `_accessible_domains -> _warm_exact`, selected-project fences | 12 / 12 | 24 / 12 | 12 / 12 |
| `projects.list(domain=tenant-a)` | `domain_context -> has_manager -> default_project` | 1 / 1 | 2 / 1 | 1 / 1 |
| `groups.get(team-0..7)` | `_sources -> _exact`, now `_warm_sources` then ordered pass | 8 / 8 | 16 / 8 | 8 / 8 |
| `users.list(group=team-0..7)` | `_sources -> _group_users`, now warmed with group reads | 8 / 8 | 16 / 8 | 8 / 8 |
| `role_assignments.list(user=user, system=all)` | `_is_system_admin -> has_scope_authority` | 1 / 1 | 1 / 1 | 1 / 1 |
| `groups.list(user=user)` | `has_scope_authority` system-group inventory | 1 / 1 | 1 / 1 | 1 / 1 |
| `role_assignments.list(project=own, effective=True)` | `validate_session/assert_project_membership -> _effective`; baseline chat repeats in `get_project_access -> _assignment_rows` | 1 / 1 | 1 / 1 | 2 / 1 |
| **Total** | | **41 / 41** | **79 / 41** | **44 / 41** |

Additional topology-dependent calls remain live: Default projects require `_effective(default)` and `_projection -> groups.list(domain=...)`; project parents require `_ancestors -> projects.get(parent)`; native system-group membership adds one `role_assignments.list(group=gid, system=all)` per distinct group. Their failures still belong to the ordered validation pass. System-group grant reads now warm at most four at once. Ancestors remain serial because each parent identifies the next read. Distinct project/domain objects were already warmed in baseline; there is no further independent per-project effective-list loop to parallelize in these endpoints.

### Request call chains

- `/auth/me`: `get_token_info -> _resolve_jwt_session -> validate_session/domain_context/assert_project_membership`; `_resolve_jwt_token_info` materializes `_domain_metadata -> _visible_domains -> accessible_domains` in the same operation. The handler consumes the exact-owner private snapshot. This already avoided a second complete directory operation in baseline; the improvement is parallel rounds, not a reduced call count.
- `/projects/capabilities`: baseline authentication and the handler owned separate operations. The handler calls `domain_context` and `can_create_project -> domain_context` in one operation, so the latter already reused physical reads. The new handler reuses authentication's entire operation; it still runs both semantic checks.
- `/chat/conversations`: `get_token_info`, then proxy `authorize_service_request -> current_service_principal -> get_project_access`. Baseline repeated catalog (two REST calls) and selected-project effective assignments (one). The request operation now supplies the existing exact project rows/catalog. The current source does **not** issue three full accessible-domain resolutions for this route. The production report's 122-call window is not reproduced by this fixture; no production reduction is claimed.
- `get_policy_capabilities` does **not** rebuild an Afterglow principal or accessible domains in this source. `/chat/cloud-tools` calls `current_service_principal` first, then `get_policy_capabilities`, which performs trusted endpoint/catalog transport and a fresh native service HTTP policy read. Ordinary conversations do not call it. Policy results remain uncached; no remote deny is bypassed and no unnecessary new operation parameter was added to policy transport.

## Design and invariants

1. `_sources` computes the same applicable assignment predicate and uses the same original ordered checks. `_accessible_domains` plans applicable group IDs across all projects before that ordered loop, including single-domain inventories not populated by `_warm_exact`'s less-than-two fast path.
2. Speculation mirrors disabled project/domain, identity-only account domain, foreign personal project and projection-source exclusions. Each group task fetches its exact group, then fetches members only if that consumer would not skip the projection. Group rows have no normative enabled policy in the existing resolver; this change preserves that behavior rather than inventing a new one.
3. Each warm-up uses the existing four-worker cap and `run_parallel` drain. Planner/fetch errors are suppressed, never memoized as success. The original sorted project and graph-source passes reread failed reads and report the first applicable error. Dependent ancestor walks and remote policy calls retain their checks and error priority.
4. FastAPI's function-scoped yield dependency owns one `NativeOperation` through authentication and handler execution, then closes/drains it before response streaming. Only capabilities GET and chat paths opt into downstream reuse. Identity mutation handlers, fresh administrator guards, workspace changes and provisioning keep separate fresh operations and existing invalidation fences.
5. Request state binds the operation to exact user/home/working domain/project/JTI/native token/admin identity. A changed owner cannot acquire it. No operation goes in a serialized token dictionary. The service principal's memo identity includes token/domain and operation generation; `invalidate()` clears observations and defeats an earlier principal snapshot.
6. Share the **whole operation**, not a bare `reads` dict. Native client, manager objects and catalog are kept alive for the identity-keyed memo lifetime. `NativeReads.retain` pins managers/catalogs until invalidation/close, preventing a collected object's `id()` from aliasing a different credential's observation. Tests exercise separate credentials, an explicitly replaced manager, `gc.collect()` and owner release.
7. Nothing is shared between HTTP requests. Removing group membership between two authenticated requests removes the formerly visible domain in the second response. No cross-request cache, TTL, schema, setting, native write, role widening or frontend change exists.

The dependency wrapper delegates to the plain `resolve_token_info(..., operation=None)` core. Explicit callers in experience ingestion, interaction ingestion and legacy Palimpsest Hub use that core, not a raw FastAPI `Depends` default. A valid-JWT route test covers direct ingestion. `memo_identity` now retains every manager/catalog before creating its identity key, including canonical domain memo insertion and projection-grant keys.

Follow-up: request-owned dependency teardown drains and closes the operation unconditionally. It clears state and memo, logs failures with a fixed message and sanitized exception traceback, and does not replace an already-committed endpoint response with a cleanup error. Explicit `NativeOperation` context owners retain strict close-error propagation. This changes neither permission checks nor mutation semantics.



## Local measurements

Three runs each, non-administrator, 10 ms artificial delay per directory call; median wall clock:

| Route | Calls before → after | Median ms before → after |
|---|---:|---:|
| `/auth/me` | 41 → 41 | 434.26 → 252.06 |
| `/projects/capabilities` | 79 → 41 | 775.13 → 262.82 |
| `/chat/conversations` | 44 → 41 | 465.50 → 255.49 |

The benchmark runs the same test fixture against detached baseline source and current source. The call-count regression pins all three current routes to 41 physical reads, each distinct native query once. A separate twelve-project/twelve-group fake checks four-way concurrency, group/member phase wall time versus serial pairs, and identical results versus serial `run_parallel`. A separate eight-system-group fake checks its bounded rounds. Targeted and final gate results are recorded in `docs/testing.md` and the completed checklist.

## Administrator chat: distinct mandatory fresh guard

An additional operator-provided read-only production observation correlated one `/api/v1/chat/conversations?limit=20` request with exactly one Afterglow inbound request and one Lumen `/v1/conversations` request. Two samples took 4.73/4.79 s at the client and 4685/4760 ms at Afterglow. One clean window had 101 Afterglow python-keystoneclient calls: role assignments 21, projects 21, group GET 16, group members 14, domains 8, user groups 4, roles 4, role inferences 4, users 3, project lists 2, group lists 2 and auth/tokens GET 2. Three token POSTs and five discovery GETs were separate. No Lumen Keystone user agent appeared in that clean window. This is operator-supplied observation, not an independent local check; 2.86 s is the summed recorded Keystone-call duration, not proof that all remaining time is specifically Lumen processing.

The caller is a system administrator. `get_token_info` leaves system-admin identity set without marking a consumer chat path `_live_system_admin`; `current_service_principal` therefore invokes `require_admin`, which intentionally creates a **second** fresh `NativeOperation`. Within that operation `domain_context`, native token validation and `_is_system_admin` share only their own reads. The separate guard explains the two directory passes in the local admin fake and is consistent with the observed production call shape; the exact production trace did not label source functions, so attribution remains an inference.

The 10 ms fake, same eight groups/twelve project reads and actual chat authentication/authorization as above, yielded one paired sample per subject. Direct system grant: 82→82 directory calls, 747.72→477.21 ms. Group-derived system grant: 84→84 calls, 784.32→510.83 ms; two additional system-group assignment calls are intentional, one per operation. `evidence/admin-measurements.json` gives the full method/argument/caller map. These are local single samples, with synthetic token validation and upstream forwarding, not production timing.

Regression tests demand those 82/84 calls, including two independent user/domain/system-grant reads. Another test revokes direct system grant, system group membership, or selected-project access after request authentication but immediately before the fresh guard. The guard uses a distinct operation, re-reads native data and denies the same request. **No reuse across the `require_admin` boundary is permitted**, including read-only chat GET. A distinct cheaper freshness policy for read-only chat is an option only for an explicit future owner decision; it is not implemented or recommended as a silent optimization here. Native token-exchange authenticity and live Keystone concurrent-state atomicity are not proved by this fake.


## Remaining limits

Keystone/native service load, process scheduling, connection pool contention, token-method POSTs, SDK discovery, real Lumen policy/provider work and browser rendering remain unmeasured after the change. Speculative reads can finish for later inputs before an earlier ordered failure, as with existing `_warm_exact`; no speculative result authorizes an otherwise failing request. Native operations are not transactions over concurrent external IAM changes; this preserves the operation-local observation boundary and next-request revocation freshness, not atomic global snapshots. Production rollout and remeasurement require separate approval.
