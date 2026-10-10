## Context

Inbound MCP already has read/manage scopes and one project-fixed Keystone application credential per grant. Lumen freezes opaque selected-grant snapshots and revalidates them before cloud dispatch. The shared dev working tree includes prior auth/MCP hardening and must be preserved.

## Goals / Non-Goals

**Goals:** default per-user Lumen resource inspection; explicit personal/OAuth access and project consent; identical closed registry; durable revocation/project fences; no secret leakage.

**Non-Goals:** production deployment/IAM edits; provider/model changes; arbitrary new cloud APIs; dynamically delegating future projects; sibling source imports or shared user credentials.

## Decisions

1. Keep the issuance/home project and existing primary credential. Add immutable allowed-project metadata and project-specific restricted credentials for additional selected projects. Existing grants are single-project. MCP tools accept optional `project_id`; omit it to use the home project. Expose an authenticated project-list tool. Resolve the target before parsing/preview/ledger/dispatch and reject targets outside the saved set. Every credential authenticates as the same owner and exact target. Keep lock/cleanup/idempotency semantics; target project enters canonical invocation arguments so reusing a mutation key across projects conflicts.
2. Both create-token and approve-consent bodies carry `access_level: read|manage`, `project_scope: selected|all`, and `project_ids: string[]`. Default selected current project; `all` resolves the current enabled user-accessible list server-side. OAuth consent can attenuate a write request to read but cannot elevate a read-only client request. Code/access/refresh scopes use the approved scope, never the original request after consent.
3. Add GET `/api/v1/auth/mcp-projects` returning `{id,name}[]` from the caller's actual Keystone memberships. No admin-all inventory shortcut. Revalidate each project by caller-token rescope before creating its credential; read-role members cannot acquire management credentials.
4. Add server-only grant source `lumen` with no externally usable personal token. On authenticated native text completion admission, when MCP and tool mode are enabled and the Lumen tools capability is authorized, lazily ensure a user/current-project read grant and select it only when no dispatchable explicit personal selection exists. Existing selection generation and grant epoch still fence paused runs. The internal workload token is bridge authentication only, never cloud resource authority. The parent integration owner implements this default-grant path and BFF; the external grant owner implements external multi-project authority.
5. Compose existing Field/input/Card/Button/Alert primitives for access/project choices in token and OAuth UI. Defaults remain read/current project; show immutable saved projects and access in listings. Reuse the Tools menu for a built-in cloud entry with current-project/read-only description; it is not a custom HTTP tool ID. Default tools follow the existing tool policy and model/service gates.

## Risks / Trade-offs

- One credential per approved project costs Keystone calls at issuance, but project-fixed credentials prevent rescope escalation and no admin secret is needed. Partial/ambiguous creation remains nondispatchable and cleanup tracks every created credential.
- All-project scope is a frozen snapshot; users must issue/approve a new connection to add projects. This avoids silent privilege expansion.
- Default read grant creation can fail on Keystone/DB errors; return a truthful failure instead of claiming cloud tools are available.
- Runtime proof must distinguish real MCP/BFF/plugin/SDK execution from synthetic identity/cloud/provider fixtures. No production resource mutation.
