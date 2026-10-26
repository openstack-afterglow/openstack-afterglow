# Afterglow Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

- **Primary:** general cloud consumers, including developers and organizations using OpenStack self-service. Researchers and practical-training teams are an important use case, not the limit of the audience.
- **Supporting:** project/domain managers and cloud operators responsible for membership, permissions, quotas, availability and infrastructure observation. Their existing capabilities must be preserved without making every consumer task depend on operator knowledge.
- This priority was confirmed by the product owner during Impeccable init.

## Product Purpose

Provide a coherent, project-scoped workspace connecting cloud infrastructure and AI work. Users prepare and operate their resources, access enabled AI capabilities and understand usage and state without navigating unrelated consoles for each task.

Success means completing the intended task within the user's actual permissions, quota and service availability, with clear next actions and honest outcomes. A runnable VM, accepted provisioning request, ready application and verified workload are different states.

## Positioning

The owner-confirmed emphasis is an **integrated cloud-and-AI workspace**, rather than only a modern replacement for an OpenStack administration console. Afterglow connects OpenStack resource management with project-authorized Kubernetes and Lumen workflows through a common web experience. Institution-operated/on-premises deployment remains a supported context, not the sole audience or product definition.

## Operating Context

- Users sign in and work within authorized projects. Account identity, organization/domain membership and project authority are distinct; the interface should not require ordinary users to understand internal identity-domain wiring.
- A typical cloud workflow selects a project, checks available resources/quota, configures compute/storage/network inputs, starts an operation and follows its actual state. Operators manage access and capacity through separate privileged surfaces.
- Kubernetes provisioning and AI work depend on enabled companion services, configured resources/models and current authorization. Do not present a disabled integration as available.
- The browser is a SvelteKit interface; the FastAPI backend owns cloud operations and authorization. Independently deployed Drover, Lumen, Waygate and Palimpsest retain their own service ownership. ARCHITECTURE.md is the implementation authority.
- Development and production deployments are separate evidence. A local fixture or passing test is not proof of live cloud readiness or successful user authentication.

## Capabilities and Constraints

- Project-scoped compute, images, block/file/object storage, networking, security groups and enabled load-balancer, database, container and secret services.
- Kubernetes provisioning through Drover, project-scoped AI chat/media capabilities through Lumen, and enabled companion-service workflows. Availability is configuration- and policy-dependent, not a promise that every installation exposes every service.
- Identity, project membership, roles, quotas, activity/audit records, monitoring and infrastructure observation are operational capabilities, not decorative dashboard data.
- Enforce project/domain/owner boundaries and distinguish consumer and fixed-executor administrative authority. Never expose provider credentials merely because an operation can read them.
- Destructive actions require explicit scope and appropriate confirmation. Unknown or partial outcomes must not become success, an empty list or an automatic retry.
- Preserve existing behavior, resource identifiers, user data and confirmed access boundaries during design work. Native policy remains authoritative; UI presentation cannot grant permission.
- Palimpsest source and detailed guides exist, but public landing copy must not advertise experiment recording, preservation, forking or reuse as generally available. Capability claims need current implementation and deployment evidence.
- Korean is the source/default language. Existing localized interfaces, keyboard access and mobile web usage are part of the product rather than separate native applications.

## Brand Commitments

- Keep the Afterglow name and the installation's configured site identity/branding precedence.
- Retain existing supplied logo, symbol and favicon assets unless an explicit identity change is approved.
- Product copy should be direct, technically accurate and task-oriented. Preserve meaningful distinctions between unavailable, denied, failed, pending, partial and empty.
- Existing visual identity and interaction rules remain in DESIGN.md and implementation tokens/primitives. This file neither replaces them nor defines palettes, fonts, page concepts or a surface's visitor mode.

## Evidence on Hand

- `README.md` and `README.en.md`: product introduction, supported workflows and the documented DMS Cloud research deployment. This is a repository-reported deployment example, not a claim that init verified its current health.
- `ARCHITECTURE.md`: current implementation ownership and service/data/security boundaries.
- `DESIGN.md`: incumbent visual and interaction authority, public feature-claim limits, accessibility and localization commitments.
- `docs/user-guide.md`, `docs/api-reference.md`, `docs/deployment.md`, `docs/security.md` and `docs/palimpsest.md`: domain and operational documentation.
- `frontend/src/routes/`, `frontend/src/lib/components/` and existing mockup/tutorial fixtures: implemented product surfaces and explicitly synthetic demonstrations.
- `frontend/static/afterglow-logo.svg`, `afterglow-symbol.svg`, `favicon.svg`, `landing/` and `docs/screenshots/`: supplied brand/illustration/reference assets. Screenshots and fixtures must be checked for freshness before becoming visual authority.
- `docs/testing.md` and archived OpenSpec verification receipts: scoped verification evidence and its limits, not universal production acceptance.
- No new customer endorsements, adoption counts, speedups, prices or outcome guarantees were supplied during init; do not invent them.

## Product Principles

1. Optimize ordinary cloud consumers' end-to-end tasks first while preserving complete operator capabilities.
2. Connect cloud and AI workflows through real project context, not a collage of disconnected feature claims.
3. Make authority, resource scope, quota, availability and operation outcomes legible before consequential actions.
4. Represent only observed or explicitly qualified state; unknown is not zero, and accepted is not ready.
5. Reuse established product behavior and shared primitives; visual refinement must not quietly change permissions, data or factual claims.

## Accessibility & Inclusion

- Preserve keyboard operation, visible focus, meaningful control labels and dialog focus containment/restoration.
- Do not communicate state through color or motion alone. Respect reduced-motion preferences and keep actions reachable on mobile web and at 200% zoom.
- Preserve complete localizable messages and accessible names without translating user/resource data, identifiers or operator-authored content.

## Open Decisions

- No numerical adoption, conversion or task-completion targets were agreed during init.
- No additional audience-specific accessibility mandate or new identity/voice direction was requested. Existing DESIGN.md commitments remain applicable.
