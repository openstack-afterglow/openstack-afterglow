---
title: Instances
parent: API Reference
grand_parent: English
lang: en
nav_order: 31
---

# Instances API

> Tags: `instances`, `instance-metrics`
> Base path: `/api/v1/instances`

Manages the creation, retrieval, control, and deletion of Nova instances (virtual machines), along with volume/network/security-group/Floating IP/data-storage attachments and resource metric queries. Supports Afterglow's core feature of creating OverlayFS/Manila-based Union Mount VMs.

---

## Authentication Headers

| Header | Description |
|--------|-------------|
| `Authorization` | `Bearer <access_token>` (access JWT from login) |
| `X-Project-Id` | (Optional) Project UUID — defaults to the JWT's project; a different value triggers rescope |

> Ownership verification: A non-admin user can only view/control instances owned by their own project. Accessing another project's instance responds with 404/403 (some paths are unified to a generic error to prevent an IDOR oracle).

---

## Table of Contents

1. [Basic CRUD](#1-basic-crud)
2. [Instance Control](#2-instance-control)
3. [Volume Management](#3-volume-management)
4. [Network Interfaces](#4-network-interfaces)
5. [Security Groups](#5-security-groups)
6. [Owner Info](#6-owner-info)
7. [Floating IP Management](#7-floating-ip-management)
8. [Admin Password Reset](#8-admin-password-reset)
9. [Data Storage Attachments](#9-data-storage-attachments-storage-attachments)
10. [Resource Metrics](#10-resource-metrics)

---

## 1. Basic CRUD

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/instances` | List instances (short-lived cache) |
| `GET` | `/api/v1/instances/availability-zones` | List availability zones |
| `GET` | `/api/v1/instances/{instance_id}` | Detail of a specific instance |
| `POST` | `/api/v1/instances` | Create an instance synchronously (5/min) |
| `POST` | `/api/v1/instances/async` | Create an instance asynchronously via SSE |
| `POST` | `/api/v1/instances/bulk-action` | Bulk action on instances (10/min) |
| `DELETE` | `/api/v1/instances/{instance_id}` | Delete an instance (including associated resources, 5/min) |

### GET /api/v1/instances

![Instance list](../../assets/instance-list.png)
*Full project VM instance list — shows status, flavor, IP, and creation time, with auto-refresh*

Returns the project's instance list. Each item's `flavor_name`/`image_name` is resolved on the server side, and for volume-boot instances `image_name` is displayed as `"Booted from volume"`. The response is cached for a short period (force refresh with `?refresh=true`).

**Response (200 OK)** — array of `InstanceInfo`

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Instance UUID |
| `name` | string | Instance name |
| `status` | string | Nova status (`ACTIVE`, `SHUTOFF`, `BUILD`, `ERROR`, etc.) |
| `image_id` / `image_name` | string \| null | Boot image |
| `flavor_id` / `flavor_name` | string \| null | Flavor |
| `ip_addresses` | array | `{addr, type("fixed"\|"floating"), network_name}` |
| `created_at` | string \| null | Creation time (ISO 8601) |
| `metadata` | object | Nova server metadata |
| `union_libraries` | array[string] | List of Union Mount libraries |
| `union_strategy` | string \| null | `prebuilt` \| `dynamic` |
| `union_share_ids` | array[string] | Attached Manila share IDs |
| `union_upper_volume_id` | string \| null | OverlayFS upper volume ID |
| `key_name` | string \| null | SSH keypair name |
| `user_id` / `project_id` | string \| null | Owning user/project |
| `fault` | object \| null | Fault info in the ERROR state `{message, code, created}` |
| `host` | string \| null | Hypervisor host (populated only in admin scope) |

The `union_*` response fields only read historical VM metadata. Ordinary VM creation no longer offers library/SquashFS consumption or HA deployment options; new plain/GPU/data-mount VMs do not create Union metadata. Administrator Palimpsest build/import/runtime deployment and the file-storage administration catalog at `/api/v1/libraries` remain independent.

### GET /api/v1/instances/availability-zones

Returns the list of available availability zones (AZ). Used for the `availability_zone` selection when creating an instance.

**Response (200 OK)** — array of availability zones

### GET /api/v1/instances/{instance_id}

![VM instance detail](../../assets/admin-instance.png)
*View basic instance info (ID, image, flavor, keypair, IP list) alongside per-interval CPU/memory/network/disk I/O graphs directly in the panel*

Returns the details of a specific instance.

| Parameter | In | Type | Required | Description |
|-----------|-----|------|----------|-------------|
| `instance_id` | path | string | Yes | Instance UUID |

**Response (200 OK)** — `InstanceInfo` (see table above)

**Errors**: `404 Not Found` — instance does not exist or is owned by another project

### POST /api/v1/instances

Creates an instance synchronously. Waits for boot-source preparation, optional data mounts, cloud-init, Nova and Floating IP setup to complete. **Rate limit: 5/min.**

**Request body** (`CreateInstanceRequest`)

```json
{
  "name": "my-vm",
  "image_id": "uuid-string",
  "flavor_id": "uuid-string",
  "network_id": "uuid-string",
  "key_name": "my-key",
  "admin_pass": "string(8-128)",
  "availability_zone": "nova",
  "security_groups": ["default"],
  "boot_volume_size_gb": 20,
  "delete_boot_volume_on_termination": false,
  "data_mounts": [{ "file_storage_id": "uuid", "mount_point": "/mnt/data", "read_only": false }]
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | No | Instance name. When omitted/duplicated, the server normalizes and assigns a unique name |
| `image_id` | string | Conditional | Glance image UUID. **Mutually exclusive** with `boot_volume_id`; one of the two is required |
| `boot_volume_id` | string | Conditional | Reuse an existing boot volume. Mutually exclusive with `image_id`. Only `available` + `bootable` volumes allowed |
| `flavor_id` | string | Yes | Nova flavor UUID |
| `network_id` | string | No | Network UUID to attach. When omitted, the default network is determined automatically |
| `key_name` | string | No | SSH keypair name |
| `admin_pass` | string | No | Admin password (8–128 chars) |
| `availability_zone` | string | No | Availability zone. When omitted, the server default AZ |
| `security_groups` | array[string] | No | Security group names. The server adds the required GPU-monitoring SG |
| `boot_volume_size_gb` | integer | No | Boot volume size (GB, 1–16384). When omitted, the server config default |
| `delete_boot_volume_on_termination` | boolean | No | Delete the boot volume together on instance deletion (forced false when reusing an existing volume) |
| `additional_volume_ids` | array[string] | No | List of existing volume UUIDs to attach right after creation |
| `new_volumes` | array | No | List of volumes `{name, size_gb}` to newly create and attach |
| `data_mounts` | array | No | Directly mount an existing Manila share `{file_storage_id, mount_point, read_only}` |

> `data_mounts[].mount_point` allows only absolute paths under `/mnt`, `/data`, `/srv`, `/home`; `..`/`.` segments and system paths such as `/opt`·`/etc`·`/usr`·`/var` are rejected. Mounting an NFS share requires `network_id` (for subnet CIDR resolution).


**Response (201 Created)** — the created Nova server object

**Errors**
- `400 Bad Request` — boot source validation failure (`image_id`/`boot_volume_id` both specified or both missing), bad volume status, name normalization failure
- `409 Conflict` — GPU quota exceeded
- `500 Internal Server Error` — creation failure (resources are rolled back in reverse order). The detailed cause is hidden from non-admins

### POST /api/v1/instances/async

Creates an instance asynchronously and delivers real-time progress via an SSE (Server-Sent Events) stream.

**Request body**: same as `POST /api/v1/instances`

**Response**: `text/event-stream`. Each event is a `ProgressMessage` JSON.

```json
{
  "step": "MANILA_PREPARING",
  "progress": 20,
  "message": "File storage ready",
  "elapsed_seconds": 3.2,
  "instance_id": null,
  "error": null
}
```

**List of step values** (actual progress ranges)

| step | Progress | Description |
|------|----------|-------------|
| `MANILA_PREPARING` | 0 → 20% | Prepare file storage (library share / data_mounts) access rules |
| `BOOT_VOLUME_CREATING` | 20 → 45% | Create the boot volume (image-based) or validate an existing volume |
| `UPPER_VOLUME_CREATING` | 45 → 60% | Create the OverlayFS upper volume or reuse an existing one (only when libraries present) |
| `USERDATA_GENERATING` | 60 → 65% | Generate cloud-init user-data (when any of libraries/GPU/data_mounts is present) |
| `SERVER_CREATING` | 65 → 95% | Create the Nova server |
| `ATTACHING_VOLUME` | 95 → 100% | Attach upper/additional/new volumes |
| `FLOATING_IP_CREATING` | 100% | Create/attach the Floating IP (when a tenant network is selected) |
| `COMPLETED` | 100% | Done. Includes `instance_id` |
| `FAILED` | — | Failed. Includes `error` (a generic message for non-admins) |

**Rollback on failure**

If an error occurs during creation, already-created resources are cleaned up in reverse order.

| Order | Rollback target |
|-------|-----------------|
| 1 | Delete Floating IP |
| 2 | Delete Nova server |
| 3 | Delete boot volume (newly created) / upper volume (newly created) |
| 4 | Revoke Manila access rule |
| 5 | Delete dynamic file storage |

> When an existing volume was reused (`boot_volume_id`/`existing_upper_volume_id`), it is not deleted during rollback.

### POST /api/v1/instances/bulk-action

Performs the same action on multiple instances in bulk. Ownership is verified per instance and **partial success is allowed**. **Rate limit: 10/min.**

**Request body**

```json
{ "action": "stop", "instance_ids": ["uuid-1", "uuid-2"] }
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `action` | string | Yes | `start` \| `stop` \| `delete` \| `reboot` |
| `instance_ids` | array[string] | Yes | List of target UUIDs (1–50) |

**Response (200 OK)** — array of per-id results. Errors are unified to a generic message so as not to expose ownership/existence.

```json
{ "results": [ { "id": "uuid-1", "ok": true }, { "id": "uuid-2", "ok": false, "error": "Processing failed" } ] }
```

### DELETE /api/v1/instances/{instance_id}

Cleans up the instance together with its associated resources (health token, dynamic share, upper volume, CephX/NFS access rules, Floating IP). Associated resource cleanup is best-effort. **Rate limit: 5/min.**

| Parameter | In | Type | Required | Description |
|-----------|-----|------|----------|-------------|
| `instance_id` | path | string | Yes | Instance UUID |

**Response**: `204 No Content`

---

## 2. Instance Control

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/instances/{instance_id}/start` | Start an instance (30/min) |
| `POST` | `/api/v1/instances/{instance_id}/stop` | Stop an instance (30/min) |
| `POST` | `/api/v1/instances/{instance_id}/reboot` | Reboot an instance (30/min) |
| `POST` | `/api/v1/instances/{instance_id}/shelve` | Shelve an instance (release resources, keep disk, 30/min) |
| `POST` | `/api/v1/instances/{instance_id}/unshelve` | Restore a shelved instance (30/min) |
| `GET` | `/api/v1/instances/{instance_id}/console` | Return the VNC console URL |
| `GET` | `/api/v1/instances/{instance_id}/log` | Return the console log |

Each control action is performed after ownership verification and all return **`204 No Content`**. `start` assumes a stopped (`SHUTOFF`) state and `stop` assumes a running state; if the state does not match, the underlying Nova error is propagated as a `500`.

### GET /api/v1/instances/{instance_id}/console

Returns the VNC console access URL of the instance.

**Response (200 OK)**

```json
{ "url": "https://.../vnc_auto.html?token=..." }
```

### GET /api/v1/instances/{instance_id}/log

Returns the console log of the instance.

| Parameter | In | Type | Default | Description |
|-----------|-----|------|---------|-------------|
| `length` | query | integer | 100 | Number of log lines to return (`0`–`100000`; `0` means the full log) |

**Response (200 OK)**

```json
{ "output": "console log text..." }
```

---

## 3. Volume Management

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/instances/{instance_id}/volumes` | List attached volumes |
| `POST` | `/api/v1/instances/{instance_id}/volumes` | Attach a volume |
| `DELETE` | `/api/v1/instances/{instance_id}/volumes/{volume_id}` | Detach a volume |
| `PATCH` | `/api/v1/instances/{instance_id}/volumes/{volume_id}` | Modify volume attachment options |

### GET /api/v1/instances/{instance_id}/volumes

Returns the list of attached volumes. Each item resolves `name`/`size`/`status` as well.

### POST /api/v1/instances/{instance_id}/volumes

Attaches an existing volume to the instance.

**Request body**

```json
{ "volume_id": "uuid-string" }
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `volume_id` | string | Yes | UUID of the volume to attach |

**Response**: `201 Created`

### DELETE /api/v1/instances/{instance_id}/volumes/{volume_id}

Detaches a volume from the instance.

| Parameter | In | Type | Required | Description |
|-----------|-----|------|----------|-------------|
| `instance_id` | path | string | Yes | Instance UUID |
| `volume_id` | path | string | Yes | Volume UUID |

**Response**: `204 No Content`

### PATCH /api/v1/instances/{instance_id}/volumes/{volume_id}

Changes the volume attachment's `delete_on_termination` flag (whether the volume is deleted together with the instance).

**Request body**

```json
{ "delete_on_termination": true }
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `delete_on_termination` | boolean | Yes | Whether to delete the volume together on instance termination |

**Response**: `204 No Content`

---

## 4. Network Interfaces

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/instances/{instance_id}/interfaces` | List network interfaces |
| `POST` | `/api/v1/instances/{instance_id}/interfaces` | Add an interface |
| `DELETE` | `/api/v1/instances/{instance_id}/interfaces/{port_id}` | Remove an interface |

### POST /api/v1/instances/{instance_id}/interfaces

Adds a new network interface to the instance.

**Request body**

```json
{ "net_id": "uuid-string" }
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `net_id` | string | Yes | UUID of the network to attach |

**Response**: `201 Created`

### DELETE /api/v1/instances/{instance_id}/interfaces/{port_id}

| Parameter | In | Type | Required | Description |
|-----------|-----|------|----------|-------------|
| `instance_id` | path | string | Yes | Instance UUID |
| `port_id` | path | string | Yes | Port UUID |

**Response**: `204 No Content`

---

## 5. Security Groups

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/instances/{instance_id}/security-groups` | List the instance's ports and security groups |
| `POST` | `/api/v1/instances/{instance_id}/ports/{port_id}/security-groups` | Replace a port's security groups |

### GET /api/v1/instances/{instance_id}/security-groups

Returns the instance's port list together with the project-wide security group list.

**Response (200 OK)**

```json
{ "ports": [ ... ], "security_groups": [ { "id": "uuid", "name": "default" } ] }
```

### POST /api/v1/instances/{instance_id}/ports/{port_id}/security-groups

Replaces the specified port's security groups (replaces the existing list).

**Request body**

```json
{ "security_group_ids": ["uuid-1", "uuid-2"] }
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `security_group_ids` | array[string] | Yes | List of security group UUIDs to set (replaces the existing list) |

---

## 6. Owner Info

### GET /api/v1/instances/{instance_id}/owner

Returns the display info of the instance's owning user.

**Response (200 OK)**

```json
{ "display": "alice(alice@example.com)", "name": "alice", "email": "alice@example.com" }
```

> If the user lookup fails, returns `{"display": "<user_id>"}`; if there is no `user_id`, returns `{"display": "-"}`.

---

## 7. Floating IP Management

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/instances/{instance_id}/floating-ip` | Auto-create a Floating IP + attach to instance |
| `DELETE` | `/api/v1/instances/{instance_id}/floating-ip` | Detach + delete the instance's Floating IP |

### POST /api/v1/instances/{instance_id}/floating-ip

Automatically determines the instance port's subnet → router → connected external network, then creates and attaches a Floating IP. If attachment fails, the created Floating IP is auto-cleaned up.

| Parameter | In | Type | Required | Description |
|-----------|-----|------|----------|-------------|
| `instance_id` | path | string | Yes | Instance UUID |
| `port_id` | query | string | No | Port ID to attach (when omitted, the first unassigned port is auto-selected) |

**Response (200 OK)**

```json
{ "id": "uuid-string", "floating_ip_address": "203.0.113.10" }
```

**Errors**
- `400 Bad Request` — the instance has no port / all interfaces already have a FIP assigned
- `404 Not Found` — the specified interface does not exist
- `409 Conflict` — the interface already has a Floating IP assigned
- `422 Unprocessable Entity` — the subnet is not connected to an external network via a router / unreachable
- `500 Internal Server Error` — allocation failure

### DELETE /api/v1/instances/{instance_id}/floating-ip

Detaches and deletes all Floating IPs attached to the instance (best-effort).

**Response**: `204 No Content`

---

## 8. Admin Password Reset

Sends Nova `changePassword` for the guest's image-defined/default administrator account. **Both endpoints require project write access and either the verified system administrator or the instance's native Nova creator**. A non-system administrator must match `server.user_id` and `server.project_id` to their authenticated user and current project. Same-project membership, a project-admin role, and editable instance metadata do not prove creator ownership.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/instances/{server_id}/admin-password/precheck` | Precheck whether a reset is possible |
| `POST` | `/api/v1/instances/{server_id}/admin-password` | Reset the password |

### GET /api/v1/instances/{server_id}/admin-password/precheck

**Response (200 OK)** — `AdminPasswordPrecheck`

| Field | Type | Description |
|-------|------|-------------|
| `supported` | boolean | Whether a reset is possible |
| `reason` | string \| null | Reason it is not possible |
| `os_admin_user` | string \| null | Guest admin account name (based on image metadata) |
| `server_status` | string | Current Nova status |

> `supported=true` requires an `ACTIVE` server and `hw_qemu_guest_agent` enabled (`yes`, `true`, or `1`) on its boot image. These metadata checks do not prove that QGA is currently running or that guest password changes are supported. For volume boot, the precheck uses the volume matching Nova's root device; when that privileged field is absent, it accepts only one unambiguous bootable Cinder volume. It never guesses that `/dev/vda` is the root disk.

### POST /api/v1/instances/{server_id}/admin-password

**Request body**

```json
{ "new_password": "string(8-128)" }
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `new_password` | string | Yes | New admin password (8–128 chars) |

**Response**: `204 No Content` — Nova accepted the request. This does not prove that the guest applied the password or that RDP/SSH login succeeds.

**Errors**
- `403 Forbidden` — missing project write access, neither verified system administrator nor actual creator, wrong creator project, or native Nova policy denial
- `404 Not Found` — instance does not exist
- `409 Conflict` — not `ACTIVE`, QGA not enabled, ambiguous boot image, or Nova password change conflict
- `422 Unprocessable Entity` — malformed request or password outside 8–128 characters; password input is not echoed
- `400`, `401`, `501`, `503` — mapped provider request/authentication/driver/availability failure
- `502 Bad Gateway` — unexpected upstream failure; raw provider errors are not returned

The guest's QGA service and driver support are required. Nova targets the image's `os_admin_user` or the driver's OS default; this endpoint cannot choose an arbitrary guest username. Check Windows with its console/RDP or Linux with its console/SSH; Linux SSH password authentication is a separate policy. A request accepted by Nova is not reported as a completed guest password change. Passwords are held in `SecretStr`, excluded from response/error details, and omitted from audit payloads; only the attempt outcome is audited. The user detail offers the action only for the current user's instance, and the administrator detail only for a verified system administrator. Unsupported instances show the reason, and closing the dialog clears its inputs.

---

## 9. Data Storage Attachments (storage-attachments)

Grants a running VM access rules for a user-owned (or public) Manila file storage and returns the mount command to run in the guest.

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/instances/{instance_id}/storage-attachments` | Grant a file storage access rule + return the mount command |
| `GET` | `/api/v1/instances/{instance_id}/storage-attachments` | List attached data file storage |
| `DELETE` | `/api/v1/instances/{instance_id}/storage-attachments/{file_storage_id}` | Revoke the access rule |

### POST /api/v1/instances/{instance_id}/storage-attachments

**Request body** (`StorageAttachRequest`)

```json
{ "file_storage_id": "uuid-string", "mount_point": "/mnt/data", "read_only": false }
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file_storage_id` | string | Yes | Manila share UUID |
| `mount_point` | string | Yes | Absolute path under `/mnt`·`/data`·`/srv`·`/home` (system paths/`..` forbidden) |
| `read_only` | boolean | No | Whether to mount read-only (default false) |

**Response (200 OK)** — the mount command differs by protocol.

```json
{
  "file_storage_id": "uuid-string",
  "share_proto": "CEPHFS",
  "mount_command": "sudo mkdir -p ... && sudo mount -t ceph ...",
  "keyring_file": "[client.data-rw-...]\n    key = ...\n",
  "keyring_path": "/etc/ceph/ceph.client.data-rw-....keyring",
  "access_id": "uuid-string"
}
```

> For an NFS share, `keyring_file`/`keyring_path` are `null`, and an access rule based on the VM's fixed IP is granted (if the fixed IP cannot be found, `409`). If access is not permitted or the share is not `available`, `403`/`409` respectively.

### GET /api/v1/instances/{instance_id}/storage-attachments

**Response (200 OK)** — array `[{file_storage_id, name, share_proto, status}]`

### DELETE /api/v1/instances/{instance_id}/storage-attachments/{file_storage_id}

Revokes the CephX/NFS access rule granted to the instance and removes it from the metadata.

**Response**: `204 No Content`

---

## 10. Resource Metrics

Queries time-series/summary metrics for an instance from Prometheus (node_exporter first; libvirt-exporter fallback for tenant-network-isolated instances).

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/instances/{instance_id}/metrics` | Single-metric time series (deprecated, batch recommended) |
| `GET` | `/api/v1/instances/{instance_id}/metrics-batch` | Bulk retrieval of multiple metric time series |
| `GET` | `/api/v1/instances/metrics-summary-batch` | Project-wide 7-day CPU/memory summary + underutilization judgment |
| `GET` | `/api/v1/instances/{instance_id}/metrics-summary` | Instance min/avg/max summary + resize recommendation |

**Common parameters**

| Parameter | Values | Description |
|-----------|--------|-------------|
| `metric` | `cpu`, `memory`, `network_rx`, `network_tx`, `disk_read`, `disk_write`, `gpu_util`, `gpu_mem` | Metric key to query |
| `metrics` | above keys comma-separated | batch only. e.g., `cpu,memory,disk_read` |
| `range` | `15m`, `1h`, `6h`, `24h`, `7d` | Query range (single/batch default `1h`, summary default `7d`) |

> GPU metrics (`gpu_util`/`gpu_mem`, DCGM-based) are valid only on GPU instances (whose flavor name starts with `gpu.`). The single endpoint returns `400` on non-GPU instances, while the batch endpoint silently excludes GPU metrics.

### GET /api/v1/instances/{instance_id}/metrics-batch

**Response (200 OK)**

```json
{
  "instance_id": "uuid-string",
  "range": "1h",
  "metrics": {
    "cpu": { "series": [ { "ts": 1710000000, "value": 12.3 } ], "error": null },
    "memory": { "series": [ ... ], "error": null }
  }
}
```

**Errors**: `422` — `metrics` empty/unknown key. On a Prometheus failure, the reason is placed in each metric's `error` field.

### GET /api/v1/instances/metrics-summary-batch

Returns the 7-day average CPU/memory and underutilization status of all instances in the project. For badges on the list screen.

**Response (200 OK)**

```json
{
  "range": "7d",
  "prometheus_available": true,
  "instances": { "uuid-string": { "cpu_avg": 8.1, "mem_avg": 15.0, "underutilized": true } }
}
```

### GET /api/v1/instances/{instance_id}/metrics-summary

Returns the instance's CPU/memory/disk I/O statistics (min/avg/max) and, when underutilized, a recommended resize flavor. The recommendation is not produced for GPU instances and reflects Nova resize constraints (disk cannot be shrunk).

**Response (200 OK)**

```json
{
  "instance_id": "uuid-string",
  "range": "7d",
  "prometheus_available": true,
  "stats": { "cpu": { "min": 1.0, "avg": 8.1, "max": 20.0 }, "memory": { ... }, "disk_read": { ... }, "disk_write": { ... } },
  "recommendation": {
    "underutilized": true,
    "reason": "cpu_avg<10,mem_avg<20",
    "current_flavor": { "id": "...", "name": "m1.large", "vcpus": 4, "ram": 8192, "disk": 40 },
    "suggested_flavor": { "id": "...", "name": "m1.small", "vcpus": 2, "ram": 2048, "disk": 40 }
  }
}
```

> When Prometheus is unreachable, responds with `prometheus_available: false`, `stats: {}`, `recommendation: null`.
