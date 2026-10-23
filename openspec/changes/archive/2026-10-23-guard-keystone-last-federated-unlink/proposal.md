## Why
Installed Keystone Manager._update_user_with_federated_objects ignores falsy federated arrays, while API schema requires at least one protocol in each nonempty IdP object. PATCH federated=[] cannot remove the last native association. Prior synthetic users.update overwrote the list and falsely accepted last-tuple transfer.

## What Changes
Mirror deployed falsy federation semantics in the native test double. Refuse a source transfer that would remove its last native federation object before journal/native writes, retaining a clear native_binding_conflict requiring an operator-native unlink step. Guard compensation snapshots with empty federation before either metadata field is written. Keep nonempty replacement and ordinary Accounts attach/create unchanged; never add dummy bindings, change mapping or delete users to force an unlink. Correct docs and prior evidence boundaries.

## Acceptance
Single-source-tuple connect/create performs no native/journal mutation, no token/session; failed compensation cannot strip stable metadata while leaving native tuple. Existing nonempty transfer and normal Accounts entry regressions pass. Run actual installed Keystone replacement method against isolated stubs to demonstrate [] no-op without native mutation. No operational change or deployment.
