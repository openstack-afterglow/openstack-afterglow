## Context

The existing ResponsiveTable switches between desktop tables and compact cards at1024px. Shared TableShell defaults to intrinsic minimum width; project instances need fixed column allocation. The prior action column was48px although padding plus its36px trigger required68px.

## Goals / Non-Goals

**Goals:** Complete all four requested instance-list UI changes with equivalent compact keyboard access and nine-locale labels.

**Non-Goals:** Changing global table primitives, administrator lists, permissions, API responses, cloud state or backup behavior.

## Decisions

- Use a64rem minimum fixed table and an80px action column; keep honest inner scrolling only below that usable content width instead of hiding overflow or actions.
- Allocate remaining width to identity/image; wrap addresses and library tags in their cells. Existing detail disclosure preserves full resource identity.
- Sort a copied full-project snapshot before paging. Localized visible status/strategy values, natural numeric collation, newest-first ties and empty-last order avoid raw-code surprises.
- Header buttons carry aria-sort through their column; compact44px controls carry aria-pressed/current direction. Both invoke one three-state controller.
- Group page size and Pagination in one footer flex group. Place tutorial and VM creation together in PageHeader.

## Risks / Trade-offs

- Narrow desktop workspaces retain inner table scrolling, while tablet/mobile use existing cards. This is not a promise to fit arbitrary dense tables at every width.
- Browser fixtures are synthetic; they prove rendered interaction and geometry, not OpenStack readiness.
