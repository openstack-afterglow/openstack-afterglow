## 1. Regression test

- [x] 1.1 Add a new test in `backend/tests/test_cloud_shell_security.py` admitting egress-only rules with native `tags`, and rejecting malformed `tags` values and tagged ingress/unknown-field rules.
- [x] 1.2 Run the new test selector and confirm it fails before the source change (3 failed on `tags` rejection, before the change).

## 2. Validator

- [x] 2.1 Add `tags` to `allowed_fields` in `validate_security_group` and type-check it as a list of strings.
- [x] 2.2 Re-run the new test and confirm it passes; re-run all of `test_cloud_shell_security.py` and `test_cloud_shell.py` (124 passed).

## 3. Evidence and docs

- [x] 3.1 Re-validate the captured production rule shapes offline (egress-only subset ACCEPTED; full production `default` group REJECTED because of ingress).
- [x] 3.2 Update `docs/api/cloud-shell.md` security group section to state that native `tags` metadata is accepted and that the configured group must still be ingress-free.
- [x] 3.3 Run ruff check/format on changed backend files.
- [x] 3.4 Update `docs/testing.md` with the verification evidence and remaining operator prerequisite.

## Operator prerequisite (not a task of this change)

The dedicated Cloud Shell project must provide an ingress-free, project-owned egress-only security group selected by `security_group`. This change does not create, modify, or select any OpenStack resource, and does not deploy the image.
