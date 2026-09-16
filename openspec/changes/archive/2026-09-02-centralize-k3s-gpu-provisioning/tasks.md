## Implementation Tasks

- [x] Add the Afterglow service credential setting, secret-only K8s rendering, and fail-closed internal K3s GPU admission dependency.
- [x] Add the internal admission endpoint that resolves a flavor with the project-scoped administrative connection and calls Afterglow's existing GPU quota authority.
- [x] Add Afterglow unit and API contract tests for credential rejection, quota denial, unavailable authority, and non-GPU flavor admission.
- [x] Add the matching Drover service credential/client configuration and invoke Afterglow admission before GPU Stampede job persistence.
- [x] Correct Drover's local K3s capacity-only PCI classification and record quota-denied/unavailable scale-up blockers without creating jobs or VMs.
- [x] Add focused Drover Stampede tests for successful admission, denial, unavailable admission, and non-GPU PCI aliases.
- [x] Run focused Afterglow and Drover test targets, lint changed Python files, and independently review both checkout diffs.
