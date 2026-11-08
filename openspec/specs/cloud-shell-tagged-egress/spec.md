# cloud-shell-tagged-egress Specification

## Purpose
TBD - created by archiving change fix-cloud-shell-tagged-egress-rules. Update Purpose after archive.
## Requirements
### Requirement: Native rule tags are accepted metadata

The Cloud Shell security group admission check SHALL accept the Neutron `tags` metadata field on security group rules when its value is a list of strings. Tags SHALL NOT affect admission decisions.

#### Scenario: Egress-only rules carrying empty native tags are admitted
- **WHEN** the configured security group contains only egress rules whose `tags` is `[]` and whose other fields satisfy the existing egress rules
- **THEN** the group is admitted by the security group check

#### Scenario: Malformed tags are rejected
- **WHEN** a rule's `tags` is a string, a dict, a number, or a list containing a non-string
- **THEN** the security group check raises a `CloudShellSecurityError`

### Requirement: Tagged rules keep every existing isolation check

A rule that carries `tags` SHALL still be rejected when it is an ingress rule, references a remote group or address group, belongs to another security group, or contains any field outside the known allowlist.

#### Scenario: Tagged ingress rule is rejected
- **WHEN** a rule has `direction` set to `ingress` and a list of tags
- **THEN** the security group check raises a `CloudShellSecurityError`

#### Scenario: Unknown field next to tags is rejected
- **WHEN** a rule has a non-empty `tags` list and an unknown field such as `unknown_remote_policy`
- **THEN** the security group check raises a `CloudShellSecurityError`

