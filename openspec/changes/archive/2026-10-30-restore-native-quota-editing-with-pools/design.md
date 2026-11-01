## Context

Stock Nova native project CPU/RAM quota remains authoritative alongside Afterglow GPU/domain caps. domain_quotas still strips cores/ram for any explicit pool and the quota editors hide them. This is an incomplete clean cutover.

## Goals / Non-Goals

Goals: explicit native quota adjustment and future defaults work for unmanaged, active and paused pool domains; native quota remains separate from Afterglow consumption cap; restore full useful UI without requiring pool readiness.
Non-goals: automatic quota enlargement, global domain enforcement, changing pool metadata, new schema, production mutations or unrelated lint reformatting.

## Decisions

- Delete _allocation_values and obsolete _domain_compute_pool usage from domain_quotas rather than retain an identity shim. Native ceilings/defaults/project writes/enable checks cover all native quota fields. Remove unused compute_pool_enabled response coupling if there are no real consumers.
- Native allocation budgets remain the sum of project quota limits, not domain pool usage. Existing explicit saved CPU/RAM ceilings/defaults become visible and applicable again, never silently dropped. Budget/usage/reserved/unknown operation guards stay in place. Defaults apply to disabled new projects before enable as before.
- Remove QuotaEditor.poolManaged, ProjectQuotaForm.poolManaged, DomainBudgetEditor.poolManaged/poolKnown and obsolete parent state/props/readiness coupling. Pool panel remains independently visible; native quota editing needs its own complete snapshot/caller authority, not pool GET success. No deprecated props or aliases.
- Regression must configure a GPU-only domain, observe insufficient native cores/RAM blocking the GPU flavor, update native quota via existing guarded writer, and observe eligibility allowed while GPU policy/cap and ACL remain unchanged. Test future CPU/RAM defaults, native budget denial and paused-pool edit independence.

## Risks / Trade-offs

Old native writer suppression hid stored CPU/RAM budgets/defaults; restoring them can expose existing drift or constrain writes. Do not erase existing values or auto-raise native quotas. Native write uncertainty remains journaled and never replayed automatically. Pool pause can still block VM creation while native quota correction is allowed.
