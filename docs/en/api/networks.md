---
title: Networks
parent: API Reference
grand_parent: English
lang: en
nav_order: 50
---

# Networks API

> Tag: `networks`
> Base path: `/api/v1/networks`

Manages Neutron networks, subnets, floating IPs, ports, and the project-wide topology.
Default network management and real-time traffic queries are also served by this router.

---

## Authentication Headers

| Header | Description |
|------|------|
| `Authorization` | `Bearer <access_token>` (access JWT from login) |
| `X-Project-Id` | (Optional) Project UUID — defaults to the JWT's project; a different value triggers rescope |

---

## Common Notes

- **Ownership verification**: The detail/delete/update family (`GET·DELETE /{network_id}`, subnet `PUT·DELETE`, floating IP `associate·disassociate·DELETE`)
  checks that the target resource's `project_id` matches the token project. On mismatch it responds with `404` (existence hiding).
- **External/shared network exemption**: `GET /{network_id}` treats the target as a valid cross-project exposure and skips ownership verification when it is an external (`is_router_external`) or shared (`is_shared`) network.
- **Cache**: List/topology responses are cached in Redis. The TTL is adjustable via the `[cache]` section of `afterglow.conf`, with defaults shown in the table below.
  Appending `?refresh=true` to the request, or a mutation (create/delete), invalidates the related cache.

| Cache target | TTL helper | Default (adjustable) |
|-----------|----------|-------------------|
| Network list (`GET ""`) | `ttl_normal` | 30s |
| Floating IP list (`GET /floating-ips`) | `ttl_fast` | 15s |
| Topology (`GET /topology`) | `ttl_normal` | 30s |
| Topology traffic port map (`GET /topology/traffic`) | `ttl_static` | 300s |

- **Rate limit**: All mutation endpoints (create/delete/associate/disassociate/subnet delete, etc.) are limited to `10/minute`.

---

## Table of Contents

