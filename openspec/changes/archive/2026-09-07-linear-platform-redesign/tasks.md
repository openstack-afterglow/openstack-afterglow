## Foundation

- [x] Define the neutral dark/light token, typography, spacing, motion, focus, radius, and layer contract in `layout.css`, `tokens.ts`, and `DESIGN.md`.
- [x] Rebuild the existing responsive shell, sidebars, context bar, page shell, page header, main landmarks, skip link, and shared geometry without remounting route children.
- [x] Consolidate shared buttons, cards, tables, status, fields, inputs, selections, alerts, empty/loading states, pagination, and toggles.
- [x] Move Modal, FormModal, ConfirmDialog, SlidePanel, and CmdPalette onto one labelled stacked focus-isolation contract; migrate every caller.
- [x] Add and export ResourceToolbar and keyboard-accessible manually activated Tabs.

## User routes

- [x] Migrate dashboard overview, my-resources, activity, usage, usage-report, and notifications.
- [x] Migrate compute instances, images, keypairs, semantic instance table/rows, and instance full/inspector detail.
- [x] Migrate volumes, backups, snapshots, and volume details.
- [x] Migrate file-storage, snapshots, networks, security-services, manage, details, object buckets, and object browser.
- [x] Migrate database instances, details, and backups.
- [x] Migrate networks, network details, routers, router details, floating IPs, security groups, load balancers, load-balancer details/create, and Waygate.
- [x] Migrate clusters, cluster details, container instances/details, Drover list/details, creation, progress, and lazy detail tabs.
- [x] Migrate secrets, account, project settings, and SettingsModal.
- [x] Migrate topology, observability, and instance console-log full-workspace surfaces.

## Administrator routes

- [x] Migrate the administrator overview.
- [x] Migrate administrator instances, images, flavors, hypervisors, containers, Drover, templates, libraries, and Palimpsest workflow.
- [x] Migrate administrator networks/details, subnets/details, routers, ports, floating IPs, load balancers, and topology.
- [x] Migrate administrator volumes/details, file storage, object storage/browsers, database instances/details.
- [x] Migrate administrator projects/details, users, groups, roles, system administrators, and quotas.
- [x] Migrate administrator services, orphans, secrets, announcements, settings, and Notion.
- [x] Migrate administrator monitoring summary and RabbitMQ, OpenStack, node, MySQL, Memcached, libvirt, HAProxy, etcd, and Ceph embeds.
- [x] Preserve `/create`, legacy detail aliases, topology aliases, security-group alias, `/admin/gpu`, and `/admin/layers` navigation adapter behavior.

## Focused workspaces

- [x] Restyle the VM wizard header, dynamic stepper, steps, choice cards, quota context, scrolling content, and persistent footer.
- [x] Cancel and fence obsolete VM project-scoped transport, lifecycle writes, defaults, preload scheduling, and destroy paths while preserving global request sharing.
- [x] Migrate consumer chat rail, transcript, composer, bubbles, pickers, sources, approvals, settings, tools, responsive overlays, and durable-run behavior.
- [x] Migrate administrator chat providers, models, tools, and statistics while preserving credential and device-authorization behavior.
- [x] Recalibrate the landing page and operations board while preserving Korean copy, brand assets, anchors, scrollspy, and auth-aware destination.
- [x] Unify login, project selection, invitation, OAuth consent/callback, root error, unauthorized, redirecting, hydration, and navigation-adapter entry states.

## Regression proof

- [x] Add real-client same-token A→B→A VM option and quota transport race regressions for user/admin scope, global images, and shared admin metadata.
- [x] Add VM store destroy/reopen lifecycle regression proving obsolete defaults cannot mutate the reopened wizard.
- [x] Add dialog, nested confirmation, inert restoration, non-dismissible, responsive SlidePanel, and focus-return regressions.
- [x] Add Tabs and ActionMenu keyboard/activation/row-propagation regressions.
- [x] Add Field help/error association, invalid state, disabled/restored anchor, input-retention, and semantic table regressions.
- [x] Update intentional semantic DOM assertions and remove old source-string responsive shell tests without repinning CSS snippets.
- [x] Run exact changed tests, design target, frontend unit suite, frontend build/check, and repository `test:gate`.
- [x] Navigate every active route in both themes and verify representative loading, empty, error, success, selection, form, chat, auth, and public states.
- [x] Verify 320, 390×844, 767/768, 834×1112, 1023/1024, and 1440×1000 layouts, keyboard/touch interaction, local overflow, contrast, reduced motion, and console health.

## Cleanup

- [x] Update `DESIGN.md` and `CHANGELOG.md`, remove temporary verification artifacts, complete this checklist, and archive the change with `--skip-specs`.
