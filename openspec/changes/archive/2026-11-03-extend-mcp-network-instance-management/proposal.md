## Why

MCP has bounded network/subnet reads/deletes and one new-network VM attach, but lacks network/subnet/port CRUD, existing-port attach/detach, interface security groups, and instance-volume lifecycle. Users must not bypass MCP with administrative CLI credentials.

## What Changes

- Add network create/update, subnet create/update, port list/get/create/update/delete; preserve existing reads/deletes.
- Add owned existing-port VM interface attach/detach and per-interface exact-project security-group replacement; add group list/get discovery. Existing vm_network_attach remains new-port-on-network path.
- Add Cinder volume name/description update, offline grow, Nova volume attach/detach; retain existing create/read/delete and snapshot/backup tools.
- Reuse issued/current/saved-role intersection, target can_write, strict schemas, mutation preview, durable idempotency, bounded SDK deadlines, final ownership/state revalidation and unknown outcome no-replay. No arbitrary native dictionaries or credential exposure.
- Forbid provider/shared network/subnet edits, infrastructure/bound port direct mutation/deletion, foreign resources, boot/multiattach/force volume detach. Security groups are exact-owned IDs; no port-security disabling. Ports on an explicitly shared network can be owned and attached, without mutating its network/subnets.

## Capabilities

### New Capabilities
- Network/subnet/port lifecycle through MCP.
- VM existing-interface lifecycle and per-interface security groups.
- VM data-volume lifecycle and offline volume growth.

### Modified Capabilities
- Canonical registry discovery/version and documented safe resource schemas.

## Impact

Source/local only, preserve concurrent dev WIP/index. No new REST endpoint, UI, schema, dependency, configuration or deployment. Real installed SDK/local native HTTP and actual MCP transport smoke are required; native authority/resources remain synthetic, not live cloud acceptance. Run focused behavior tests then canonical whole gate; distinguish concurrent shared failures from owned-overlay qualification. Update architecture/API/security/testing/changelog; archive rapid change after completion.
