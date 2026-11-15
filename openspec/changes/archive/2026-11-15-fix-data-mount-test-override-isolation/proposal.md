# Isolate data-mount test dependency overrides

## Goal and scope

Fix the demonstrated backend gate blocker without changing application behavior. Parent explicitly approved changing only `backend/tests/test_instances_data_mounts.py`, plus its own documentation and verification receipt. Keep this test-only fix distinct from the dashboard visual changes.

## Evidence

On the unchanged backend at `1b902c1d`, the isolated canonical gate produced15023 passed/106 skipped and one failure: `test_auth_security.py::test_protected_endpoints_without_token` returned503 instead of401 after data-mount cases on the same worker.

A deterministic single-process regression, without xdist:

```sh
cd backend
uv run python -m pytest 'tests/test_instances_data_mounts.py::test_get_reports_provider_rule_state_not_guest_mount_state_and_no_secret[active]' tests/test_auth_security.py::test_protected_endpoints_without_token -q --setup-show
```

Before the fix:1passed/1failed. The victim alone passes. `--setup-show` demonstrates `monkeypatch` setup before `client`, then `client` teardown/clear before `monkeypatch` teardown. `monkeypatch.setitem` consequently reinserted the client's previous token override after the fixture had cleared the global dictionary.

## Change

Replace the three token-override `monkeypatch.setitem` sites with a snapshot of `app.dependency_overrides`, direct assignment inside `try`, and `finally: clear(); update(previous)`. Assert response behavior after restoration. Remove unused explicit monkeypatch parameters. Keep fixture setup, authority assertions, API and native behavior unchanged; do not weaken the victim or retry away the failure.

## Verification

The same ordered pair now passes2tests with the same fixture order. The full data-mount and auth-security files pass140tests in one process; the changed file passes Ruff check and format-check. Run the complete isolated canonical gate over the combined branch before committing. No production request, schema, dependency, credential or native policy change.
