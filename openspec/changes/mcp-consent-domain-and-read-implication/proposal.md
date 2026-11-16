# MCP consent domain selection, implied read, and service role tiers

## Why

Owner review (2026-11-17) of the OAuth consent screen after 1.32.22:

- The domain select listed only the other domains. The connected domain was missing and nothing was selected by default.
- Choosing another domain reloaded the whole page and returned to the first step. The owner wants the domain to change in place, in the project/permission area, with only the project list refreshing.
- A project could keep create/update selected without read.
- Drover, Palimpsest and Waygate should give a `member` every capability and a `reader` read-only access. A read-only probe of production (managed member account, roles member+reader, DMSLAB) returned Drover 6 of 6 and Waygate 7 of 7 leaves but only 3 of 5 for Palimpsest: `palimpsest-keys_editor` (`keys:issue`) and `palimpsest-keys_admin` (`keys:revoke`) were manager-only in Palimpsest's own policy ceiling, which operator YAML cannot raise.

## What Changes

1. The consent domain select lists every available domain, adds the connected domain when the session list omits it, and selects it by default. Selecting another domain switches the working domain without a button and refreshes only the project area of the same ticket; the step, duration and client details stay. A failure restores the selection and shows the error.
2. Choosing create or update selects read for that project and keeps it while a write operation stays chosen; the read column toggle skips such projects. The server adds read to any stored write selection (`validate_project_operations`), including saved selections.
3. Palimpsest (separate repo, worktree `palimpsest-wt-member-keys`, not merged or released): `keys:issue` and `keys:revoke` move to the member tier so a member holds all five Palimpsest capabilities and a manager keeps only package/layer/export deletion and project management. Reader is unchanged. Drover and Waygate already match and are unchanged.

## Capabilities

### Added Capabilities

- `mcp-consent-operations`
