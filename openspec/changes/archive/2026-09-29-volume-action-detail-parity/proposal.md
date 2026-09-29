# Volume action parity in detail

## Why

The volume-list overflow menu offers boot-from-volume, extend, snapshot, backup, transfer, delete and administrator force-delete actions. The shared list SlidePanel and direct `/dashboard/volumes/[id]` detail render only connect, rename and delete, leaving most operations unreachable after entering detail.

## What Changes

Share the list's operation menu and eligibility rules with both detail surfaces. Keep list navigation as the list's `연결` action and present instance attachment in detail when available. Reuse existing operation modals and the VM wizard rather than introduce API routes. Preserve snapshot feature gating, status restrictions, attached-volume deletion guard and administrator-only force deletion. After a successful mutation, refresh detail and any open list; deletion leaves the detail surface, while accepting an unrelated transfer refreshes the current detail. Clear modal targets on volume/project switch.

## Acceptance

- The list SlidePanel and directly loaded detail offer the list operations with the same current-status and role conditions; bootable available volumes can open the VM wizard from either surface.
- Extend, snapshot, backup and transfer open the existing working dialogs for the currently displayed volume; refresh or close follows successful operations according to the existing dialog behavior. Errors stay visible in the dialogs.
- Normal deletion is disabled for attached volumes; force deletion appears only for a system administrator on error/deleting states. Snapshot gating is preserved.
- Responsive detail actions remain reachable without overflowing mobile panels. A focused UI test covers both availability and real modal/wizard dispatch; local runtime smoke exercises a detail route without claiming a live OpenStack mutation.
