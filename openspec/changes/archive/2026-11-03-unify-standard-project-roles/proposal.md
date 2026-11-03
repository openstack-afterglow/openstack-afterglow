## Why

The user explicitly replaces separate Lumen/Drover/Waygate/Palimpsest grade and leaf-role assignments with the standard project model: member and above create/manage project resources; reader queries/reads only. Separate service roles make manager/system-admin operation and review inefficient. This directive supersedes earlier default service-grade authorization decisions, not ownership/current credential boundaries.

## What Changes

- All four native services evaluate standard core member/manager/admin for project management and reader/member/manager/admin for ordinary visible resource reads, under fresh native role-ID authority. Existing project owner/admin/member/reader hierarchy continues to imply the appropriate core role.
- Remove default service-specific grade/leaf role granting, service-role collision dependencies, assignable role areas and preset seeding. Existing native IDs/assignments remain data; there is no automatic live role or assignment deletion.
- Keep action/capability labels internal and continue native policy capability projection. Afterglow never authorizes by a browser role label or guesses a capability when native checks fail.
- Reader cannot invoke paid chat/generation/tools, publish/mutate/delete resources, mint service keys or issue privileged kubeconfig/VPN access merely because the HTTP operation uses GET. Ordinary visible package/file reads retain existing owner/private visibility.
- Keep genuine human system administration for global provider credentials/statistics/catalog/resource-policy and machine/controller operations. Project member does not become global administrator.
- Preserve exact user/project/private-resource ownership, disabled/revoked membership, original credential/issued-role/API-key ceilings, budget/approval/sandbox/one-send and unknown-I/O fences. Fix actual native human OpenID method recognition only where proved omitted; unknown/delegated credentials remain restricted.
- Synchronize shipped native policy examples/generators/Kolla inputs, IAM UI/guides/locales and meaningful regression coverage. Keep chat progress parity and production federated-admin403 fixes active under their existing change.

## Capabilities

### New Capabilities
None; replace the authorization model of existing project-scoped service workflows.

### Modified Capabilities
Lumen, Drover, Waygate, Palimpsest project authorization; Afterglow IAM/preset UI and native capability consumption.

## Impact

Coordinated source changes span five repositories. Native APIs/workers must receive matching default/operator policy before rollout; existing live overrides may retain old service checks and must be reviewed. Source qualification is not a production activation. No production deployment, role/assignment deletion, schema migration, native resource creation, paid provider call, key replacement, commit/push/version/release is authorized by this change. Parent verifies native standard-role and reduced-credential boundaries, all relevant source gates, actual browser flows and declared image platforms before archive; remaining live rollout prerequisites are explicit.
