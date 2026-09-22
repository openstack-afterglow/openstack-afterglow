## Why

The Object Storage browser has only tree/table rows; image-heavy folders cannot be scanned visually. The active multipart upload route accepts client MIME and a no-op security scan before copying from quarantine, so successful responses do not establish type or byte integrity.

## What Changes

- Add a folder grid with an explicit persisted table/grid switch, authenticated bounded image/PDF thumbnails, and a useful full preview fallback.
- Inspect uploads server-side while streaming to quarantine. Compare browser SHA-256 with independently computed bytes, verify stored size and digest before promotion, and return inspection metadata.
- Reject active-content or malformed files and unsafe archives without silently publishing them. Preserve cancel, size-cap, ownership, and quarantine cleanup contracts.
- Expose upload hashing, inspection, rejection, and success states in the existing queue and modal; update focused tests and architecture evidence.

## Capabilities

### Modified Capabilities

- Object Storage folder browsing, inline media preview, and authenticated thumbnail access.
- Object Storage quarantined upload validation, integrity verification, and progress reporting.

## Impact

Affects `backend/app/api/object_storage`, `backend/app/services/s3.py`, the browser/queue components under `frontend/src/lib`, focused tests, and architecture documentation. No new UI palette or unauthenticated object URL. Existing Swift and S3 clients retain their ownership boundary; thumbnail requests use the caller-scoped Swift connection.
