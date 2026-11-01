## Why

A normal in-place Keystone session-token renewal changes the stored root token but not the authenticated login family or workspace. GPU quota request fences currently treat the token bytes as a session-generation change and return 401, which can unnecessarily trigger frontend auth recovery.

## What Changes

- Fence stable session identity, workspace/scope generation and provider binding without using the renewable native-token bytes as an identity.
- Continue requiring a present valid session record and independent fresh native subject/role authorization; fail closed for deleted, blacklisted, malformed or scope-changed sessions.
- Exercise real session-store token CAS during GPU request creation, listing and administrator review, with no quota mutation and no production DB/cloud operations.

## Impact

Backend GPU request session fence, endpoint regressions, architecture/testing/changelog. No migration, UI contract change or deployment.