1. [Networks](#1-networks)
2. [Default Networks](#2-default-networks)
3. [Subnets](#3-subnets)
4. [Floating IP](#4-floating-ip)
5. [Ports](#5-ports)
6. [Network Topology](#6-network-topology)

---

## 1. Networks

### Endpoint List

| Method | Path | Description |
|--------|------|------|
| `GET` | `/api/v1/networks` | Network list (30s cache) |
| `POST` | `/api/v1/networks` | Create network |
| `GET` | `/api/v1/networks/{network_id}` | Network detail (includes subnets/routers) |
| `DELETE` | `/api/v1/networks/{network_id}` | Delete network |

### GET /api/v1/networks

Returns the project's Neutron network list. The response is cached for 30 seconds.

| Parameter | Location | Type | Required | Description |
|----------|------|------|------|------|
| `refresh` | query | boolean | No | If `true`, ignore the cache and re-query |

**Response (200 OK)** — `NetworkInfo[]` array

```json
[
  {
    "id": "uuid-string",
    "name": "private-net",
    "status": "ACTIVE",
    "subnets": ["uuid-string"],
    "is_external": false,
    "is_shared": false
  }
]
```

| Field | Type | Description |
|------|------|------|
| `id` | string | Network UUID |
| `name` | string | Network name |
| `status` | string | Status (`ACTIVE`, `DOWN`, etc.) |
| `subnets` | array[string] | Subnet UUID list |
| `is_external` | boolean | Whether it is an external network |
| `is_shared` | boolean | Whether it is a shared network |

**Errors**

| Code | Description |
|------|------|
| `500` | Failed to fetch network list |

### POST /api/v1/networks

Creates a new network.

**Request body** — `CreateNetworkRequest`

```json
{
  "name": "string (required)"
}
```

| Field | Type | Required | Description |
|------|------|------|------|
| `name` | string | Yes | Network name |

**Response (201 Created)** — `NetworkInfo` object

**Errors**

| Code | Description |
|------|------|
| `500` | Failed to create network |

### GET /api/v1/networks/{network_id}

Returns detailed information for a specific network. Includes subnet details and the list of connected routers.
Ownership verification is performed unless it is an external/shared network.

| Parameter | Location | Type | Required | Description |
|----------|------|------|------|------|
| `network_id` | path | string | Yes | Network UUID |

**Response (200 OK)** — `NetworkDetail`

```json
{
  "id": "uuid-string",
  "name": "private-net",
  "status": "ACTIVE",
  "subnets": ["uuid-string"],
  "is_external": false,
  "is_shared": false,
  "subnet_details": [
    {
      "id": "uuid-string",
      "name": "subnet-name",
      "cidr": "192.168.1.0/24",
      "gateway_ip": "192.168.1.1",
      "dhcp_enabled": true
    }
  ],
  "routers": [
    {
      "id": "uuid-string",
      "name": "router-name",
      "status": "ACTIVE",
      "project_id": "uuid-string",
      "external_gateway_network_id": "uuid-string",
      "connected_subnet_ids": ["uuid-string"]
    }
  ]
}
```

**Errors**

| Code | Description |
|------|------|
| `404` | Network not found / ownership mismatch |

### DELETE /api/v1/networks/{network_id}

Deletes a network. It cannot be deleted if it has subnets or connected ports.

| Parameter | Location | Type | Required | Description |
|----------|------|------|------|------|
| `network_id` | path | string | Yes | Network UUID |

**Response**: `204 No Content`

**Errors**

| Code | Description |
|------|------|
| `404` | Network not found / ownership mismatch |
| `500` | Failed to delete network (child resources exist, etc.) |

---

## 2. Default Networks

Records a per-project "default network" in the app DB so it can be reused for instance creation, etc.
If `default_network_enabled` in `afterglow.conf` is off, `ensure-default` returns `404`.

### Endpoint List

| Method | Path | Description |
|--------|------|------|
| `POST` | `/api/v1/networks/ensure-default` | Get or create the default network |
| `GET` | `/api/v1/networks/default` | Read the stored default network record |
| `PUT` | `/api/v1/networks/default` | Assign the default network |

### POST /api/v1/networks/ensure-default

Gets the project's default network, or creates one if it does not exist. Called by the frontend when switching projects.
If already recorded in the DB it returns quickly; otherwise it provisions a network/subnet/router based on the configuration values
(`default_network_external_id`, `default_network_cidr`). On success it invalidates the network list cache.

**Response (200 OK)** — `NetworkInfo` object

**Errors**

| Code | Description |
|------|------|
| `404` | Default network feature is disabled (`default_network_enabled = false`) |
| `500` | Failed to process the default network |

### GET /api/v1/networks/default

Returns the default network record stored for the current project (DB-based).

**Response (200 OK)** — record dict

```json
{
  "project_id": "uuid-string",
  "network_id": "uuid-string",
  "subnet_id": "uuid-string",
  "router_id": "uuid-string",
  "auto_created": true,
  "created_at": "2026-01-01T00:00:00+00:00",
  "updated_at": "2026-01-01T00:00:00+00:00"
}
```

| Field | Type | Description |
|------|------|------|
| `project_id` | string | Project UUID |
| `network_id` | string | Default network UUID |
| `subnet_id` | string\|null | Representative subnet UUID |
| `router_id` | string\|null | Connected router UUID |
| `auto_created` | boolean | Whether it was auto-created by `ensure-default` |
| `created_at` | string\|null | Creation time (ISO 8601) |
| `updated_at` | string\|null | Update time (ISO 8601) |

**Errors**

| Code | Description |
|------|------|
| `404` | No default network is set |

### PUT /api/v1/networks/default

Assigns a user-chosen network as the project's default network. The subnet ID uses the first subnet of that network.
After assignment it invalidates the network list cache.

**Request body**

```json
{
  "network_id": "uuid-string (required)"
}
```

| Field | Type | Required | Description |
|------|------|------|------|
| `network_id` | string | Yes | Network UUID to assign as default |

**Response (200 OK)** — updated record dict (same shape as `GET /default`)

**Errors**

| Code | Description |
|------|------|
| `404` | Target network not found |

---

## 3. Subnets

### Endpoint List

| Method | Path | Description |
|--------|------|------|
| `POST` | `/api/v1/networks/{network_id}/subnets` | Create subnet |
| `PUT` | `/api/v1/networks/subnets/{subnet_id}` | Edit subnet (name/gateway/DHCP) |
| `DELETE` | `/api/v1/networks/subnets/{subnet_id}` | Delete subnet |

> **Path priority**: Fixed paths (`/subnets/{subnet_id}`) must be registered before dynamic paths (`/{network_id}`), so
> subnet edit/delete use the `/networks/subnets/...` form, while only subnet creation uses `/networks/{network_id}/subnets`.

### POST /api/v1/networks/{network_id}/subnets

Creates a subnet in the specified network.

| Parameter | Location | Type | Required | Description |
|----------|------|------|------|------|
| `network_id` | path | string | Yes | Target network UUID |

**Request body** — `CreateSubnetRequest`

```json
{
  "name": "string (required)",
  "cidr": "192.168.1.0/24 (required)",
  "gateway_ip": "string (optional)",
  "enable_dhcp": true
}
```

| Field | Type | Required | Description |
|------|------|------|------|
| `name` | string | Yes | Subnet name |
| `cidr` | string | Yes | CIDR notation (e.g., `192.168.1.0/24`). Must not overlap with other subnets in the network |
| `gateway_ip` | string | No | Gateway IP. If omitted, the first IP of the CIDR is used |
| `enable_dhcp` | boolean | No | Whether DHCP is enabled (default: `true`) |

**Response (201 Created)** — `SubnetDetail`

**Errors**

| Code | Description |
|------|------|
| `500` | Failed to create subnet (CIDR conflict, etc.) |

### PUT /api/v1/networks/subnets/{subnet_id}

Updates a subnet's name, gateway, and DHCP settings. Subject to ownership verification.

| Parameter | Location | Type | Required | Description |
|----------|------|------|------|------|
| `subnet_id` | path | string | Yes | Subnet UUID |

**Request body** — `UpdateSubnetRequest` (all fields optional; only provided fields are updated)

```json
{
  "name": "string (optional)",
  "gateway_ip": "string (optional)",
  "enable_dhcp": true
}
```

| Field | Type | Required | Description |
|------|------|------|------|
| `name` | string | No | Subnet name |
| `gateway_ip` | string | No | Gateway IP address |
| `enable_dhcp` | boolean | No | Whether DHCP is enabled |

**Response (200 OK)** — `SubnetDetail`

**Errors**

| Code | Description |
|------|------|
| `404` | Subnet not found / ownership mismatch |
| `500` | Failed to update subnet |

### DELETE /api/v1/networks/subnets/{subnet_id}

Deletes a subnet. Subject to ownership verification.

| Parameter | Location | Type | Required | Description |
|----------|------|------|------|------|
| `subnet_id` | path | string | Yes | Subnet UUID |

**Response**: `204 No Content`

**Errors**

| Code | Description |
|------|------|
| `404` | Subnet not found / ownership mismatch |
| `500` | Failed to delete subnet (router interfaces/ports exist, etc.) |

---

## 4. Floating IP

### Endpoint List

| Method | Path | Description |
|--------|------|------|
| `GET` | `/api/v1/networks/floating-ips` | Floating IP list (15s cache) |
| `POST` | `/api/v1/networks/floating-ips` | Create floating IP |
| `POST` | `/api/v1/networks/floating-ips/{fip_id}/associate` | Associate floating IP with an instance |
| `POST` | `/api/v1/networks/floating-ips/{fip_id}/disassociate` | Disassociate floating IP |
| `DELETE` | `/api/v1/networks/floating-ips/{fip_id}` | Delete floating IP |

### GET /api/v1/networks/floating-ips

Returns the project's floating IP list. The response is cached for 15 seconds.

**Response (200 OK)** — `FloatingIpInfo[]` array

```json
[
  {
    "id": "uuid-string",
    "floating_ip_address": "203.0.113.10",
    "fixed_ip_address": "10.0.0.5",
    "status": "ACTIVE",
    "port_id": "uuid-string",
    "floating_network_id": "uuid-string",
    "project_id": "uuid-string",
    "instance_id": "uuid-string",
    "instance_name": "web-01"
  }
]
```

| Field | Type | Description |
|------|------|------|
| `id` | string | Floating IP UUID |
| `floating_ip_address` | string | Floating IP address |
| `fixed_ip_address` | string\|null | Associated fixed IP address |
| `status` | string | Status (`ACTIVE`, `DOWN`, etc.) |
| `port_id` | string\|null | Associated port UUID |
| `floating_network_id` | string | External network UUID |
| `project_id` | string\|null | Project UUID |
| `instance_id` | string\|null | Associated instance UUID |
| `instance_name` | string\|null | Associated instance name |

### POST /api/v1/networks/floating-ips

Allocates a new floating IP from an external network.

**Request body** — `CreateFipRequest`

```json
{
  "floating_network_id": "uuid-string (required)"
}
```

| Field | Type | Required | Description |
|------|------|------|------|
| `floating_network_id` | string | Yes | External network UUID (must be a network with `is_external = true`) |

**Response (201 Created)** — `FloatingIpInfo` object

### POST /api/v1/networks/floating-ips/{fip_id}/associate

Associates a floating IP with an instance. The target floating IP undergoes ownership verification, and
the association succeeds only if the instance has a connectable port (fixed IP).

| Parameter | Location | Type | Required | Description |
|----------|------|------|------|------|
| `fip_id` | path | string | Yes | Floating IP UUID |

**Request body** — `AssociateFipRequest`

```json
{
  "instance_id": "uuid-string (required)"
}
```

| Field | Type | Required | Description |
|------|------|------|------|
| `instance_id` | string | Yes | Instance UUID to associate |

**Response (200 OK)** — `FloatingIpInfo` object

**Errors**

| Code | Description |
|------|------|
| `404` | Floating IP not found / ownership mismatch |
| `500` | Failed to associate floating IP |

### POST /api/v1/networks/floating-ips/{fip_id}/disassociate

Disassociates a floating IP from an instance. The floating IP itself is retained. After disassociation it invalidates the list cache.

| Parameter | Location | Type | Required | Description |
|----------|------|------|------|------|
| `fip_id` | path | string | Yes | Floating IP UUID |

**Response (200 OK)** — `FloatingIpInfo` object

**Errors**

| Code | Description |
|------|------|
| `404` | Floating IP not found / ownership mismatch |
| `500` | Failed to disassociate floating IP |

### DELETE /api/v1/networks/floating-ips/{fip_id}

Deletes (releases) a floating IP. After deletion it invalidates the list cache.

| Parameter | Location | Type | Required | Description |
|----------|------|------|------|------|
| `fip_id` | path | string | Yes | Floating IP UUID |

**Response**: `204 No Content`

**Errors**

| Code | Description |
|------|------|
| `404` | Floating IP not found / ownership mismatch |
| `500` | Failed to delete floating IP |

---

## 5. Ports

### GET /api/v1/networks/ports

Returns the Neutron port list for the current project.

**Response (200 OK)** — dict array

```json
[
  {
    "id": "uuid-string",
    "name": "",
    "status": "ACTIVE",
    "mac_address": "fa:16:3e:00:00:01",
    "fixed_ips": [{ "ip_address": "10.0.0.5", "subnet_id": "uuid-string" }],
    "network_id": "uuid-string",
    "device_owner": "compute:nova",
    "device_id": "uuid-string"
  }
]
```

| Field | Type | Description |
|------|------|------|
| `id` | string | Port UUID |
| `name` | string | Port name (empty string if none) |
| `status` | string | Status |
| `mac_address` | string | MAC address |
| `fixed_ips` | array[object] | Fixed IP list (`ip_address`, `subnet_id`) |
| `network_id` | string | UUID of the network it belongs to |
| `device_owner` | string | Type of device that owns the port (e.g., `compute:nova`) |
| `device_id` | string | UUID of the attached device (instance, etc.) |

**Errors**

| Code | Description |
|------|------|
| `500` | Failed to fetch ports |

---

## 6. Network Topology

![Network topology](../../../assets/network-topology.png)
*Visualizes the connection structure among routers, load balancers, and instances along with real-time rx/tx traffic figures in a graph view — supports search by name/IP*

The topology is split into two endpoints. **Structure** (`/topology`) returns node/edge relationships with a 30s cache, and
**Traffic** (`/topology/traffic`) is a short-interval-polling-only endpoint that computes real-time rx/tx bps on every call with no cache.
Values are **30-second averages** from Prometheus `rate(...[30s])`. The window depends on the scrape interval: the two jobs the topology reads (`instances-node`, `instances-libvirt`) must scrape every 10s so three samples fall inside the window (`deploy/k8s*/monitoring/prometheus/configmap.yaml`). The window constant is `app.api.network.networks.TOPOLOGY_RATE_WINDOW`; `backend/tests/test_topology_traffic.py` pins the window together with the scrape interval across **both** the deployed and template configmaps.

> **Failure mode**: a 30s window with a 10s scrape is exactly 3 samples, leaving one sample of slack. If **two consecutive scrapes are missed** (e.g. during an http_sd target refresh), `rate()` returns nothing and that instance drops out of `instances`, `networks`, and the history `series` entirely — the UI shows no value (`—`), not `0`. Raise the window to 45-60s for more slack (the `scrape x 3 <= window` contract still passes).

### Endpoint List

| Method | Path | Description |
|--------|------|------|
| `GET` | `/api/v1/networks/topology` | Topology structure (30s cache) |
| `GET` | `/api/v1/networks/topology/traffic` | Real-time traffic (rx/tx bps) |
| `GET` | `/api/v1/networks/topology/traffic/history` | Usage series + avg/max for one network |

### GET /api/v1/networks/topology

Returns the project's full network topology. Includes network, router, instance, floating IP, and load balancer relationships. Instances, routers, floating IPs, and load balancers are limited to the current project; networks include the project's own plus external/shared networks.
In user scope it shows only resources owned by the current project plus external/shared networks. The response is cached for 30 seconds.

**Response (200 OK)** — `TopologyData`

```json
{
  "networks": [
    {
      "id": "uuid-string",
      "name": "private-net",
      "status": "ACTIVE",
      "is_external": false,
      "is_shared": false,
      "project_id": "uuid-string",
      "subnet_details": [],
      "mtu": 1450
    }
  ],
  "routers": [
    {
      "id": "uuid-string",
      "name": "router-name",
      "status": "ACTIVE",
      "external_gateway_network_id": "uuid-string",
      "external_gateway_ips": ["203.0.113.1"],
      "interface_ips": [{ "ip_address": "192.168.1.1", "subnet_id": "uuid-string" }],
      "is_distributed": false,
      "is_ha": false,
      "connected_subnet_ids": ["uuid-string"],
      "dvr_subnet_ids": [],
      "project_id": "uuid-string",
      "enable_snat": true,
      "routes": [{ "destination": "10.20.0.0/16", "nexthop": "192.168.1.254" }]
    }
  ],
  "instances": [
    {
      "id": "uuid-string",
      "name": "web-01",
      "status": "ACTIVE",
      "project_id": "uuid-string",
      "network_names": ["private-net"],
      "ip_addresses": [
        {
          "addr": "10.0.0.5",
          "type": "fixed",
          "network_name": "private-net",
          "network_id": "uuid-string",
          "port_id": "uuid-string",
          "mac_addr": "fa:16:3e:00:00:01"
        }
      ],
      "flavor_name": "m1.small",
      "image_id": "uuid-string",
      "is_database": false
    }
  ],
  "floating_ips": [],
  "load_balancers": [
    {
      "id": "uuid-string",
      "name": "lb-01",
      "vip_address": "10.0.0.100",
      "vip_subnet_id": "uuid-string",
      "vip_network_id": "uuid-string",
      "provisioning_status": "ACTIVE",
      "operating_status": "ONLINE",
      "project_id": "uuid-string",
      "listeners": [],
      "members": []
    }
  ]
}
```

Key fields:

| Group | Field | Description |
|------|------|------|
| `networks[]` | `mtu` | Network MTU (`null` when Neutron does not expose the attribute) |
| `routers[]` | `is_distributed` / `is_ha` | Whether it is a DVR / HA router |
| `routers[]` | `external_gateway_ips` | Gateway external fixed IPs (including SNAT IP) |
| `routers[]` | `enable_snat` | Whether SNAT is enabled on the external gateway. `null` when the router has no gateway |
| `routers[]` | `routes` | Static routes `[{destination, nexthop}]` (malformed entries are dropped) |
| `instances[]` | `flavor_name` / `image_id` | Instance flavor name and boot image UUID (`image_id` is `null` for volume-booted instances) |
| `instances[]` | `is_database` | Whether the Nova instance backs a Trove database instance. `true` only when a **fixed** IP matches a Trove IP (floating IPs are never matched) |
| `instances[].ip_addresses[]` | `network_id` | Belonging network UUID enriched via the compute port mapping |
| `instances[].ip_addresses[]` | `port_id` / `mac_addr` | UUID and MAC of the Neutron compute port holding that IP. `null` for IPs without a port (e.g. floating) |
| `load_balancers[]` | `listeners` / `members` | Summary of listeners/members attached to the LB |

> The port metadata (`network_id` / `port_id` / `mac_addr`) and `flavor_name` / `image_id` are all filled from the existing
> Neutron/Nova batch queries, so the number of OpenStack calls does not change.
> `is_database` is filled from a single listing of Trove instances, an optional service. When Trove is not deployed or the
> listing fails, that is treated as a normal condition rather than an error and every instance is returned with `is_database: false`.
> Provider segment metadata (`provider_network_type` / `provider_segmentation_id` / `provider_physical_network`) is
> never included in the tenant response; it is returned only by the admin-only `GET /api/v1/admin/topology` (`AdminTopologyData`).

### GET /api/v1/networks/topology/traffic

Returns instant traffic (rx/tx bps) for the current topology resources. This is a **short-interval-polling-only** endpoint separate from the structure endpoint.
It collects libvirt/node_exporter metrics from Prometheus via instant queries, and the port↔MAC↔network mapping uses a 300s cache.
On Prometheus failure, traffic values fall back to 0.

| Parameter | Location | Type | Required | Description |
|----------|------|------|------|------|
| `all_projects` | query | boolean | No | Query traffic for all projects (default `false`). **System admin only** |

**Response (200 OK)**

```json
{
  "ts": 1767225600,
  "instances": { "uuid-string": { "rx_bps": 1024.0, "tx_bps": 2048.0 } },
  "networks": { "uuid-string": { "rx_bps": 4096.0, "tx_bps": 8192.0 } },
  "interfaces": {
    "port-uuid": {
      "instance_id": "uuid-string",
      "network_id": "uuid-string",
      "mac_address": "fa:16:3e:00:00:01",
      "rx_bps": 1024.0,
      "tx_bps": 2048.0
    }
  },
  "routers": {},
  "load_balancers": { "uuid-string": { "rx_bps": 512.0, "tx_bps": 512.0 } },
  "_meta": { "router_traffic": "exporter_required" }
}
```

| Field | Type | Description |
|------|------|------|
| `ts` | integer | Unix timestamp (seconds) of response generation |
| `instances` | object | Instance UUID → `{rx_bps, tx_bps}` |
| `networks` | object | Network UUID → `{rx_bps, tx_bps}` |
| `interfaces` | object | Port UUID → per-NIC traffic (includes instance/network/mac) |
| `routers` | object | Router traffic. Currently always `{}` — populated after ovs/libvirt exporter is enabled (Phase 2) |
| `load_balancers` | object | LB UUID → `{rx_bps, tx_bps}` (Octavia `/stats` delta) |
| `_meta` | object | Meta information (`router_traffic: exporter_required`) |

**Errors**

| Code | Description |
|------|------|
| `403` | `all_projects=true` called by a non-system-admin user |

### GET /api/v1/networks/topology/traffic/history

Returns the rx/tx bps series plus avg/max/latest stats for **one** network. The canvas network panel's "usage trend" section calls it **once when the panel opens**, and again when the user switches the range toggle (15m / 30m / 1h).

It uses the **same attribution rule** as the instant endpoint: the value is the sum of the NICs attached to that network, *not* router↔switch traffic (no router exporter). For the same reason it includes east-west (instance-to-instance) traffic.

Design constraints:

- **Do not poll.** Calling this periodically for every network multiplies Prometheus load by the number of networks.
- `step_s` is a fixed per-range value and is always **at or below** `TOPOLOGY_RATE_WINDOW` (30s). Using `calc_step()` (range/100) would yield 36s for the 1h range, which would drop traffic between samples from the graph. `backend/tests/test_topology_traffic.py::test_history_step_never_exceeds_rate_window` pins this contract.
- `stats` is computed **from the returned `series`**, not from separate `avg_over_time` queries. Two sources would make the graph peak disagree with the label.
- `stats` is **per direction**, not an rx+tx sum. The instant endpoint reports per direction, so a summed figure would sit next to `▼ 5.8M ▲ 2.0M` as an uncomparable `7.8M`. The rx and tx values of `max` may come from different timestamps (each is that direction's independent peak).
- Past traffic of instances no longer in the port map (deleted) is dropped because it has nothing to attribute to — the instant endpoint has the same limitation.
- The node_exporter fallback attributes only instances that libvirt did not observe **and** that have a single NIC. Multi-NIC instances cannot be resolved to a network by device name.

| Parameter | Location | Type | Required | Description |
|----------|------|------|------|------|
| `network_id` | query | string | Yes | Network ID to query |
| `range` | query | string | No | `15m` (default) · `30m` · `1h` |
| `all_projects` | query | boolean | No | Cover ports of all projects (default `false`). **System admin only** |

| `range` | Span | `step_s` | Samples |
|---------|------|----------|---------|
| `15m` | 900s | 15s | 60 |
| `30m` | 1800s | 30s | 60 |
| `1h` | 3600s | 30s | 120 |

**Response (200 OK)**

```json
{
  "network_id": "uuid-string",
  "range": "15m",
  "step_s": 15,
  "window": "30s",
  "series": [
    { "ts": 1767225585, "rx_bps": 4096.0, "tx_bps": 8192.0 },
    { "ts": 1767225600, "rx_bps": 5120.0, "tx_bps": 8192.0 }
  ],
  "stats": {
    "avg": { "rx_bps": 4608.0, "tx_bps": 8192.0 },
    "max": { "rx_bps": 5120.0, "tx_bps": 8192.0 },
    "latest": { "rx_bps": 5120.0, "tx_bps": 8192.0 }
  },
  "_meta": { "source": "network_nic_sum", "router_traffic": "exporter_required" }
}
```

| Field | Type | Description |
|------|------|------|
| `step_s` | integer | Sample interval in seconds; guaranteed to be at or below the rate window |
| `window` | string | Backend rate window (`TOPOLOGY_RATE_WINDOW`) |
| `series` | array | `{ts, rx_bps, tx_bps}` samples. Empty array on Prometheus failure |
| `stats` | object | Per-direction `avg`/`max`/`latest` computed from `series`. Each is `{rx_bps, tx_bps}`, or `null` when there are no samples (distinct from 0) |
| `_meta.source` | string | Always `network_nic_sum` — states that this is a NIC sum, not router↔switch |

**Errors**

| Code | Description |
|------|------|
| `403` | `all_projects=true` called by a non-system-admin user |
| `422` | `network_id` missing or `range` not an allowed value |
