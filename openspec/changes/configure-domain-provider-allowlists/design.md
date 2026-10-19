## Context

The auth registry already supports multiple instances of one kind and the UI uses provider IDs. Selection currently concatenates common and domain `providers` lists, then appends domain SQL providers. The change is server-side selection/enforcement; the public response schema and existing login component remain unchanged. Concurrent WIP, private settings, the shared index and existing runtimes must be preserved.

## Goals / Non-Goals

**Goals:** unrestricted enabled-provider fallback; explicit default/domain allowlists; empty versus omitted distinction; exact domain IDs; no SQL-provider bypass; same-kind independent IDs; correct policy fallback guard and deployment round-trip.

**Non-Goals:** wildcard/name/subdomain matching, new database schema or dependencies, automatic federation provisioning, credential/pinning redesign, UI redesign, deployment or release.

## Decisions

1. `AuthMethods.allow_providers` is optional, defaulting to null internally. A domain's non-null value overrides the default's value. No effective value means unrestricted; `[]` means no provider. Empty domain tables inherit. Reject the old `providers` selector rather than silently interpreting or ignoring it.
2. Entries use the existing file registry key or a canonical lowercase UUID of a SQL IAM provider. Unknown registry keys fail static validation. SQL UUIDs resolve only against enabled configured rows owned by the requested domain; absent/foreign IDs offer no access. Use no new identifier alias or namespace.
3. With no list, keep file registration order followed by the existing SQL sort. With a list, preserve its first-occurrence order across both sources and omit disabled/unavailable entries. Kind and display name are never identity or deduplication keys.
4. Reuse selection in file provider loads and check the same effective allowlist on SQL loads/verification. Existing authorize, callback and refresh consumers therefore reject removed access. SQL usable-provider checks must exclude denied providers, so a hidden provider cannot justify disabling password login.
5. Render only explicitly specified `allow_providers` values in generated TOML. Do not turn an omitted list into `[]`; retain empty lists and empty domain tables. Keep client secrets exclusively in existing Secret env projection. Helm uses the shared renderer.

## Risks / Trade-offs

- All-enabled fallback intentionally broadens availability when no allowlist exists; actual native domain/IdP/protocol and identity mapping still gate login. Operators needing isolation must set an explicit list.
- Old selector fields fail startup/generation; migrate them to complete allowlists, because old additive lists are not equivalent to replacement lists.
- An operator can intentionally configure no external methods, including for a password-disabled domain. Do not silently enable password or another provider. Existing IAM last-method mutations must not count denied SQL providers.
- No live GitLab/Keystone or cluster acceptance is inferred from local SQLite, fakeredis, scripted discovery or browser smoke. Redis discovery-pin durability is unchanged and is not a guarantee made by this change.

## Configuration-only connection contract

Domain selection never branches on a display name, a known domain ID, provider label or GitLab host. Each registry instance carries its own issuer/client and native IdP/protocol; exact-domain allowlists choose instance keys. Multiple instances may intentionally share issuer/application credentials while selecting different native mappings. Returned user domain and optional federation IdP/protocol remain mandatory independent checks; an IdP's fallback domain is not a substitute for the returned identity domain. The frontend continues to render server-returned IDs/names with one generic authorization/callback path. A new supported OIDC or GitHub instance needs configuration, native federation and upstream callback preparation, not a source/image rebuild; cached API/worker settings still require restart. A new wire protocol is not a configurable instance of an existing protocol and needs an explicitly implemented verifier.

