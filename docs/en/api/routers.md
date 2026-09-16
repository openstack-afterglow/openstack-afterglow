---
title: Routers
parent: API Reference
grand_parent: English
lang: en
nav_order: 51
---

# Routers API

> Tag: `routers`
> Base path: `/api/v1/routers`

Manages Neutron routers, interfaces, and external gateways.
A router serves two roles: routing between subnets (internal interfaces) and connectivity to external networks (gateway).

---

## Authentication Headers

| Header | Description |
|------|------|
| `Authorization` | `Bearer <access_token>` (access JWT from login) |
| `X-Project-Id` | (Optional) Project UUID — defaults to the JWT's project; a different value triggers rescope |

---

## Common Notes

- **Ownership verification**: endpoints that handle a single router and all mutations proceed only when the router `project_id` is present and matches the token project. Interface add/remove requires the same condition for its subnet. Mismatch or missing owner metadata responds with `404` (existence hiding). Only a system admin bypasses this check.
- **Cache**: The router list (`GET ""`) is cached with `ttl_normal` (adjustable via `afterglow.conf`, default 30s).
  On create/delete mutations, the list cache is invalidated.
- **Rate limit**: All mutation endpoints (create/delete/interface/gateway) are limited to `10/minute`.

### Interface vs. Gateway

| Category | Target | Direction | Endpoint |
|------|------|------|-----------|
| Internal interface | Tenant subnet | Subnet ↔ router | `POST·DELETE /{router_id}/interfaces` |
| External gateway | External network (`is_external`) | Router → external network (SNAT) | `POST·DELETE /{router_id}/gateway` |

Gateway configuration always requires the UUID of an **external network** (`is_external = true`).

---

## Endpoint List

| Method | Path | Description |
|--------|------|------|
| `GET` | `/api/v1/routers` | Router list (30s cache) |
| `POST` | `/api/v1/routers` | Create router |
| `GET` | `/api/v1/routers/{router_id}` | Router detail (includes interfaces) |
| `DELETE` | `/api/v1/routers/{router_id}` | Delete router |
| `POST` | `/api/v1/routers/{router_id}/interfaces` | Add subnet interface |
| `DELETE` | `/api/v1/routers/{router_id}/interfaces/{subnet_id}` | Remove interface |
| `POST` | `/api/v1/routers/{router_id}/gateway` | Set external gateway |
| `DELETE` | `/api/v1/routers/{router_id}/gateway` | Remove gateway |

---

## GET /api/v1/routers

Returns the project's Neutron router list. The response is cached for 30 seconds.

| Parameter | Location | Type | Required | Description |
|----------|------|------|------|------|
| `refresh` | query | boolean | No | If `true`, ignore the cache and re-query |

**Response (200 OK)** — `RouterInfo[]` array

```json
[
  {
    "id": "uuid-string",
    "name": "router-name",
    "status": "ACTIVE",
    "project_id": "uuid-string",
    "external_gateway_network_id": "uuid-string",
    "connected_subnet_ids": ["uuid-string"]
  }
]
```

| Field | Type | Description |
|------|------|------|
| `id` | string | Router UUID |
| `name` | string | Router name |
| `status` | string | Status (`ACTIVE`, `DOWN`, etc.) |
| `project_id` | string\|null | Project UUID |
| `external_gateway_network_id` | string\|null | UUID of the network set as external gateway (`null` if none) |
| `connected_subnet_ids` | array[string] | List of connected internal subnet UUIDs |

**Errors**

| Code | Description |
|------|------|
| `500` | Failed to fetch router list |

---

## POST /api/v1/routers

Creates a new router. If `external_network_id` is passed as well, the external gateway is set at creation time.

**Request body** — `CreateRouterRequest`

```json
{
  "name": "string (required)",
  "external_network_id": "uuid-string (optional)"
}
```

| Field | Type | Required | Description |
|------|------|------|------|
| `name` | string | Yes | Router name |
| `external_network_id` | string | No | UUID of the external network to set as external gateway |

**Response (201 Created)** — `RouterInfo` object

**Errors**

| Code | Description |
|------|------|
| `500` | Failed to create router |

---

## GET /api/v1/routers/{router_id}

