# Coordinated service releases and Kolla deployment

## Goal

Release the merged Afterglow, Lumen, Palimpsest, Drover, and Waygate changes and deploy the published immutable images through the existing wireguard-dmslab Kolla environment.

## Scope and decisions

- Afterglow 1.25.0; Lumen 0.3.0; Palimpsest root 0.2.0; Drover 0.2.23; Waygate 0.1.4. Independently versioned subpackages retain their repository contracts.
- Work on `dev`. The user explicitly authorized this release's validated version and service-tag promotion PR merges. No direct commits to `main`, force pushes, or moving existing tags.
- Release the four service repositories before promoting their immutable tags into the Afterglow operator manifest and lock. Release Afterglow from the reviewed, merged result.
- Use each repository's existing release/package/image workflows; require the actual declared architecture builds and runtime verification. Palimpsest's signed release retains its native KVM gate.
- On wireguard-dmslab, preserve the existing configuration, secrets, inventory, database data, volumes, locally modified legacy roles, and rollback image references before changing deployment inputs.
- Replace obsolete in-tree sibling role links with the package-owned roles via the canonical locked operator environment. The user explicitly authorized adding Palimpsest Hub as a new production service, including its inventory, dedicated database/credentials and endpoints, without automatic legacy-data migration. Other disabled components remain disabled.
- Deploy only published immutable images through standard Kolla commands. Check readiness and authenticated dashboard/service paths separately.
- Palimpsest API and worker initially share the persistent local Hub volume on controller1; do not distribute a non-shared blob store across controllers. Public DNS/TLS routing must be verified independently before advertising the new endpoint.

## Risks and completion criteria

- The production plugin checkout predates the package-owned role cutover and contains local Waygate/Palimpsest changes; these must be backed up and accounted for, not discarded.
- Production credentials/configuration must never appear in tracked artifacts or command output.
- A published release or healthy container alone is insufficient deployment proof. Record the merged refs, image revisions/digests, Kolla recap, and authenticated smoke results.
- Keep unsupported or unavailable live paths explicit; do not claim provider inference, destructive VM lifecycle, or Cloud Shell lifecycle coverage from metadata/read-only checks.
