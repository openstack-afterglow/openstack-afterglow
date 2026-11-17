# MCP catalog dashboard

## Purpose
Expose Lumen's registry-backed remote MCP connections and managed sandbox profiles in the existing chat settings/tools surface. Preserve custom HTTP tools, skills, global administrator publication, and the separate Afterglow cloud delegation consent.

## Contract
Browser `/api/v1/chat/*` reaches Lumen `/v1/*` through the authenticated BFF. Lumen owns current native domain membership, exact-domain manager authority, credential encryption and configuration-version activation. UI uses `mcp-settings.domain_id` and `can_manage_domain`, never auth-store manager claims. Every mutation remains server-authorized.

## Requirements
- Browse/search the complete paginated registry with featured GitHub/Notion and managed Playwright/Markitdown.
- Separate personal, organization and global connection state. Organization/global activation sends the displayed `config_version`. Personal rows need no activation consent: owner publication plus connected credentials makes them effective, and the owner's publication toggle uses the scoped connection PATCH.
- Exact-domain managers create, change, revoke OAuth and delete organization connections. Members only inspect secret-free state and change their own activation.
- Secret drafts exist only in memory, clear before dispatch and on owner change/unmount, and never appear in returned rows or storage.
- Fence every read, mutation, confirmation and OAuth redirect across logical owner, domain, project, readiness and unmount changes.
- Keep errors attached to their own row; distinguish loading, empty, failed, stale activation and managed-unavailable.
- Preserve administrator registry installation and existing MCP/custom-tool/skill controls.

## Evidence
Focused frontend/BFF tests and local desktop/mobile tutorial captures are required. Real local BFF-to-Lumen smoke uses synthetic identity/provider when the companion source is runnable. Source/local checks do not imply production acceptance. Shared architecture/design/testing/changelog proposals belong in `local://mcp-catalog-ui-notes.md` for coordinator integration.
