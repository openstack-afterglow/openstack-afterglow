## Implementation Tasks

- [ ] Add project-scoped quota and attached-instance read endpoints and rule target/default behavior; cover owner boundaries, quota failures, port membership and rule semantics in backend tests.
- [x] Update user screen with quota, selected-group instance usage, project-safe refreshing, in-table rule form, per-rule IPv4/IPv6 column, remote SG selection and explicit remove/recreate edit path.
- [ ] Extend admin project quota GET/PUT for additional Nova/Cinder fields and all requested Neutron/Manila fields, with no fabricated usage, admin guard, strict optional limits, partial-write reporting and backend regression tests.
- [ ] Extend admin quota UI with independent supported-field compute, volume, network and Manila section saves, project fencing, clear unavailability/error feedback and meaningful frontend tests; retain GPU workflow.
- [ ] Run focused backend and frontend checks plus runtime UI/API smoke at mobile/tablet/desktop; distinguish local from live evidence.
- [ ] Update API and architecture documentation and changelog; stamp architecture after reviewing source and run available architecture checks without touching unrelated staged changes.
