## Context

`validate_security_group` in `backend/app/services/cloud_shell_security.py` admits a Cloud Shell security group only when every rule is a known, project-owned egress rule. Its field allowlist (`allowed_fields`) omits Neutron's `tags` metadata. The OpenStack SDK returns `tags` on every security group rule (for example `tags: []`), so an otherwise egress-only group is rejected as "must contain only known egress rules".

Live read-only inspection on 2026-11-08 of the configured group `58c3309c-…` (`default`, service project) found 4 rules: 2 self-referencing ingress rules (IPv4/IPv6, `remote_group_id` = the group) and 2 egress rules. The egress rules fail only on `tags`. With `tags` removed in memory, the egress subset is accepted. The ingress rules are a separate, independent blocker.

## Goals / Non-Goals

**Goals**
- Accept native `tags` metadata on security group rules when it is a list of strings.
- Keep every existing fail-closed check (direction, ownership, lateral remote groups, unknown fields, port/prefix shape) unchanged.
- Keep a regression test that fails before the change and passes after.

**Non-Goals**
- No change to the production `default` group, Neutron rules, Kolla precheck, or deployment configuration.
- No new bypass for ingress or self-referencing rules, and no fallback to the `default` group.
- Tags have no authorization meaning and are not used for policy decisions.

## Decisions

1. **Add `tags` to `allowed_fields` and type-check it.** A `tags` value must be a list of `str`; anything else (string, dict, list with non-strings, None) raises `CloudShellSecurityError`. Rationale: an allowlist entry without a type check would let arbitrary metadata shapes through the admission boundary.
2. **Do not add `tags` to `required_fields`.** Older or differently-shaped native responses that omit `tags` remain accepted only if other required fields exist; absence is not treated as an error because it carries no policy. [INFERENCE: SDK/Neutron always returns it; this keeps behavior unchanged for dict fixtures that omit it.]
3. **No change in the Kolla precheck or docs-driven operator steps.** The Kolla precheck checks ownership only; the runtime validator remains the single admission gate, so there is no second copy of the allowlist to update (grep: `allowed_fields` / `validate_security_group` appear only in `cloud_shell_security.py` and its tests).

## Risks / Trade-offs

- Accepting a new field widens the allowlist. Mitigation: only `tags` is added, with type enforcement and a test that unknown fields are still rejected.
- Passing this validator does not make production Cloud Shell ready. The configured `default` group still has ingress rules; the operator must provision a dedicated egress-only group in the service project. This is documented, not worked around.

## Verification Plan

- Regression test (new function, not an edit of existing tests) that fails before the code change and passes after.
- Full `backend/tests/test_cloud_shell_security.py` and `backend/tests/test_cloud_shell.py` runs.
- Ruff check/format on changed backend files.
- Offline re-validation of the captured production rule shapes with the fixed validator, recorded as evidence.
