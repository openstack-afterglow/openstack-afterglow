---
title: Security Groups
parent: API Reference
grand_parent: English
lang: en
nav_order: 53
---

# Security Groups API

> Tag: `security-groups`  
> Base path: `/api/v1/security-groups`

Manages Neutron security groups and rules. Used to control network traffic access for instances.

---

## Authentication Headers

| Header | Description |
|------|------|
| `Authorization` | `Bearer <access_token>` (access JWT from login) |
| `X-Project-Id` | (Optional) Project UUID — defaults to the JWT's project; a different value triggers rescope |

---

## Table of Contents

1. [Security Groups](#1-security-groups)
2. [Security Group Rules](#2-security-group-rules)

---

## 1. Security Groups

### Endpoint List

| Method | Path | Description |
|--------|------|------|
| `GET` | `/api/v1/security-groups` | Security group list (60s cache) |
| `GET` | `/api/v1/security-groups/quota` | Project security-group and rule limits/usage |
| `GET` | `/api/v1/security-groups/{sg_id}/instances` | Project instances using the group on compute ports |
| `POST` | `/api/v1/security-groups` | Create security group |
| `DELETE` | `/api/v1/security-groups/{sg_id}` | Delete security group |

### GET /api/v1/security-groups

Returns the project's security group list. The response is cached for 60 seconds.

**Response (200 OK)** — array

```json
[
  {
    "id": "uuid-string",
    "name": "default",
    "description": "Default security group",
    "rules": [
      {
        "id": "uuid-string",
        "direction": "ingress",
        "protocol": null,
        "port_range_min": null,
        "port_range_max": null,
        "remote_ip_prefix": null,
        "ethertype": "IPv4",
        "remote_group_id": null
      }
    ]
  }
]
```

Each rule includes `remote_group_id`: `null` for CIDR targets, otherwise the referenced project security-group UUID. The UI resolves the group's name while retaining its UUID.

### GET /api/v1/security-groups/quota

Returns the current project's Neutron security-group/rule quota `limit` and actual `in_use`. `limit: -1` is unlimited. Missing or failed detailed usage is an error, never silently treated as zero.

```json
{
  "security_group": { "limit": 10, "in_use": 2 },
  "security_group_rule": { "limit": 100, "in_use": 7 }
}
```

### GET /api/v1/security-groups/{sg_id}/instances

Requires ownership of the group in the current project. Joins project Neutron compute ports carrying the group with Nova servers; each instance appears once even with multiple matching ports. A lookup error is not returned as an empty list.

```json
[{ "id": "instance-uuid", "name": "app-vm", "status": "ACTIVE" }]
```

### POST /api/v1/security-groups

Creates a new security group.

**Request body**

```json
{
  "name": "string (required)",
  "description": "string (optional)"
}
```

| Field | Type | Required | Description |
|------|------|------|------|
| `name` | string | Yes | Security group name |
| `description` | string | No | Description |

**Response (201 Created)**

### DELETE /api/v1/security-groups/{sg_id}

Deletes a security group. The default security group cannot be deleted.

| Parameter | Location | Type | Required | Description |
|----------|------|------|------|------|
| `sg_id` | path | string | Yes | Security group UUID |

**Response**: `204 No Content`

---

## 2. Security Group Rules

![Security group rule detail](../../../assets/security-group-detail.png)
*The in-table IP version column shows each rule's `ethertype` (`IPv4`/`IPv6`); creation and removal stay inside the table. Neutron does not edit rule match fields in place; the edit action copies values for an explicit remove-and-create flow. Policy changes between those two requests.*

### Endpoint List

| Method | Path | Description |
|--------|------|------|
| `POST` | `/api/v1/security-groups/{sg_id}/rules` | Add security group rule |
| `DELETE` | `/api/v1/security-groups/{sg_id}/rules/{rule_id}` | Delete security group rule |

### POST /api/v1/security-groups/{sg_id}/rules

Adds a new rule to a security group.

**Request body**

```json
{
  "direction": "ingress",
  "protocol": "tcp",
  "port_range_min": 22,
  "port_range_max": 22,
  "remote_ip_prefix": "0.0.0.0/0",
  "ethertype": "IPv4"
}
```

| Field | Type | Required | Description |
|------|------|------|------|
| `direction` | string | Yes | Traffic direction (`ingress`, `egress`) |
| `protocol` | string | No | Protocol (`tcp`, `udp`, `icmp`, `null` = all protocols) |
| `port_range_min` | integer | No | Minimum port number |
| `port_range_max` | integer | No | Maximum port number |
| `remote_ip_prefix` | string | No | Remote IP range (CIDR notation, e.g., `0.0.0.0/0`) |
| `remote_group_id` | string | No | Remote security-group UUID owned by the current project; mutually exclusive with `remote_ip_prefix` |
| `ethertype` | string | No | Ethertype (`IPv4`, `IPv6`, default: `IPv4`) |

Choose CIDR or a remote security group, not both. If neither is supplied (or CIDR is blank), IPv4 uses `0.0.0.0/0` and IPv6 uses `::/0`. Omitting the end port when a start port is present creates a single-port rule. No default CIDR is sent with a group target.

| direction allowed value | Description |
|-------------------|------|
| `ingress` | Inbound traffic (receive) |
| `egress` | Outbound traffic (send) |

| protocol allowed value | Description |
|-----------------|------|
| `tcp` | TCP |
| `udp` | UDP |
| `icmp` | ICMP |
| `null` | All protocols |

**Response (201 Created)**

```json
{
  "id": "uuid-string",
  "direction": "ingress",
  "protocol": "tcp",
  "port_range_min": 22,
  "port_range_max": 22,
  "remote_ip_prefix": "0.0.0.0/0",
  "ethertype": "IPv4",
  "security_group_id": "uuid-string",
  "remote_group_id": null
}
```

### DELETE /api/v1/security-groups/{sg_id}/rules/{rule_id}

Deletes a security group rule.

| Parameter | Location | Type | Required | Description |
|----------|------|------|------|------|
| `sg_id` | path | string | Yes | Security group UUID |
| `rule_id` | path | string | Yes | Rule UUID |

**Response**: `204 No Content`
