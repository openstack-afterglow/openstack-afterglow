---
title: Volumes
parent: API Reference
grand_parent: English
lang: en
nav_order: 54
---

# Volumes API

> Tags: `volumes`, `volume-backups`, `volume-snapshots`  
> Base paths: `/api/v1/volumes`, `/api/v1/volumes/backups`, `/api/v1/volume-snapshots`

Manages Cinder block storage volumes, backups, and snapshots.

---

## Authentication Headers

| Header | Description |
|--------|-------------|
| `Authorization` | `Bearer <access_token>` (access JWT from login) |
| `X-Project-Id` | (Optional) Project UUID — defaults to the JWT's project; a different value triggers rescope |

> Volumes, backups, and snapshots are OpenStack-native resources not subject to app-level ownership
> verification, but single-item retrieval/mutation endpoints accessed via a path parameter re-verify
> project ownership with `assert_resource_owner`.
> To avoid exposing existence to non-owners, they uniformly return `404`.

---

## Table of Contents

1. [Volumes](#1-volumes)
2. [Volume Extension](#2-volume-extension)
3. [Volume Force-Delete and Delete Recovery Diagnostics](#3-volume-force-delete-and-delete-recovery-diagnostics)
4. [Volume Transfer](#4-volume-transfer)
5. [Volume Backups](#5-volume-backups)
6. [Auto Backup](#6-auto-backup)
7. [Volume Snapshots](#7-volume-snapshots)

---

## 1. Volumes

> Tags: `volumes`  
> Base path: `/api/v1/volumes`

### Endpoint List

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/volumes` | List volumes (15-second cache) |
| `GET` | `/api/v1/volumes/{volume_id}` | Volume detail |
| `POST` | `/api/v1/volumes` | Create a volume (10/min) |
| `POST` | `/api/v1/volumes/{volume_id}/extend` | Extend volume capacity (10/min) |
| `DELETE` | `/api/v1/volumes/{volume_id}` | Delete a volume |
| `POST` | `/api/v1/volumes/{volume_id}/force-delete` | Force-delete a volume in error/error_deleting state (admin) |

### GET /api/v1/volumes

![Volume list](../../assets/volume-list.png)
*Cinder volume list — check size, status (available/in-use), attached instance, and volume type*

Returns the project's Cinder volume list. The response is cached for about 15 seconds (`ttl_fast`). You can bypass the cache with `?refresh=true`.

**Response (200 OK)** — array of `VolumeInfo[]`

```json
[
  {
    "id": "uuid-string",
    "name": "volume-name",
    "status": "in-use",
    "size": 50,
    "volume_type": "ceph",
    "attachments": [
      {
        "server_id": "uuid-string",
        "device": "/dev/vdb"
      }
    ],
    "bootable": false,
    "volume_image_metadata": null
  }
]
```

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Volume UUID |
| `name` | string | Volume name |
| `status` | string | Status (`available`, `in-use`, `error`, `error_deleting`, etc.) |
| `size` | integer | Size (GB) |
| `volume_type` | string\|null | Volume type |
| `attachments` | array | Attachment info (`server_id`, `device`, etc.) |
| `bootable` | boolean | Whether the volume is bootable |
| `volume_image_metadata` | object\|null | Metadata when created from an image |

**Errors**

| Status | Cause |
|--------|-------|
| `500` | Volume list retrieval failed |

### GET /api/v1/volumes/{volume_id}

Returns the details of a specific volume. Verifies ownership before retrieval.

| Parameter | In | Type | Required | Description |
|-----------|-----|------|----------|-------------|
| `volume_id` | path | string | Yes | Volume UUID |

**Response (200 OK)** — `VolumeInfo` object

**Errors**

| Status | Cause |
|--------|-------|
| `404` | Volume does not exist or is not in the owning project |

### POST /api/v1/volumes

Creates a new Cinder volume. **Rate limit: 10/min**

**Request body** — `CreateVolumeRequest`

```json
{
  "name": "string (required, 1-255 chars)",
  "size_gb": 50,
  "availability_zone": "string (optional)"
}
```

| Field | Type | Required | Constraint | Description |
|-------|------|----------|------------|-------------|
| `name` | string | Yes | 1–255 chars | Volume name |
| `size_gb` | integer | Yes | 1–16384 | Size (GB) |
| `availability_zone` | string | No | | Availability zone |

**Response (201 Created)** — `VolumeInfo` object

**Errors**

| Status | Cause |
|--------|-------|
| `422` | Request body validation failure (name length, size range, etc.) |
| `429` | Per-minute creation limit exceeded |
| `500` | Volume creation failed |

### DELETE /api/v1/volumes/{volume_id}

Deletes a volume. A volume in the `in-use` state (attached to an instance) cannot be deleted and must be detached first. Verifies ownership before deletion.

| Parameter | In | Type | Required | Description |
|-----------|-----|------|----------|-------------|
| `volume_id` | path | string | Yes | Volume UUID |

**Response**: `204 No Content`

**Errors**

| Status | Cause |
|--------|-------|
| `404` | Volume does not exist or is not in the owning project |
| `500` | Deletion failed (attached state, dependent snapshots/backups, etc.) |

---

## 2. Volume Extension

### POST /api/v1/volumes/{volume_id}/extend

Extends volume capacity. **Rate limit: 10/min**

Because Ceph online extension is supported, not only `available` volumes but also **`in-use` volumes (attached to an instance) can be extended without downtime**. Shrinking is not supported — the new size must be larger than the current size. Verifies ownership before extension.

| Parameter | In | Type | Required | Description |
|-----------|-----|------|----------|-------------|
| `volume_id` | path | string | Yes | Volume UUID |

**Request body** — `ExtendVolumeRequest`

```json
{
  "new_size": 100
}
```

| Field | Type | Required | Constraint | Description |
|-------|------|----------|------------|-------------|
| `new_size` | integer | Yes | `> 0`, must be larger than current size | New capacity (GB) |

**Response (200 OK)** — the `VolumeInfo` object after extension

**Errors**

| Status | Cause |
|--------|-------|
| `400` | New size is at or below the current size, or Cinder extension failed |
| `404` | Volume does not exist or is not in the owning project |
| `429` | Per-minute extension limit exceeded |

---

## 3. Volume Force-Delete and Delete Recovery Diagnostics

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/volumes/{volume_id}/force-delete` | Force-delete a volume in error/error_deleting state |
| `GET` | `/api/v1/admin/volumes/{volume_id}/delete-diagnostics` | Admin-only diagnosis of delete-failure causes |
| `POST` | `/api/v1/admin/volumes/{volume_id}/recover-delete` | Admin-only automatic delete recovery based on diagnostics |

### POST /api/v1/volumes/{volume_id}/force-delete

**Admin-only** (`require_admin`). Force-deletes a volume in the `error` or `error_deleting` state. The current implementation resets the status to `error` via Cinder's `os-reset-status`, then performs `os-force_delete`.

| Parameter | In | Type | Required | Description |
|-----------|-----|------|----------|-------------|
| `volume_id` | path | string | Yes | Volume UUID |

**Response**: `204 No Content`

**Errors**

| Status | Cause |
|--------|-------|
| `403` | No admin privilege |
| `500` | Force-delete failed |

### GET /api/v1/admin/volumes/{volume_id}/delete-diagnostics

An admin-only endpoint. For a volume in a delete-failure state such as `error_deleting`, it checks the Cinder status, attachments, snapshot/backup dependencies, and Cinder messages, and returns whether automatic recovery is possible. Retrieving Cinder messages is best-effort, and the diagnosis continues even if it fails.

### POST /api/v1/admin/volumes/{volume_id}/recover-delete

An admin-only endpoint. The server re-runs the diagnosis and then, only when there are no attachment and snapshot/backup dependencies, executes in the order `reset_status(error, detached)` → normal deletion → deletion verification → force-delete if necessary → deletion verification. Snapshot/backup dependencies are not deleted automatically; if present, a `blocked` result is returned, so the admin must decide separately whether to preserve or delete them via an explicit action.

---

## 4. Volume Transfer

A volume's ownership can be transferred to another project. The flow is in the order **sender creates the transfer → shares the `auth_key` → receiver accepts**.

### Endpoint List

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/volumes/transfers` | List transfers |
| `POST` | `/api/v1/volumes/{volume_id}/transfer` | Create a transfer |
| `POST` | `/api/v1/volumes/transfer/{transfer_id}/accept` | Accept a transfer |
| `DELETE` | `/api/v1/volumes/transfer/{transfer_id}` | Cancel a transfer |

### GET /api/v1/volumes/transfers

Returns the current project's volume transfer list.

**Response (200 OK)** — array

### POST /api/v1/volumes/{volume_id}/transfer

Creates a volume ownership transfer request. The response's `auth_key` is required for the receiver to accept.

If the volume is attached to an instance, it is **automatically detached first**, then it waits for the `available` state before creating the transfer. If transfer creation fails, the volume is re-attached (rollback) to the instance it was detached from.

| Parameter | In | Type | Required | Description |
|-----------|-----|------|----------|-------------|
| `volume_id` | path | string | Yes | UUID of the volume to transfer |

**Request body** — `CreateVolumeTransferRequest` (optional, can be omitted)

```json
{
  "name": "string (optional) — transfer name"
}
```

**Response (201 Created)**

```json
{
  "id": "transfer-uuid",
  "name": "transfer-name",
  "volume_id": "volume-uuid",
  "auth_key": "auth-key-string"
}
```

> ⚠️ `auth_key` is returned only at creation time. Store it safely.

**Errors**

| Status | Cause |
|--------|-------|
| `404` | Volume does not exist or is not in the owning project |
| `409` | Failed to detach the attached volume or detach wait timed out |
| `500` | Transfer creation failed (an automatic rollback is attempted on failure) |

### POST /api/v1/volumes/transfer/{transfer_id}/accept

Accepts a transfer request, transferring volume ownership to the current project.

| Parameter | In | Type | Required | Description |
|-----------|-----|------|----------|-------------|
| `transfer_id` | path | string | Yes | Transfer UUID |

**Request body** — `AcceptVolumeTransferRequest`

```json
{
  "auth_key": "string (required) — the auth key issued at transfer creation"
}
```

**Response (200 OK)**

```json
{
  "id": "transfer-uuid",
  "volume_id": "volume-uuid"
}
```

**Errors**

| Status | Cause |
|--------|-------|
| `422` | `auth_key` missing |
| `500` | Transfer acceptance failed (including an incorrect auth_key) |

### DELETE /api/v1/volumes/transfer/{transfer_id}

Cancels a transfer request. An already-accepted transfer cannot be canceled.

| Parameter | In | Type | Required | Description |
|-----------|-----|------|----------|-------------|
| `transfer_id` | path | string | Yes | Transfer UUID |

**Response**: `204 No Content`

---

## 5. Volume Backups

> Tags: `volume-backups`  
> Base path: `/api/v1/volumes/backups`

When no browser preference is stored, the frontend shows the volume-backup navigation and flows by default. A user can still turn the feature off for the current browser in Account Settings, and an explicitly stored `false` preference remains authoritative. UI visibility does not prove that the Cinder backup service is available; production deployments must verify its `enabled`/`up` state separately.

### Endpoint List

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/volumes/backups` | List volume backups |
| `GET` | `/api/v1/volumes/backups/{backup_id}` | Backup detail |
| `POST` | `/api/v1/volumes/backups` | Create a backup |
| `POST` | `/api/v1/volumes/backups/{backup_id}/restore` | Restore a backup |
| `DELETE` | `/api/v1/volumes/backups/{backup_id}` | Delete a backup |

### GET /api/v1/volumes/backups

Returns the project's Cinder volume backup list. The response is cached (`ttl_slow`). You can bypass the cache with `?refresh=true`.

**Response (200 OK)** — array

```json
[
  {
    "id": "uuid-string",
    "name": "backup-name",
    "status": "available",
    "size": 50,
    "volume_id": "uuid-string",
    "created_at": "2024-01-01T00:00:00Z"
  }
]
```

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Backup UUID |
| `name` | string | Backup name |
| `status` | string | Status (`available`, `creating`, `restoring`, `error`, etc.) |
| `size` | integer | Size (GB) |
| `volume_id` | string | Source volume UUID |
| `created_at` | string | Creation time (ISO 8601) |

### GET /api/v1/volumes/backups/{backup_id}

Returns the details of a specific backup. Verifies backup ownership before retrieval.

**Errors**: `404` (backup does not exist or is not in the owning project)

### POST /api/v1/volumes/backups

Creates a new volume backup. Verifies ownership of the source volume.

**Request body** — `CreateBackupRequest`

```json
{
  "volume_id": "uuid-string (required)",
  "name": "string (required)",
  "description": "string (optional)",
  "incremental": false
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `volume_id` | string | Yes | UUID of the volume to back up |
| `name` | string | Yes | Backup name |
| `description` | string | No | Description |
| `incremental` | boolean | No | Whether it is an incremental backup (default: `false`) |

**Response (201 Created)**

```json
{
  "id": "uuid-string",
  "name": "backup-name",
  "status": "creating",
  "volume_id": "uuid-string"
}
```

**Errors**

| Status | Cause |
|--------|-------|
| `404` | Source volume does not exist or is not in the owning project |
| `4xx/5xx` | Manila/Cinder API errors passed through with their status code and message |
| `500` | Backup creation failed |

### POST /api/v1/volumes/backups/{backup_id}/restore

Restores a backup. Verifies backup ownership, and when `volume_id` is specified, also verifies ownership of the target volume.

**Request body** — `RestoreBackupRequest` (optional, can be omitted)

```json
{
  "volume_id": "uuid-string (optional, when overwriting an existing volume)"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `volume_id` | string | No | UUID of the volume to overwrite. When omitted, restores to a new volume |

**Response (200 OK)**

```json
{
  "restore": {
    "backup_id": "uuid-string",
    "volume_id": "uuid-string",
    "volume_name": "restored-volume"
  }
}
```

### DELETE /api/v1/volumes/backups/{backup_id}

Deletes a backup. Verifies ownership.

| Parameter | In | Type | Required | Description |
|-----------|-----|------|----------|-------------|
| `backup_id` | path | string | Yes | Backup UUID |

**Response**: `204 No Content`

---

## 6. Auto Backup

Configures and manages periodic automatic backups of a volume. Auto-backup settings are managed by Afterglow, and **the first backup cycle runs in the background immediately upon activation**. Subsequent cycles are rotated by the scheduler according to the retention policy (daily/weekly/monthly).

### Endpoint List

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/volumes/backups/auto-backup/configs` | List the project's auto-backup settings |
| `GET` | `/api/v1/volumes/backups/auto-backup/{volume_id}` | Get a volume's auto-backup settings |
| `POST` | `/api/v1/volumes/backups/auto-backup/{volume_id}` | Enable auto backup |
| `DELETE` | `/api/v1/volumes/backups/auto-backup/{volume_id}` | Disable auto backup |

### POST /api/v1/volumes/backups/auto-backup/configs

Returns the list of all auto-backup settings in the current project.

**Response (200 OK)** — array

### GET /api/v1/volumes/backups/auto-backup/{volume_id}

Retrieves the auto-backup settings of the specified volume.

| Parameter | In | Type | Required | Description |
|-----------|-----|------|----------|-------------|
| `volume_id` | path | string | Yes | Volume UUID |

**Response (200 OK)** — auto-backup settings object

**Errors**: `404` (settings do not exist)

### POST /api/v1/volumes/backups/auto-backup/{volume_id}

Enables auto backup on the specified volume. The first backup cycle starts in the background right after activation.

| Parameter | In | Type | Required | Description |
|-----------|-----|------|----------|-------------|
| `volume_id` | path | string | Yes | Volume UUID |

**Request body** — `AutoBackupRequest` (optional, defaults applied when omitted)

```json
{
  "max_daily": 2,
  "max_weekly": 2,
  "max_monthly": 1
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `max_daily` | integer | No | `2` | Number of daily backups to retain |
| `max_weekly` | integer | No | `2` | Number of weekly backups to retain |
| `max_monthly` | integer | No | `1` | Number of monthly backups to retain |

**Response**: `201 Created` — the created auto-backup settings object

### DELETE /api/v1/volumes/backups/auto-backup/{volume_id}

Disables auto backup on the specified volume.

| Parameter | In | Type | Required | Description |
|-----------|-----|------|----------|-------------|
| `volume_id` | path | string | Yes | Volume UUID |

**Response**: `204 No Content`

---

## 7. Volume Snapshots

> Tags: `volume-snapshots`  
> Base path: `/api/v1/volume-snapshots`

Unlike backups, a snapshot is a point-in-time copy that resides in the same Ceph pool as the source volume.

### Endpoint List

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/volume-snapshots` | List snapshots |
| `GET` | `/api/v1/volume-snapshots/{snapshot_id}` | Snapshot detail |
| `POST` | `/api/v1/volume-snapshots` | Create a snapshot |
| `DELETE` | `/api/v1/volume-snapshots/{snapshot_id}` | Delete a snapshot |

### GET /api/v1/volume-snapshots

Returns the project's Cinder volume snapshot list. The response is cached (`ttl_normal`).

| Parameter | In | Type | Required | Description |
|-----------|-----|------|----------|-------------|
| `volume_id` | query | string | No | Filter snapshots of a specific volume only |
| `refresh` | query | boolean | No | Whether to bypass the cache |

**Response (200 OK)** — array

```json
[
  {
    "id": "uuid-string",
    "name": "snapshot-name",
    "status": "available",
    "size": 50,
    "volume_id": "uuid-string",
    "created_at": "2024-01-01T00:00:00Z"
  }
]
```

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Snapshot UUID |
| `name` | string | Snapshot name |
| `status` | string | Status (`available`, `creating`, `error`, etc.) |
| `size` | integer | Size (GB) |
| `volume_id` | string | Source volume UUID |
| `created_at` | string | Creation time (ISO 8601) |

### GET /api/v1/volume-snapshots/{snapshot_id}

Returns the details of a specific snapshot. Verifies ownership before retrieval.

**Errors**: `404` (snapshot does not exist or is not in the owning project)

### POST /api/v1/volume-snapshots

Creates a new volume snapshot. Verifies ownership of the source volume.

**Request body** — `CreateSnapshotRequest`

```json
{
  "volume_id": "uuid-string (required)",
  "name": "string (required)",
  "description": "string (optional)",
  "force": false
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `volume_id` | string | Yes | UUID of the volume to snapshot |
| `name` | string | Yes | Snapshot name |
| `description` | string | No | Description |
| `force` | boolean | No | Force-snapshot even an `in-use` volume (default: `false`) |

**Response (201 Created)**

**Errors**

| Status | Cause |
|--------|-------|
| `404` | Source volume does not exist or is not in the owning project |
| `4xx/5xx` | Cinder API errors passed through with their status code and message |
| `500` | Snapshot creation failed |

### DELETE /api/v1/volume-snapshots/{snapshot_id}

Deletes a snapshot. Verifies ownership.

| Parameter | In | Type | Required | Description |
|-----------|-----|------|----------|-------------|
| `snapshot_id` | path | string | Yes | Snapshot UUID |

**Response**: `204 No Content`
