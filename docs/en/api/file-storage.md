---
title: File Storage
parent: API Reference
grand_parent: English
lang: en
nav_order: 55
---

# File Storage API

> Tags: `file-storage`  
> Base path: `/api/v1/file-storage`

Manages the Manila shared file system (CephFS/NFS).

> **Activation condition:** `afterglow.conf [services] manila = true`.
> Since Manila is an optional service, when disabled this router itself is not mounted, so
> all `/api/v1/file-storage*` paths return `404`.

---

## Authentication Headers

| Header | Description |
|--------|-------------|
| `Authorization` | `Bearer <access_token>` (access JWT from login) |
| `X-Project-Id` | (Optional) Project UUID — defaults to the JWT's project; a different value triggers rescope |

> **Ownership model:** Afterglow tracks the owning project via the share's `metadata.union_project_id`.
> On single-item retrieval/mutation, if this value differs from the caller's project, `404` (existence concealment) is returned.
> However, system admins and `is_public` shares are exempt from verification because cross-project exposure is normal for them.

---

## Table of Contents

1. [File Storage CRUD](#1-file-storage-crud)
2. [Access Rules](#2-access-rules)
3. [Quota, Type, and Network Queries](#3-quota-type-and-network-queries)

---

## 1. File Storage CRUD

### Endpoint List

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/file-storage` | List file storage |
| `GET` | `/api/v1/file-storage/{file_storage_id}` | File storage detail |
| `POST` | `/api/v1/file-storage` | Create file storage (5/min) |
| `DELETE` | `/api/v1/file-storage/{file_storage_id}` | Delete file storage |

### GET /api/v1/file-storage

Returns the project's Manila share list. The response is cached for about 15 seconds (`ttl_fast`). Admins can view shares across all projects.

| Parameter | In | Type | Default | Description |
|-----------|-----|------|---------|-------------|
| `refresh` | query | boolean | `false` | Whether to bypass the cache |

**Response (200 OK)** — array of `FileStorageInfo[]`

```json
[
  {
    "id": "uuid-string",
    "name": "union-prebuilt-python311",
    "status": "available",
    "size": 20,
    "share_proto": "CEPHFS",
    "export_locations": ["10.0.0.1:/volumes/_nogroup/..."],
    "metadata": {
      "union_type": "prebuilt",
      "union_library": "python311"
    },
    "is_public": false,
    "library_name": "python311",
    "library_version": "3.11",
    "built_at": "2024-01-01T00:00:00Z"
  }
]
```

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Share UUID |
| `name` | string | Share name |
| `status` | string | Status (`available`, `creating`, `error`, etc.) |
| `size` | integer | Size (GB) |
| `share_proto` | string | Protocol (`CEPHFS`, `NFS`) |
| `export_locations` | array[string] | List of mount paths |
| `nfs_export_location` | string\|null | NFS-only export path |
| `metadata` | object | Metadata (includes Afterglow-specific fields) |
| `is_public` | boolean | Whether it is a public share |
| `library_name` | string\|null | Afterglow library ID |
| `library_version` | string\|null | Library version |
| `built_at` | string\|null | Build time |

### GET /api/v1/file-storage/{file_storage_id}

Returns the details of a specific file storage. Verifies ownership.

> The `host` field is backend controller / CephFS pool topology information, so it is **exposed only to admins**
> and is masked to `null` in non-admin responses.
> On detail retrieval, extended fields such as `user_name` (Keystone name) are resolved best-effort.

| Parameter | In | Type | Required | Description |
|-----------|-----|------|----------|-------------|
| `file_storage_id` | path | string | Yes | File storage UUID |

**Response (200 OK)** — `FileStorageInfo` object

**Errors**: `404` (does not exist or is not in the owning project)

### POST /api/v1/file-storage

Creates a new Manila share. **Rate limit: 5/min**

When `share_type`/`share_network_id` are omitted, the config file defaults apply. The default share type differs by protocol — `NFS` uses `os_manila_nfs_share_type`, otherwise `os_manila_share_type`.

For NFS shares, `share_network_id` is sent to Manila only when the selected share type has `DHSS=True`. It is omitted for `DHSS=False`; if the share type's DHSS mode cannot be determined, creation fails before allocating a share.

**Request body** — `CreateFileStorageRequest`

```json
{
  "name": "string (required, 1-255 chars)",
  "size_gb": 20,
  "share_type": "cephfstype (optional)",
  "share_network_id": "uuid-string (optional)",
  "metadata": {},
  "share_proto": "CEPHFS"
}
```

| Field | Type | Required | Constraint | Description |
|-------|------|----------|------------|-------------|
| `name` | string | Yes | 1–255 chars | Share name |
| `size_gb` | integer | Yes | 1–16384 | Size (GB) |
| `share_type` | string | No | max 255 chars | Manila share type. Default: config file |
| `share_network_id` | string | No | | Share network UUID. Default: config file |
| `metadata` | object | No | | Metadata |
| `share_proto` | string | No | `CEPHFS` \| `NFS` | Protocol (default: `CEPHFS`) |

**Response (201 Created)** — `FileStorageInfo` object

**Errors**

| Status | Cause |
|--------|-------|
| `4xx` | Manila API responded with 4xx (status code and message passed through) |
| `409` | Manila polling error (error status, capabilities filter failure, etc. — failure reason exposed) |
| `422` | Request body validation failure |
| `429` | Per-minute creation limit exceeded |
| `502` | Manila API 5xx (external service failure) |
| `500` | Other creation failure |

### DELETE /api/v1/file-storage/{file_storage_id}

Deletes file storage. Verifies ownership, and when deleting a cross-project-owned share, also invalidates the owning project's cache.

| Parameter | In | Type | Required | Description |
|-----------|-----|------|----------|-------------|
| `file_storage_id` | path | string | Yes | File storage UUID |

**Response**: `204 No Content`

> For cases where a normal deletion fails due to `dhss_false_share_network_mismatch`, etc.,
> admin-only diagnostic (`delete-diagnostics`) and force-delete (`force-delete`) endpoints
> exist in a separate admin router. (See the `FileStorageDeleteDiagnostic` model)

---

## 2. Access Rules

Manages access control for a Manila share. CephX authentication or IP-based access is possible.

### Endpoint List

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/file-storage/{file_storage_id}/access-rules` | List access rules |
| `POST` | `/api/v1/file-storage/{file_storage_id}/access-rules` | Add an access rule |
| `DELETE` | `/api/v1/file-storage/{file_storage_id}/access-rules/{access_id}` | Delete an access rule |

All access rule endpoints first verify ownership of the target share.

### GET /api/v1/file-storage/{file_storage_id}/access-rules

Returns the access rule list of the file storage.

**Response (200 OK)** — array

### POST /api/v1/file-storage/{file_storage_id}/access-rules

Adds an access rule to the file storage.

**Request body** — `CreateAccessRuleRequest`

```json
{
  "access_to": "string (required, 1-255 chars)",
  "access_level": "ro",
  "access_type": "cephx",
  "root_squash": true,
  "sec_flavor": "sys"
}
```

| Field | Type | Required | Constraint | Description |
|-------|------|----------|------------|-------------|
| `access_to` | string | Yes | 1–255 chars | Access target (CephX ID or IP/CIDR) |
| `access_level` | string | No | `ro` \| `rw` | Access level (default: `ro` read-only) |
| `access_type` | string | No | `cephx` \| `ip` | Access type (default: `cephx`) |
| `root_squash` | boolean | No | | For `ip`-type NFS only. Maps root UID to nobody (default: `true`) |
| `sec_flavor` | string | No | `sys` \| `krb5` \| `krb5i` \| `krb5p` | Security flavor for `ip`-type NFS (default: `sys`) |

> **Security defaults:** The defaults for `root_squash` and `sec_flavor` are the security-recommended settings.
> For IP-based NFS access, `root_squash=true` prevents a client's root from acquiring unauthorized file ownership,
> and the Kerberos flavors (`krb5i`/`krb5p`) additionally guarantee integrity and confidentiality.
> For detailed background, see the architecture and security documents.

**Response (201 Created)**

**Errors**

| Status | Cause |
|--------|-------|
| `4xx` | Manila API 4xx (status code and message passed through) |
| `502` | Manila API 5xx |
| `500` | Other creation failure |

### DELETE /api/v1/file-storage/{file_storage_id}/access-rules/{access_id}

Deletes (revokes) an access rule.

| Parameter | In | Type | Required | Description |
|-----------|-----|------|----------|-------------|
| `file_storage_id` | path | string | Yes | File storage UUID |
| `access_id` | path | string | Yes | Access rule UUID |

**Response**: `204 No Content`

---

## 3. Quota, Type, and Network Queries

### GET /api/v1/file-storage/quota

Returns the project's Manila file storage quota.

**Response (200 OK)**

```json
{
  "gigabytes": {"limit": 1000, "in_use": 200},
  "shares": {"limit": 50, "in_use": 10},
  "snapshots": {"limit": 50, "in_use": 5}
}
```

### GET /api/v1/file-storage/types

Returns the list of available Manila share types.

**Response (200 OK)** — array

### GET /api/v1/file-storage/networks

A convenience endpoint that returns the list of Manila share networks usable for file storage creation.

> This endpoint is read-only. For creating/deleting share networks and detailed management,
> use `/api/v1/share-networks` in the [Share Snapshot & Network API](../../api/share-management.md).

**Response (200 OK)** — array
