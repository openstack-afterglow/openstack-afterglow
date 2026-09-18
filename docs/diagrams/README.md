# Afterglow interactive diagrams

각 HTML은 독립 실행형 Archify Viewer이다. Light/dark 전환, guided views, relationship tracing, pan/zoom, search, presentation, export를 제공한다. 본문은 현재 저장소 source와 API contract를 기준으로 작성했으며, 각 `*.visual-check.json`과 contact sheet는 해당 HTML의 browser containment evidence다.

## System and frontend

| Diagram | Covers | Source evidence |
| --- | --- | --- |
| [Platform architecture](afterglow-platform.html) | Browser, BFF, OpenStack, data ownership, sibling-service boundaries | `ARCHITECTURE.md`, `backend/app/main.py` |
| [Authenticated API request](afterglow-authenticated-api.html) | Login, refresh, project rescope, caller-scoped resource request | `backend/app/api/identity/`, `frontend/src/lib/api/client.ts` |
| [Frontend behavior](afterglow-frontend-behavior.html) | Route admission, state, API client, SSE, terminal authentication handling | `frontend/src/hooks.server.ts`, `frontend/src/lib/api/client.ts` |

## Backend API flows

| Diagram | API contract and boundary | Source evidence |
| --- | --- | --- |
| [Drover K3s cluster provisioning](afterglow-drover-cluster-provisioning.html) | `POST /api/v1/k3s/clusters` BFF proxy → Drover `/v1/clusters`; K3s VM legacy callback → Drover `/v1/callback`; agent provisioning to `ACTIVE`/`ERROR` | `backend/app/api/drover/`, `backend/app/services/service_proxy.py`, `backend/tests/contracts/test_drover_proxy.py`, `docs/drover-workflow.md` |
| [VM provisioning](afterglow-vm-provisioning.html) | `POST /api/v1/instances/async`; placement/GPU admission, optional Manila, Cinder, Nova, Neutron, SSE terminal messages, reverse cleanup | `backend/app/api/compute/instances.py`, `docs/api/instances.md` |
| [Lumen durable run](afterglow-lumen-durable-run.html) | Completion `202` descriptor, journal/provider ownership, events subscription, approval/cancel forwarding | `docs/api/chat.md`, `frontend/src/lib/api/chatStream.ts`, `backend/app/api/lumen/` |
| [Lumen BFF transport](afterglow-lumen-bff-transport.html) | Caller-scoped internal endpoint discovery, forwarded headers, unbuffered raw SSE, separate public OpenAI/Anthropic-compatible SDK surface | `backend/app/services/service_proxy.py`, `backend/app/api/lumen/`, `backend/tests/contracts/test_lumen_proxy.py`, `docs/api/chat.md` |

`/api/v1/chat/*` is the browser BFF surface. External OpenAI/Anthropic-compatible `/v1` runtime endpoints belong to Lumen and are not mounted by Afterglow.
