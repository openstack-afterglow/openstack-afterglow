## Why

Nova public/private controls tenant API access, but it does not express whether a service or infrastructure flavor belongs in Afterglow's end-user creation experience. Public service flavors such as Amphora or Manila helpers currently appear beside user VM flavors and create noise or unsafe choices.

## What Changes

- Add an administrator-controlled Afterglow frontend visibility flag for every flavor, independent of Nova public/private access.
- Persist the flag as a namespaced Nova flavor extra spec so no Afterglow database migration is required.
- Default existing flavors to visible for backward compatibility; explicitly hidden flavors are omitted from ordinary Afterglow flavor discovery.
- Keep all flavors visible in administrator flavor management and preserve administrator target-project operations.
- Complete project-switch request generation isolation so rapid A→B→A changes cannot strand the VM wizard with stale or permanently loading options.

## Capabilities

### New Capabilities

- Administrators can show or hide a flavor from ordinary Afterglow VM, resize, and K3s selectors without changing Nova access.

### Modified Capabilities

- User flavor discovery excludes flavors marked `afterglow:frontend_visible=false` before quota eligibility evaluation.
- VM creation option loading remains project-consistent across repeated rapid project changes.

## Impact

Backend admin and user flavor APIs, flavor eligibility metadata handling, administrator flavor management UI, VM option-loading tests, and API documentation. Direct Nova API visibility and Flavor Access remain unchanged.
