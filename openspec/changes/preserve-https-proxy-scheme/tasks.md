## Implementation Tasks

- [x] Inspect live Uvicorn command/environment and prove controller-origin forwarded HTTPS is ignored; audit related proxy and public URL generation paths.
- [x] Correct Kolla proxy trust with bounded inventory-derived peers and connect existing Kubernetes/Helm trust settings to Uvicorn. Twelve real-app ASGI redirect contracts failed six HTTPS cases before the fix and passed all twelve after; arm64/amd64 actual Uvicorn HTTP confirmed HTTPS, direct HTTP, untrusted header rejection and query preservation.
- [ ] Verify actual containerized runtime behavior, update deployment documentation/changelog/architecture, run the full project gate, and publish a patch release after exact-SHA CI.
- [ ] Back up operator configuration, deploy through canonical Afterglow-tagged Kolla lifecycle, and verify live container settings, public redirects, authentication boundaries and read-only MCP; archive the change.
