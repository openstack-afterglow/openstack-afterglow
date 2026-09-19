# Palimpsest Admin Dockerfile Build, Manage, and Live Run Workflow

## Why

Palimpsest provides content-addressable, squashfs-backed layered VMs mounted via OverlayFS.
While the backend has core support for inline Dockerfile parsing, build planning (`/api/v1/palimpsest/builds/dockerfile/plan`), and inline build execution (`/api/v1/palimpsest/builds/dockerfile`), the frontend admin interface has gaps:

1. **Restricted to Admin Only**:
   In accordance with security guidelines, Palimpsest build, view, delete, and profile operations must remain strictly within the administrator interface (`/admin/libraries` and `/admin/layers`), inaccessible to regular tenants.
2. **Limited Dockerfile Input Methods**:
   The admin UI only supports GitHub repository URL + commit SHA + path imports, lacking:
   - Direct Dockerfile URL fetching (e.g. from GitHub raw, GitLab, or web URLs).
   - Direct local Dockerfile file upload (drag-and-drop or file picker).
   - Direct inline text editing with preset templates.
3. **Missing Build Plan Preview**:
   Administrators cannot preview parsed instructions (`RUN`, `ENV`, `WORKDIR`), cache hits, or base image compatibility before submitting a build.
4. **Disjointed Build-to-Run Workflow**:
   After a Dockerfile build completes, there is no direct path to immediately launch an active OverlayFS VM instance (consume instance) using the resulting profile.

## What Changes

1. **Backend URL Fetcher Helper (`backend/app/api/palimpsest/builds.py`)**:
   - Add `POST /api/v1/palimpsest/builds/dockerfile/fetch-url` protected by `require_admin`.
   - Normalizes GitHub `/blob/` URLs to raw URLs, prevents SSRF to loopback/link-local/private networks, enforces a 1MiB limit, and returns the Dockerfile content.
2. **Frontend Multi-Mode Dockerfile Input & Plan Preview (`frontend/src/routes/admin/libraries/+page.svelte`)**:
   - Provide mode switching:
     - **URL Mode**: Fetch Dockerfile from any URL via the secure backend helper or GitHub repo import.
     - **File Upload Mode**: Read local `.dockerfile` or `Dockerfile` files in the browser and populate the editor.
     - **Editor Mode**: Direct inline editing with syntax templates (Ubuntu 24.04, Python 3.12, C/C++ Build Tools).
   - Add **Build Plan Preview**: Call `POST /api/v1/palimpsest/builds/dockerfile/plan` and render parsed steps, cache hits, and validation issues in an interactive summary.
   - Add **Inline Build Execution**: Call `POST /api/v1/palimpsest/builds/dockerfile` and monitor build job progress.
3. **Seamless Build-to-Run (Consume) Integration**:
   - When a Dockerfile build completes or an existing profile is selected, provide an action to immediately populate the consume instance form and scroll to the instance creation section.
4. **Mockup Transport & Test Coverage**:
   - Update `frontend/src/lib/mockup/transport.ts` to mock the Palimpsest Dockerfile endpoints.
   - Add unit and regression tests in `backend/tests/test_palimpsest_api.py` and `frontend/src/routes/admin/libraries/__tests__/libraries-layer-workflow.test.ts`.
5. **Architecture & Documentation**:
   - Update `ARCHITECTURE.md` and stamp freshness guard via `python3 scripts/check_architecture.py`.

## Capabilities

### New Capabilities
- `palimpsest-dockerfile-url-fetch`: Secure administrator endpoint to fetch remote Dockerfiles with SSRF protection.
- `palimpsest-dockerfile-multi-mode-build`: Administrator UI supporting URL import, file upload, inline editing, build plan preview, and execution.
- `palimpsest-build-to-run-workflow`: One-click transition from completed layer profile to OverlayFS VM instance launch.

### Modified Capabilities
- `admin-library-page`: Expanded Dockerfile import card into a full-featured Palimpsest Dockerfile build and run studio.

## Impact

- Files:
  - `backend/app/api/palimpsest/builds.py`
  - `backend/tests/test_palimpsest_api.py`
  - `frontend/src/routes/admin/libraries/+page.svelte`
  - `frontend/src/routes/admin/libraries/__tests__/libraries-layer-workflow.test.ts`
  - `frontend/src/lib/mockup/transport.ts`
  - `ARCHITECTURE.md`
- Security: Strictly admin-only; URL fetcher implements SSRF filtering against loopback, link-local, and private addresses.
