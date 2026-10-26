# Hide private manager projection groups

## Problem
The system-admin group inventory exposes reserved `afterglow-default-managers-*` / `afterglow:default-manager-reader:v1:*` groups as ordinary mutable groups. Its delete button reaches the intentional403 `domain_manager_projection_is_private` guard. These groups maintain domain-manager reader access; deleting them is not a safe bugfix.

## Change
Apply the existing canonical projection predicate to inventory responses before creation-event enrichment, including previously cached inventory. Keep ordinary groups, native domain scoping, ordering and all backend mutation guards unchanged. No new frontend contract or translated text is required because private groups are absent from the existing list response.

## Acceptance
- Name-only and marker-only reserved groups are omitted on fresh, warm and legacy-warm cache reads.
- Ordinary same-domain groups remain visible and deletable when existing authority safeguards allow deletion.
- A direct deletion attempt for a private projection remains403 and makes no native mutation.
- Exercise actual HTTP and the compiled administrator group surface with synthetic identity/provider state; do not delete or mutate any operational group.

## Scope
Backend group-list projection and focused regressions/docs only. No deployment, schema, settings, native IAM mutation or shared-branch/index manipulation.
