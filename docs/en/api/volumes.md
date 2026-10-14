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
| `PATCH` | `/api/v1/volumes/{volume_id}` | Rename an owned volume, including `in-use` volumes |
| `POST` | `/api/v1/volumes` | Create a volume (10/min) |
| `POST` | `/api/v1/volumes/{volume_id}/extend` | Extend volume capacity (10/min) |
| `DELETE` | `/api/v1/volumes/{volume_id}` | Delete a volume |
| `POST` | `/api/v1/volumes/{volume_id}/force-delete` | Force-delete a volume in error/error_deleting state (admin) |

### GET /api/v1/volumes

![Volume list](../../assets/volume-list.png)
*Cinder volume list — check size, status (available/in-use), attached instance, and volume type*

Returns the project's Cinder volume list. The response is cached for about 15 seconds (`ttl_fast`). You can bypass the cache with `?refresh=true`.

The list menu and both the list SlidePanel and `/dashboard/volumes/{id}` detail share operation availability: rename; boot a VM from an available bootable volume; extend or back up an available or in-use volume; create a snapshot when enabled; transfer an available volume; and delete. Normal delete is disabled for attached volumes. Force-delete appears only for system administrators on volumes in error, error_deleting, or deleting state. Detail uses the existing dialogs and VM wizard, and refreshes the open volume/list after successful mutations. The list's Connect item opens detail; detail's Attach to instance action selects a VM when available.

Attached instance names are resolved in the current project and shown alongside UUIDs. When name lookup fails, the view labels the UUID as an unavailable name rather than guessing an instance from another project.

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

### PATCH /api/v1/volumes/{volume_id}

Renames a volume in the current project after verifying write permission and ownership. Attached (`in-use`) volumes may be renamed without detaching. The trimmed name must contain 1–255 characters.

**Request body** — `{ "name": "new-volume-name" }`

**Response (200 OK)** — refreshed `VolumeInfo`; the list cache is invalidated, and success or failure is recorded in the activity log.

| Status | Cause |
|--------|-------|
| `403` | No project write permission or Cinder rejected the change |
| `404` | Volume missing or belongs to another project |
| `409` | Cinder rejected the change in its current state |
| `422` | Name is blank or exceeds 255 characters |
| `500`/`502` | Volume retrieval or Cinder service failure |

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

The project API extends detached `available` volumes, or `in-use` volumes only when every attachment resolves to a server in the effective project with exact `SHUTOFF`, raw power state `4`, an explicitly idle task, and a reciprocal volume attachment. System admins cannot bypass project ownership here. Reread authoritative Cinder ownership/status/size/attachments immediately before mutation and reject changes. The separate global admin endpoint retains its existing contract.

| Parameter | In | Type | Required | Description |
|-----------|-----|------|----------|-------------|
| `volume_id` | path | string | Yes | Volume UUID |

**Request body** — `ProjectExtendVolumeRequest`

```json
{
  "new_size": 100
}
```

| Field | Type | Required | Constraint | Description |
|-------|------|----------|------------|-------------|
| `new_size` | integer | Yes | strict integer, `1..2147483647`, larger than current size | New capacity (GB); booleans, strings, fractions and shrink requests are rejected |

**Response (200 OK)** — actual provider-reread `VolumeInfo`, potentially still showing the previous size during asynchronous `extending`. Acceptance does not prove completed capacity growth or guest partition/filesystem expansion. Verify disk discovery after boot/rescan and perform any required guest-specific growth separately. No guest execution occurs. Attached root/data rows and the existing volume list/detail use the same explicitly scoped modal.

**Errors**

| Status | Cause |
|--------|-------|
| `400` | New size is at or below the current size, or Cinder extension failed |
| `404` | Volume does not exist or is not in the owning project |
| `403` | No project write permission |
| `409` | Unknown/unsafe attachment, power, task, reciprocity, or changed final Cinder snapshot |
| `422` | Strict integer/range validation failed |
| `502` | Provider lookup failed or accepted result could not be verified |
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

Transfer ownership between projects in **the same or different Keystone domains within the configured OpenStack cloud and region**. This does not copy data between separate clouds.

