## Implementation Tasks

- [x] Diagnose SDK delimiter/subdir loss and implicit-folder mutation failures against the installed SDK and read-only Swift fixture.
- [x] Replace SDK object listing with complete raw Swift JSON paging and robust metadata, marker, error and SLO behavior.
- [x] Make recursive move, bulk permanent delete and bulk trash operate only on stored markers and report logical folder success accurately.
- [x] Add failing-before/passing-after storage service and authenticated route regressions for implicit hierarchy, collisions, pagination, encoding, failures, existing markers, SLO and mutations.
- [x] Exercise focused tests, relevant wider test/lint targets and disposable FastAPI → real ObjectBrowser interaction at desktop/tablet/mobile sizes; distinguish live-bucket verification from fixture evidence.
- [x] Update object-storage API docs, changelog and architecture review; stamp/check architecture and archive this change.
- [x] Review follow-up: fail closed on non-2xx raw Swift COPY/PUT/DELETE responses, guard identical/overlapping same-container moves, and prove both through a real openstacksdk Proxy with injected HTTP errors (failing before, passing after).
