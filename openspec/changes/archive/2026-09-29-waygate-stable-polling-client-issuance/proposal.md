# Waygate stable polling and client issuance

## Why

An empty Waygate client or attachment list switches to an animated skeleton on every poll because `clientsLoading` and `attachmentsLoading` are set even after the first response. The refresh icons spin and repeated identical payloads replace the entire reactive list and traffic history. The deployed Waygate API also returns HTTP 422 when client issuance sends the newer `inherit_dns` and `inherit_persistent_keepalive` request fields.

## What Changes

- Keep the initial loading state separate from background polling; after the first response, preserve the visible empty/list state and do not spin refresh controls for automatic reads.
- Reconcile server, client, attachment and network catalog results by stable ID and payload so unchanged rows retain their identity. Preserve stale-response/project isolation and real traffic-aging behavior.
- Omit client inheritance flags on creation: the newer Waygate service infers them from absent DNS/keepalive fields, while the reported deployed service rejects the flags. Continue to send explicit null DNS and zero keepalive overrides. The deployed service version and dynamic server-default inheritance behavior have not been verified; a service rollout remains a separate authorized operation.

## Acceptance

- A previously loaded empty client and attachment section never shows a skeleton or spinning refresh icon during an automatic poll, unchanged responses leave those sections unchanged, and new/updated/deleted entries appear on their next successful poll.
- Initial loads, manual refresh, errors, hidden-tab polling, server/project switches and traffic staleness still behave correctly.
- Creating a client with the default settings emits no unsupported inheritance flags; explicit DNS/keepalive values remain distinct from omitted values.
