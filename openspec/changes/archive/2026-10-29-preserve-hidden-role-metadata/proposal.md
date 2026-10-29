## Why

A delayed consumer-contract review of hide-native-admin-role-choices found two side effects: direct-role labels used the grantable catalog and therefore fell back to UUIDs after admin removal, and the hidden-admin descendant workaround overloaded external_role_ids, which must describe group/domain inheritance only.

## What Changes

- Keep native admin absent from every assignment choice and keep all existing grant denial rules.
- Publish exact read-only direct-role metadata (`direct_roles`: id, name, transitive inherited_role_ids) on member observations. Use that metadata for direct-role labels and for the editor's inherited projection, never as selectable roles.
- Restore external_role_ids to group/domain-inherited provenance only and remove the hidden-admin-specific overload.
- Migrate real consumers, new-member drafts and synthetic fixtures to the direct metadata contract; preserve current IDs, hidden grants and graph overlap semantics.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

Member read-only role metadata no longer depends on the assignable-role catalog. Generic role assignment remains unable to grant native admin.

## Impact

Existing project/IAM member JSON, frontend member types, shared editor/direct-role display and their mocks/tests, architecture and API documentation. No new route, database, configuration, permission or live grant changes. Local fixture verification only.
