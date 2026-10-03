## MODIFIED Requirements

### Requirement: Client tunnel settings are editable without rotating issued keys
The Waygate dashboard SHALL send DNS, optional MTU, and PersistentKeepalive through the authenticated project-scoped BFF on client issuance and edit. DNS and keepalive SHALL each offer explicit server inheritance or direct override; inherited values are displayed read-only, and custom DNS null/keepalive zero are valid overrides. MTU remains per-client. The dashboard SHALL indicate whether a server-generated PSK is present without displaying it in lists, and explain that changed settings require downloading or scanning and reimporting the updated configuration on installed devices. Existing clients SHALL NOT gain a PSK or rotate a private key merely by being listed or edited.

#### Scenario: Inherit current server settings
- **WHEN** a member issues a client with DNS and keepalive inherited, then changes the server defaults
- **THEN** the client list and subsequent downloaded/QR configuration show the new effective DNS and keepalive without rotating its private key or PSK, while the already installed device is not silently reconfigured

#### Scenario: Override and restore inheritance
- **WHEN** a member switches an existing client to custom DNS omitted and keepalive zero, then later restores server inheritance
- **THEN** the first PATCH stores explicit null DNS and zero keepalive, and the later PATCH sends only the true inheritance flags; MTU and key material remain unchanged

### Requirement: Client traffic is grounded in recent agent reports
The Waygate dashboard SHALL poll peer reports approximately once per second only for a visible selected server in the current authenticated project. It SHALL interpret peer byte counters from the client perspective (client RX equals gateway TX and client TX equals gateway RX), derive rates only from distinct, timely, successive server-receipt reports, retain at most 60 samples per client within the selected server and project, and show unknown rates instead of fabricated activity for missing, stale, out-of-order, duplicated, or reset counters. Polls SHALL stop when the workspace is hidden or unmounted, and in-flight responses from previous scopes SHALL be discarded.

#### Scenario: Fresh traffic report arrives
- **WHEN** two successive, recent agent reports with increasing peer counters arrive for the selected client
- **THEN** the displayed RX/TX totals use the client perspective and rates use the byte deltas divided by elapsed report time

#### Scenario: Reports stop, repeat, reset, or scope changes
- **WHEN** the report expires, duplicates or precedes the latest sample, counters reset, the page becomes hidden, or the user switches server or project
- **THEN** no synthetic positive rate appears; samples from the previous scope are not attributed to the current scope and hidden pages stop polling
