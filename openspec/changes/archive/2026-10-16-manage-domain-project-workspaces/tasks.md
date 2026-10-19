## Implementation Tasks

- [x] Inspect existing identity, enrollment, role, selector, quota and monitoring contracts; record user decisions for owner-only creator deletion, quota-sum budgets and new-users-only personal domains.
- [x] Replace the top-left project dropdown with the shared authorized domain→project resource dialog, preserving session lifetime, identity and stale-response fences.
- [x] Enforce server-side created/joined domain and exact project membership on directory reads and atomic workspace selection; manager sees all domain projects without granting tenant-global system authority.
- [x] Add UUID-keyed user pin, ordering and visibility preferences with hidden-resource recovery and no authorization effect.
- [x] Add explicit native project_creator delegation and safe create/delete UI/API; creator deletion requires sole ownership, Default is immutable and nonempty/unknown projects are blocked.
- [x] Guarantee canonical Default creation and immediate Default project_reader enrollment for signup and both new/existing-user invitation acceptance with durable native-effect recovery.
- [x] Enforce unique explicit project_owner for new projects and explicit ownership transfer; preserve native owner→admin→member→reader, separate manager authority and flag ambiguous legacy ownership.
- [x] Provision personal identity domains only for new human users using the chosen display name, unique native identity and duplicate display-name support; do not move existing users.
- [x] Support same-domain joined-user project invitations/additions for project administrators and email-only domain invitations for managers; protect foreign identity credentials.
- [x] Preserve and complete system:all admin domain/project/group/user/credential observation with exact domain filtering and safe metadata.
- [x] Implement system-admin domain allocation budgets, manager project quotas and future-project defaults, serialize allocation and integrate all first-party project creation/quota writers.
- [x] Move domain switch/create entry points out of the sidebar into the resource dialog while keeping authentication continuation routes functional.
- [x] Add IAM user/project quota and actual usage views plus domain resource monitoring, including truthful unsupported/partial/unavailable and unattributed data.
- [x] Qualify meaningful endpoint regressions and relevant test targets; exercise actual API/SQL/Redis/SDK state transitions and compiled browser paths across four locales, themes and responsive widths. See evidence/verification.json; known outside-scope gate failures remain explicit.
- [x] Build affected canonical backend/frontend images for every declared architecture; deploy to an isolated authorized local target, observe readiness and exercise real runtime paths without production/native-cloud mutations. All nine target/architecture images, dual-architecture 477-assertion native runs and three native supervisors passed; disposable resources were removed.
- [x] Update existing architecture/design/API/testing/changelog evidence, verify architecture guard and archive this completed change with exact scope and remaining verification limits. Scoped working/staged guard passed; no production deployment, release, commit or full-gate-success claim.