In the source project, create a transfer from an unattached `available` volume and securely share the transfer ID and auth key. Select the receiving project, open **Receive volume** from the volume list header, search the entire transfer ID, review the source domain/project and volume, then authenticate with the key. Receiving works with an empty destination inventory. **Pending transfers** lists and cancels only transfers sent by the current project.

### Endpoint List

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/volumes/transfers` | Current project's pending transfers |
| `GET` | `/api/v1/volumes/transfer/{transfer_id}` | Exact pending transfer lookup across every source domain/project |
| `POST` | `/api/v1/volumes/{volume_id}/transfer` | Create a transfer for an owned, unattached volume |
| `POST` | `/api/v1/volumes/transfer/{transfer_id}/accept` | Authenticate with the key and receive into the current project |
| `DELETE` | `/api/v1/volumes/transfer/{transfer_id}` | Cancel the current project's outgoing transfer |

`transfer_id` must be a complete, lowercase, hyphenated canonical UUID. There is no prefix/name/fuzzy search or global transfer-list API. Reads require authentication; mutations require current-project write permission. All transfer responses have `Cache-Control: no-store, private` and `Pragma: no-cache`.

### GET /api/v1/volumes/transfers

Uses the caller's genuinely project-scoped credential. Even an administrator selecting another project cannot substitute the administrator's home project or an all-project list. Rows contain `{id, name, volume_id, created_at}`, never the auth key. Foreign or unverifiable provider rows fail closed rather than becoming an empty list.

### GET /api/v1/volumes/transfer/{transfer_id}

The configured operator connection **only reads** one exact native transfer, its unattached `awaiting-transfer` volume, and the actual Keystone source project/domain. Source-project membership is not required. The response whitelist is:

```json
{
  "id": "11111111-1111-4111-8111-111111111111",
  "name": "data-handoff",
  "volume_id": "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
  "created_at": "2026-10-14T01:01:00Z",
  "volume_name": "research-data",
  "size": 24,
  "volume_type": "ceph_hdd",
  "status": "awaiting-transfer",
  "source_project": { "id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "name": "Research" },
  "source_domain": { "id": "11111111111111111111111111111111", "name": "Source domain" }
}
```

No auth key, user identity, endpoint, volume metadata or attachment body is exposed. This display snapshot does not authorize acceptance. Editing the search ID discards the previous result/key. Missing, accepted, cancelled or nonpending transfers return `404`; unverifiable ownership/directory identities return `502`; operator authentication, policy or service failure returns `503`. The operator needs exact Cinder transfer/volume and Keystone project/domain read permission. The application neither changes policies nor bypasses their failure.

### POST /api/v1/volumes/{volume_id}/transfer

Only current-project-owned, `available`, unattached volumes are eligible, including for administrators. **No automatic instance detachment or reattachment rollback occurs.** Detach a connected volume safely before transferring.

Optional body: `{ "name": "data-handoff" }` (at most255 characters). **201 response:** `{ "id": "transfer-uuid", "name": "data-handoff", "volume_id": "volume-uuid", "created_at": null, "auth_key": "issued-key" }`.

The native key is returned only at issuance. ID and key have separate copy controls; source inventory refresh leaves issuance visible. Closing/unmounting, user/project/token change or write-permission change discards the key. If it is lost or the issuance reply is missing, cancel through Pending transfers before creating another transfer. Neither the browser nor Afterglow persists the key.

### POST /api/v1/volumes/transfer/{transfer_id}/accept

Required body: `{ "auth_key": "issued-key" }`. The key must be nonblank and at most512 characters; never put it in the URI. Validation errors do not echo the rejected key.

Rechecks the pending native transfer and rejects source=destination with `409`. Uses a Keystone credential verified to belong to **the receiving caller and the selected destination project**, never operator/service credentials. Cinder validates the key, quota and native policy. After submission, exact returned IDs and actual destination ownership must match before success is reported.

**200 response:** `{ "id": "transfer-uuid", "name": "data-handoff", "volume_id": "volume-uuid" }`.

Create/cancel invalidate the source volume inventory; acceptance invalidates both source and destination inventories. Lost replies or failed ownership readback also invalidate both inventories but never retransmit the POST. Refresh the destination inventory to observe actual ownership after an ambiguous error. Guest/data consistency and application readiness are not guaranteed.

### DELETE /api/v1/volumes/transfer/{transfer_id}

Cancels only an unattached pending transfer actually owned by the current project, using the caller credential. Consumed/cancelled transfers return `404`; foreign transfers return native-policy `403` or strict-owner `404`. **Success: `204 No Content`.**

### Errors

| Status | Cause |
|--------|-------|
| `401` | Authentication missing |
| `403` | Write/project scope/native permission denied or incorrect auth key |
| `404` | Transfer/volume absent, consumed transfer or foreign source ownership |
| `409` | Attachment/state change, same source/destination, native state/quota conflict |
| `413` | Native destination-project quota exceeded |
| `422` | Noncanonical UUID or invalid name/key input |
| `502`/`503` | Unverifiable provider identity/readback, provider failure or operator unavailable |

Installed SDK3.3.0 selects `/os-volume-transfer` or microversion3.55+ `/volume-transfers` according to native support. Snapshot/encrypted-volume support, policies and quotas remain Cinder-owned; no bypass or separate copy is added. [Cinder native API reference](https://docs.openstack.org/api-ref/block-storage/v3/index.html#volume-transfers-os-volume-transfer).

---

## 5. Volume Backups

> Tags: `volume-backups`  
> Base path: `/api/v1/volumes/backups`

Volume backup navigation, pages, inline actions, and auto-backup are visible regardless of browser-local beta preferences; a legacy `afterglow.beta.volumeBackups=false` value no longer hides them. Switching projects clears the previous backup list and ignores late responses. UI visibility does not prove that the Cinder backup service is available or that a backup can be restored; verify service `enabled`/`up` and a real backup/restore separately in production.

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

Open **Volumes → Volume backups → Auto Backup settings** to save the source, wall-clock time, timezone, daily/weekly/monthly retention and enabled state. The same volume list/detail action links to `/dashboard/volumes/backups?auto-backup=<volume_id>`. **Saving or resuming never starts an immediate backup; execution starts at the returned next scheduled time.** Calendar events use the selected IANA timezone, not elapsed 24-hour/7-day/30-day intervals.

### Scheduling and execution across controllers

Backend processes automatically join when they share the same Redis/Valkey primary, logical database and `afterglow:auto_backup` namespace. No per-controller cron or additional worker service is required. Redis server-time45-second membership/leader leases and an independent10-second heartbeat retain one scheduler leader. Only that leader scans all policies every15seconds. Execution is a separate loop, so the leader's slow SDK request does not block assignments to other workers.

New due work and work with a departed owner are distributed by live workers' assignment counts; healthy pending/active ownership remains stable. Each worker claims only its own queue, atomically checking current membership/assignment and the renewable90-second volume lease. One volume/schedule slot is submitted once; different volumes can execute on different workers. Idle, paused and zero-tier policies open no new SDK connection, except that already accepted operations continue completion observation.

Graceful shutdown drains/closes SDK work and releases the volume lease before removing the participant. A crash hands work over after45-second membership/leader expiry and the next heartbeat/poll, without bypassing a remaining90-second volume lease. Late claim replies, Redis failure and lost incarnations fail closed; rejoining uses a fresh identity. An accepted-but-lost Cinder response is not retried by the SDK's create POST: observe the saved `unknown` journal instead.

The assignment unit is an API process, not an equal physical-controller weight when worker counts differ. Every replica must run this implementation and preserve persistent shared Redis policy/slot/journal data. Independent Redis stores, deleted keys or failover data loss invalidate duplicate prevention. Local distributed-runtime evidence is separate from production backup storage, restore and deployment qualification in the [testing guide](../../testing.md).

### Endpoint List

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/volumes/backups/auto-backup/configs` | List saved current-project policies and source observations |
| `GET` | `/api/v1/volumes/backups/auto-backup/{volume_id}` | Read the currently owned source's policy |
| `POST` | `/api/v1/volumes/backups/auto-backup/{volume_id}` | Create, edit, pause or resume a policy |
| `DELETE` | `/api/v1/volumes/backups/auto-backup/{volume_id}` | Remove the policy only; retain existing backups |

### POST /api/v1/volumes/backups/auto-backup/{volume_id}

Requires write authority and fresh **exact current-project source ownership**, including for system administrators. An enabled source must be `available` or `in-use`; `in-use` requires separately saved `force=true` consent.

**Request body** — `AutoBackupRequest` (omitting it uses these defaults)

```json
{
  "enabled": true,
  "max_daily": 2,
  "max_weekly": 2,
  "max_monthly": 1,
  "schedule_time": "03:00",
  "timezone": "UTC",
  "weekly_day": 0,
  "monthly_day": 1,
  "force": false
}
```

| Field | Type/range | Default | Meaning |
|---|---|---|---|
| `enabled` | boolean | `true` | `false` pauses while preserving settings |
| `max_daily` | integer, 0–30 | `2` | Daily execution and retention; 0 disables the tier |
| `max_weekly` | integer, 0–30 | `2` | Execution and retention on the selected weekday |
| `max_monthly` | integer, 0–30 | `1` | Execution and retention on the selected monthly date |
| `schedule_time` | `HH:mm`, 00:00–23:59 | `03:00` | Wall-clock time in the selected timezone |
| `timezone` | valid IANA timezone | `UTC` | For example, `Asia/Seoul` |
| `weekly_day` | integer, 0–6 | `0` | Monday=0, Sunday=6 |
| `monthly_day` | integer, 1–28 | `1` | A date present in every month |
| `force` | boolean | `false` | Forced-backup permission for future runs of this saved policy |

Enabled policies require at least one positive retention count. A zero tier does not delete its existing backups. Coincident events create **one full backup** with `monthly > weekly > daily` precedence and count it only in that tier. Missed schedules coalesce to one run, advancing the next time beyond now rather than bursting through a backlog. DST may skip or repeat wall-clock times; see [CronTrigger's DST warning](https://apscheduler.readthedocs.io/en/3.x/modules/triggers/cron.html#daylight-saving-time-behavior) or use UTC.

Policy force consent is not inherited from manual, one-time backup consent. It allows a backup while attached without detaching or overwriting the source, but does not quiesce guest writes or guarantee database/application consistency or successful recovery.

**Response**: `201 Created` — the saved input fields plus `project_id`, `volume_id`, `created_at`, `updated_at`, `schema_version`, `revision`, `next_run_at`, `next_tier`, `last_run_at`, `last_status`, `last_backup_id`, and `last_error`. Execution timestamps are UTC ISO 8601; the UI renders the policy timezone. `last_status` is `never | creating | available | error | unknown | skipped`. Cinder acceptance/creating is not completion. Unknown means the submission outcome cannot be established; observe by existing ID/exact name rather than automatically reissuing it.

**Errors**: `400` (enabled source state/force consent), `403` (write/provider authority), `404` (absent source or ownership mismatch), `422` (invalid settings), `503` (Redis or temporary source-read failure). Save the same fields with `enabled=false` to pause, or `true` to resume at a new future time.

### Reading policies and absent sources

`GET .../{volume_id}` checks fresh ownership and a saved policy; absent source/policy or ownership mismatch returns404. `POST .../configs` returns200 with an array. Saved current-project policies stay visible when the source is absent or unreadable. Only affected rows add response-only `source_status=missing | not_owned | unavailable`, `source_available=false | null`, and safe `source_error`, also used as `last_error` when no persisted error exists. Reads do not rewrite enabled state, retention or history.

### DELETE /api/v1/volumes/backups/auto-backup/{volume_id}

**Response**: `204 No Content`. Removes policy Redis data, never Cinder backups. Permitted only after fresh ownership succeeds, or when the source is authoritatively404/None and the **original stored identity exactly matches the current project and source**. Foreign/missing owners return404, provider403 stays403, and timeout/5xx returns503 while retaining the policy. Temporary failure is not authoritative absence.

Retention starts only after the new backup is observed `available`. It considers only older completed, valid-timestamp, full backups with the exact same project/source, recognized managed name and explicitly absent dependencies. Manual, foreign, pending, error, incremental and unknown-owner/dependency items are retained. Source, backup, current policy revision/enabled state and execution lease are checked again immediately before deletion.

Healthy legacy policies normalize once while preserving enabled state, retention, history, extra fields and existing force (false when absent), with UTC03:00/Monday/monthly1 calendar defaults. Invalid saved JSON or calendar fields remain byte-preserved, fail-closed disabled/error views until an explicit edit repairs them. Removing an orphan policy remains separate from keeping its backups.

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
