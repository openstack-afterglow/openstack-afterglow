# Preserve legacy Lumen connections during local deployment

## Goal and approved scope
The user requires existing connections to survive and a real local deployment against the same DB as Kolla. The user explicitly selected a legacy-compatible phase first: keep Kolla0.6.9 unchanged, limit new multi-account/credential functionality until a coordinated Kolla transition, then deploy locally. Existing migrations must not be blindly rerun.

## Evidence and decision
The user-issued Compose run applied provider-account migration027 to shared `lumen_kolla`. Read-only inspection of deployed Kolla0.6.9 proves it still uses legacy provider-row credentials. Six credential rows preserve five encrypted API keys, but the old provider fields are all empty. The auth-attempt primary-key transition is also incompatible with old writers. Current development source is therefore not a safe mixed-version rollout.

Use the exact existing Kolla source revision `6ca10eed3f33497496d04ee7434dbeae06dffe30` for the local compatibility cohort, built through the canonical Lumen Dockerfile. Preserve the current development checkout and its future account-runtime work. Restore legacy-owned connection fields and old auth-attempt write compatibility through a reviewed, backup/restore-tested bounded operation; retain new account/credential data and original migration history, never decrypt/export/reset provider credentials or guess an owner. The legacy stores remain authoritative during this phase; later account promotion requires an explicit stopped-writer reconciliation and schema transition, not automatic fallback.

Add an explicit canonical development build-context override for the pinned compatibility source and gate new account controls on the native provider contract, not guessed version numbers. Existing provider creation/editing/auth flows remain available. Preserve DB/Redis/checkpointer targets, encryption/signing/service keys, mounts, IDs, project/user identities and resources.

## Completion criteria
Protected recovery point restored on matching MariaDB; exact target repair rehearsed and preservation checked. Legacy provider auth and auth-attempt writes verified without paid inference. API/worker images built and executed for arm64/amd64, actual local canonical Compose deployment and existing Afterglow backend/frontend started without rerunning migration jobs. Actual health/readiness, non-mutating authenticated metadata and browser flow observed. Existing Kolla container IDs/images remain unchanged. Source gates, architecture/docs/changelog, diagnostics and remaining real-provider/OAuth limitations recorded before archive.
