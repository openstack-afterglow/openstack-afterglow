## Why

Users should see the same understandable `cpu.{vcpus}c_{ramGiB}g` convention for existing and new CPU flavors. Existing native Nova names cannot be renamed through the standard API without replacing identity; deleting/recreating flavors would affect VM references and ACLs.

## What Changes

- New Afterglow-generated CPU flavors use `cpu.{vcpus}c_{ramGiB}g`; retain deterministic IDs, avoid altering GPU names and never adopt unrelated native names merely on collision.
- Existing CPU flavors retain native IDs, names, immutable shape and existing VM references. Present a separately derived canonical display name in Afterglow while keeping the native name available and using native IDs/names for every authorization, matching and mutation operation.
- Include existing and future manual CPU flavors automatically in Afterglow CPU domain policy and automation, including private-project access reconciliation when safely classifiable; preserve native hardware specs, description and identity. Public Nova flavors cannot be converted in-place to private using the standard API and remain public; Afterglow admission remains subject to domain policy and native quotas, but external Nova clients can bypass Afterglow. Unverifiable devices, ownership, partial catalogs or mutation outcomes are reported rather than guessed.
- Preserve operator-specified native attributes, raw source identity, current claim/lease/revision fences, strict readback, and unknown-write handling; existing VM data and native flavor resources are never deleted.

## Capabilities

### New Capabilities
- Canonical CPU flavor presentation and safe automatic inclusion of existing native CPU flavors.

### Modified Capabilities
- Managed flavor reconciliation and administrator/user CPU flavor lists and selection.

## Impact

- Backend flavor reconciliation, native flavor presentation, API responses, admin and user surfaces, tests, architecture and detailed docs.
- No production deployment, native database edits, direct live Nova mutations, or activation is authorized by implementation. Existing shared writers and shared worktree remain untouched.
