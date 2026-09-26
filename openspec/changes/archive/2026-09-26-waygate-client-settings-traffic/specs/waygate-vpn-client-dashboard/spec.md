## ADDED Requirements

### Requirement: Client tunnel settings are editable without rotating issued keys
The Waygate dashboard SHALL send DNS, optional MTU, and PersistentKeepalive through the authenticated project-scoped BFF on client issuance and edit. It SHALL allow zero keepalive and explicit DNS/MTU clearing, indicate whether a server-generated PSK is present without displaying the PSK in client lists, and explain that changed settings require downloading or scanning and reimporting the updated configuration on installed devices. Existing clients SHALL NOT gain a PSK or rotate a private key merely by being listed or edited.

#### Scenario: Issue a configured client
- **WHEN** a project member issues a client with two DNS hosts, an MTU, and PersistentKeepalive 0
- **THEN** the dashboard sends those settings to Waygate, reflects the stored values and PSK presence, and offers a downloadable configuration and browser-generated QR containing the issued configuration

#### Scenario: Clear optional settings
- **WHEN** the member clears DNS and MTU on an existing client and saves while keepalive is 0
- **THEN** the PATCH explicitly sends null for both optional fields and retains keepalive 0, and the subsequently downloaded configuration omits DNS and MTU without changing the client's existing keys

### Requirement: Client traffic is grounded in recent agent reports
The Waygate dashboard SHALL interpret peer byte counters from the client perspective (client RX equals gateway TX and client TX equals gateway RX). It SHALL derive rates only from distinct, timely, successive server-receipt reports, retain at most 60 samples per client within the selected server and project, and show unknown rates instead of fabricated activity for missing, stale, out-of-order, duplicated, or reset counters.

#### Scenario: Fresh traffic report arrives
- **WHEN** two successive, recent agent reports with increasing peer counters arrive for the selected client
- **THEN** the displayed RX/TX totals use the client perspective and rates use the byte deltas divided by elapsed report time

#### Scenario: Reports stop, repeat, reset, or scope changes
- **WHEN** the report expires, duplicates or precedes the latest sample, counters reset, or the user switches server or project
- **THEN** no synthetic positive rate appears; samples from the previous scope are not attributed to the current scope

### Requirement: Real traffic waves remain a secondary background
The dashboard SHALL draw a low-opacity, pointer-inert RX/TX wave behind the legible client traffic metrics only when real contiguous rate samples exist. The two series SHALL have visible labels, use a shared zero baseline, and cease entrance motion under reduced-motion preference. A missing report SHALL NOT animate or generate a substitute wave.

#### Scenario: Valid report series and reduced motion
- **WHEN** the selected client has at least two contiguous rates from real reports and reduced motion is preferred
- **THEN** the background displays both RX/TX series behind readable labeled totals without intercepting client actions, and its report-arrival animation is disabled

#### Scenario: Insufficient data
- **WHEN** fewer than two contiguous rates exist
- **THEN** no traffic wave is rendered and the unknown or pending rate state remains explicit
