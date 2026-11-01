# Resource composition contract

Canonical working contract: local://flavor-composer-contract.md. CPU1–128 integer; RAM1–2048GiB in1GiB steps; optional one approved GPU profile and exact integer count bounded by same-host primary/companion and numbered-group16. Existing hardware UUID construction is shared by standard and custom requests. Names are presentation, never identity.

## Boundaries
- GET options varies one coordinate at a time and evaluates a batch using existing quota/pool/capacity logic, sharing a fresh native capacity snapshot. No Cartesian product or native resource writes on GET.
- POST validates caller/target live authority and existing enabled policy, uses a configured verified native administrator executor only for narrow publication, positively reads exact specs/access and records caller-project history. Personal native member tokens cannot mutate stock Nova flavor metadata; they still own target visibility/quota reads.
- Existing RuntimeSetting managed state adds private validated scalar custom intents and bounded caller/home/project history. No DDL. Native+SQL+Redis are not a single transaction; dispatched unknown never blindly replays. Periodic reconciliation regenerates custom intents under current retained hosts/approved specs and only accepts exact same UUID.
- Browser stores safe coordinates/mode/selected reference only, keyed by immutable user/home/effective target/surface. Every restore revalidates; passwords/cloud-init/usage consent are never persisted. Logical authority changes fence pending responses, ordinary bearer renewal preserves safe draft.

## Acceptance
Same-host crossed CPU/RAM/GPU limits, non-power-of-two CPU/GPU counts, transient usage shrink, missing AZ/quota/capacity, zero vs unknown, saved UUID reuse/native-name stability, private history and reader/foreign/revoked fences, nonreplay, reload/navigation/reset/scope persistence. Actual isolated HTTP+SDK+SQL+Redis ownership and Chromium source/build checks are separate from native login/live scheduling/deployment. Old/new writers mixed execution unsupported.
