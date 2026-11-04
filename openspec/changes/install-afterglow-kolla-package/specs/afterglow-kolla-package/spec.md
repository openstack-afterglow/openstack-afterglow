## ADDED Requirements

### Requirement: Package-owned Kolla integration

The installable `afterglow-kolla` distribution SHALL include its Kolla role and integration assets under the unchanged `share/afterglow/kolla` path, and installing an upgrade SHALL update those installed assets. Documentation SHALL distinguish reviewed local source/wheel installation from package publication and service rollout.

#### Scenario: Package install and upgrade
- **WHEN** an operator installs and upgrades the `afterglow-kolla` distribution in the Kolla environment
- **THEN** Kolla integration uses the installed package's role and playbook rather than a source checkout

#### Scenario: Existing checkout-linked role
- **WHEN** the legacy role path points to an explicitly identified Afterglow checkout
- **THEN** migration prevents the package installer from writing through that link and preserves the checkout

#### Scenario: Independently identified legacy checkouts
- **WHEN** the role and aggregate-playbook symlinks have different legacy checkout roots
- **THEN** the operator can identify their complete absolute target texts independently using `AFTERGLOW_LEGACY_ROLE_TARGET` and `AFTERGLOW_LEGACY_SITE_TARGET`, each overriding only its own `AFTERGLOW_REPO_DIR` fallback, and migration preflights both links before changing either

#### Scenario: Retired distribution installed
- **WHEN** the environment still contains `openstack-afterglow` distribution metadata
- **THEN** the integration installer refuses wiring changes and instructs explicit removal of the retired distribution followed by installation/reinstallation of the reviewed `afterglow-kolla` artifact, without deleting legacy source checkouts, configuration or unrelated assets
- **AND** operators must not co-install both names or run Kolla between old-package removal and new-package reinstallation/registration because both distributions own the same private files

#### Scenario: Unexpected target
- **WHEN** an existing integration target is not recognized as owned
- **THEN** migration refuses to replace or remove it

#### Scenario: Stock Kolla installation
- **WHEN** Kolla's stock site has not been wired or was reinstalled
- **THEN** the operator must establish the additive integration import before stock Kolla commands run Afterglow
