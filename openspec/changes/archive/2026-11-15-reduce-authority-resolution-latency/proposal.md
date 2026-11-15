# Reduce authority resolution latency

## Goal

Reduce authenticated request latency without a cross-request authority cache, stale revocation, new privileges, or changes to ordered failure reporting. Production observations are the external report `~/.local/share/afterglow-proofs/perf-20261114/REPORT.md`; local synthetic measurements are not production acceptance.

## Scope

- Warm independent applicable group and membership reads across the full accessible-project set with at most four workers.
- Preserve project/domain/source checks, projection exclusions, personal-project rules and ordered error reporting.
- Share one `NativeOperation` (client, catalog and read memo) through authenticated capabilities and chat authorization; never share bare manager-ID dictionaries between clients.
- Retain identity-keyed memo owners until invalidation or operation close. Keep independent mutation and system-administrator guards fresh.
- Add endpoint call-count/timing, cross-request revocation, warm-up failure-order and credential-isolation tests.

No frontend, schema, SQL, config, production mutation, release or deployment changes.
