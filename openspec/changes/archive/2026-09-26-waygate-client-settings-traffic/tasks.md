## Implementation
- [x] Coordinate upstream settings/traffic contract and update frontend request/response types.
- [x] Implement issuance and editing settings with PSK status, reimport notice, loading/error/focus behavior.
- [x] Implement bounded, scope-isolated traffic sampling and real RX/TX card visualization.
- [x] Add meaningful settings and traffic boundary tests without running checks mid-flight.
- [x] Update Waygate documentation and hand off exact integration commands/routes.

## Release-branch parent integration
- [x] Run release-branch focused and full gate, diagnostics, and Chromium QA with scoped auth/Waygate fixtures at desktop/tablet/mobile and reduced motion; actual authenticated BFF and Linux WireGuard data-plane smoke were separately exercised before branch integration.
- [x] Review integrated release-branch source and architecture, then stamp/check the source snapshot after browser smoke.
