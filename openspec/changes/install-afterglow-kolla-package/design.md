## Context

Sibling root distributions install Kolla roles as wheel shared-data. Afterglow currently requires a checkout-linked role and aggregate playbook; stock Kolla does not automatically discover custom roles.

## Goals / Non-Goals

An installed Afterglow distribution owns Kolla assets and upgrades them with the package. Preserve explicit Kolla integration wiring and operator configuration. Do not deploy, bump a version, or claim a package release.

## Decisions

Use exactly the `afterglow-kolla` distribution and retain the private `share/afterglow/kolla` asset directory. This source package is unpublished; neither a matching public-index release nor a containing immutable release tag is assumed. Install reviewed source/wheel artifacts explicitly with pip or uv. The installer links the Kolla role and aggregate playbook to the package directory and retains stock-site import wiring. Installing the wheel cannot write through existing source symlinks; the installer migrates only exact identified legacy targets. Independent absolute `AFTERGLOW_LEGACY_ROLE_TARGET` and `AFTERGLOW_LEGACY_SITE_TARGET` values authorize role/site links from different legacy checkout roots; each missing override falls back to its expected path under `AFTERGLOW_REPO_DIR`. Both links are preflighted before either is changed. Unknown links and foreign content fail closed. Kolla reinstall may require re-establishing its stock-site import.
The retired `openstack-afterglow` distribution shares the private asset files and must not coexist with `afterglow-kolla`. If installed, explicitly uninstall the old name before installing the new artifact; if both already coexist, uninstall the old name and force-reinstall the reviewed new artifact before registration or Kolla execution. The installer refuses legacy metadata and does not automatically uninstall packages or delete source checkouts, operator configuration or unrelated data. Stable package links may temporarily dangle during this migration. No production installation of the retired distribution or operational migration is assumed.
Require `AFTERGLOW_OPERATOR_LOCK` to identify the reviewed lock actually used for synchronization; the wheel's bundled snapshot may lag independent sibling promotions and is not an authority.

## Risks / Trade-offs

Package updates are not service deployment. Initial wiring and exact legacy link migration require the installer; installed links subsequently follow package upgrades. Installed assets and operator defaults must not be sourced from an unrelated checkout or stale wheel. The operator lock cannot refer to an unpublished artifact and remains separate until release promotion.
