## Why

The user topology canvas is read-only even though the backend already exposes authenticated OpenStack write APIs for attaching an instance interface, attaching a router subnet gateway, setting a router external gateway, creating a network, and adding a subnet. Operators must leave topology context to perform those routine relationships, and the network detail panel cannot add a missing subnet.

## What Changes

- Honor `CreateNetworkRequest.subnet` and roll back a new network if its requested subnet cannot be created.
- Add a user-only topology canvas create toolbar and cable-drag workflow. Valid targets dispatch the existing resource APIs, then refresh the factual topology graph.
- Add subnet creation to the user network detail slide panel, including CIDR feedback before submit.
- Keep `/admin/topology` and the existing lane topology view read-only.

## Capabilities

### New Capabilities

- `topology-create-and-connect`: A project operator can create resources from the canvas, attach an instance to a tenant network, attach a router gateway to a tenant subnet, set an empty router's external gateway, and create a required subnet in context.
- `network-detail-subnet-create`: A user network detail panel can add a subnet whether the network presently has zero or more subnets.

### Modified Capabilities

- `network-create-subnet`: User network creation honors an optional nested subnet specification and returns the created subnet identifiers.

## Impact

- Backend network request model, network create handler, and focused pytest coverage.
- User topology canvas, canvas toolbar/node interactions, topology page, network detail components, mock transport, and focused Vitest coverage.
- Existing APIs remain the mutation contract; the page invokes them with the current project-scoped token and refreshes topology after success.
