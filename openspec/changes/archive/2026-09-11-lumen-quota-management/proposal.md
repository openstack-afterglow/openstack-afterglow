## Why

Afterglow exposes Lumen chat usage and API keys, but users cannot rename keys or set per-key weekly/monthly credit limits, administrators cannot manage per-user Lumen quotas, and chat settings still live in a modal that cannot be linked directly.

## What Changes

- Add a dedicated `/dashboard/chat/settings?section=…` route and remove the settings overlay contract.
- Add API-key rename and owner weekly/monthly limit controls within the user's Lumen quota ceilings.
- Add `/admin/chat/quotas`, merging Keystone users with Lumen quota records for monthly and ISO-week limits.
- Extend frontend usage/key contracts and BFF proxy contract coverage for the new Lumen endpoints.

## Capabilities

### New Capabilities
- Linkable chat settings sections for usage, API keys, memory, MCP, tools, and skills.
- User-managed API-key names and weekly/monthly credit limits.
- Administrator-managed Lumen user quotas.

### Modified Capabilities
- Chat usage surfaces include ISO-week credited usage and quota data.
- Settings navigation now changes routes instead of opening a modal.

## Impact

The frontend consumes new fields and endpoints supplied by Lumen through the existing generic `/api/v1/chat` BFF proxy. No Afterglow backend route is added. Existing token/project forwarding and admin layout authorization remain authoritative.