Returns detailed information for a specific router. Includes the list of connected interfaces and the external gateway network name.

| Parameter | Location | Type | Required | Description |
|----------|------|------|------|------|
| `router_id` | path | string | Yes | Router UUID |

**Response (200 OK)** — `RouterDetail`

```json
{
  "id": "uuid-string",
  "name": "router-name",
  "status": "ACTIVE",
  "project_id": "uuid-string",
  "external_gateway_network_id": "uuid-string",
  "external_gateway_network_name": "external-net",
  "interfaces": [
    {
      "id": "uuid-string (port ID)",
      "subnet_id": "uuid-string",
      "subnet_name": "subnet-name",
      "network_id": "uuid-string",
      "ip_address": "192.168.1.1"
    }
  ]
}
```

| Field | Type | Description |
|------|------|------|
| `external_gateway_network_name` | string\|null | External gateway network name |
| `interfaces[].id` | string | Interface port UUID |
| `interfaces[].subnet_id` | string | Connected subnet UUID |
| `interfaces[].ip_address` | string | The router's interface IP on that subnet |

**Errors**

| Code | Description |
|------|------|
| `404` | Router not found / ownership mismatch |

---

## DELETE /api/v1/routers/{router_id}

Deletes a router. If it has connected interfaces or a gateway, they must be removed first. After deletion it invalidates the list cache.

| Parameter | Location | Type | Required | Description |
|----------|------|------|------|------|
| `router_id` | path | string | Yes | Router UUID |

**Response**: `204 No Content`

**Errors**

| Code | Description |
|------|------|
| `404` | Router not found / ownership mismatch |
| `500` | Failed to delete router (interfaces/gateway remain, etc.) |

---

## POST /api/v1/routers/{router_id}/interfaces

Adds an internal subnet interface to the router only for a subnet **owned by the same project**. If `auto_gateway` is `true`, the subnet's gateway IP is used as the interface IP.

| Parameter | Location | Type | Required | Description |
|----------|------|------|------|------|
| `router_id` | path | string | Yes | Router UUID |

**Request body** — `RouterInterfaceRequest`

```json
{
  "subnet_id": "uuid-string (required)",
  "auto_gateway": false
}
```

| Field | Type | Required | Description |
|------|------|------|------|
| `subnet_id` | string | Yes | UUID of the subnet to connect |
| `auto_gateway` | boolean | No | Use the subnet gateway IP as the interface (default: `false`) |

**Response (201 Created)**

**Errors**

| Code | Description |
|------|------|
| `404` | Router or subnet not found / ownership mismatch / missing owner metadata |
| `500` | Failed to add interface |

---

## DELETE /api/v1/routers/{router_id}/interfaces/{subnet_id}

Removes a subnet interface from the router.

| Parameter | Location | Type | Required | Description |
|----------|------|------|------|------|
| `router_id` | path | string | Yes | Router UUID |
| `subnet_id` | path | string | Yes | UUID of the subnet to remove |

**Response**: `204 No Content`

**Errors**

| Code | Description |
|------|------|
| `404` | Router not found / ownership mismatch |
| `500` | Failed to remove interface |

---

## POST /api/v1/routers/{router_id}/gateway

Sets an external gateway on the router. The target must be an external network (`is_external = true`).

| Parameter | Location | Type | Required | Description |
|----------|------|------|------|------|
| `router_id` | path | string | Yes | Router UUID |

**Request body** — `RouterGatewayRequest`

```json
{
  "external_network_id": "uuid-string (required)"
}
```

| Field | Type | Required | Description |
|------|------|------|------|
| `external_network_id` | string | Yes | UUID of the external network to set as external gateway |

**Response**: `204 No Content`

**Errors**

| Code | Description |
|------|------|
| `404` | Router not found / ownership mismatch |
| `500` | Failed to set gateway |

---

## DELETE /api/v1/routers/{router_id}/gateway

Removes the router's external gateway.

| Parameter | Location | Type | Required | Description |
|----------|------|------|------|------|
| `router_id` | path | string | Yes | Router UUID |

**Response**: `204 No Content`

**Errors**

| Code | Description |
|------|------|
| `404` | Router not found / ownership mismatch |
| `500` | Failed to remove gateway |
