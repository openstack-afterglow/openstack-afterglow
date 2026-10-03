## ADDED Requirements

### Requirement: Environment preview explains each step with the matching panel
The landing environment preview SHALL render a console-style scene with four panels — request, policy, resource, and reuse — whose content is specific to the selected scenario (GPU 연구, 클러스터 실습, 공유 데이터). Exactly the panel that belongs to the current step SHALL be active, earlier panels SHALL show a completed state with visible text, and later panels SHALL show an explicit waiting state with visible text rather than a faded copy of their result. The run SHALL start only from an explicit user action, finish in four steps, and expose start, pause, resume, and replay through one persistent control.

#### Scenario: Step advances the matching panel
- **WHEN** the user starts the preview and the run reaches the policy step
- **THEN** the policy panel is the only active panel, the request panel shows a completed state, and the resource and reuse panels show a waiting state

#### Scenario: Scenario-specific resource and reuse result
- **WHEN** the user selects 클러스터 실습 and the run completes
- **THEN** the resource panel shows cluster nodes and their ready state, and the reuse panel shows the saved template, without the GPU instance or shared-data mounts

#### Scenario: Idle preview is legible
- **WHEN** the page loads and the user has not started the preview
- **THEN** every panel shows visible content or a visible waiting label, and no panel relies on reduced opacity alone to communicate its state

#### Scenario: Run lifecycle is preserved
- **WHEN** the user pauses, the page becomes hidden, the preview scrolls out of view, the scenario changes, or the user prefers reduced motion
- **THEN** pausing, hiding, and leaving the viewport stop progression until explicit resume, a scenario change cancels pending progression and returns to idle, and reduced motion shows the completed state immediately

### Requirement: Lifecycle story keeps one continuous scene
The request-to-reuse story SHALL show one scene whose project boundary, members, environment card, and attached network and shared data persist across the 신청, 배정, 관측, and 재사용 steps, while a step-specific detail area presents request contents, quota checks, metrics and activity records, or immutable-layer branching. The active step SHALL be selectable with four buttons at every viewport tier and SHALL follow the reading position on roomy desktop viewports without scroll-linked translation or scaling.

#### Scenario: Selecting a step updates scene, caption, and article
- **WHEN** the user activates the 관측 button
- **THEN** that button reports pressed, the caption names 관측, the matching article is marked active, and the scene shows the metrics and activity detail while the environment card and its attachments remain visible

#### Scenario: Desktop reading position drives the step
- **WHEN** a roomy desktop viewport without reduced motion scrolls so that the 배정 article crosses the activation line
- **THEN** the scene changes to the 배정 step using the shared motion durations

#### Scenario: Compact and reduced-motion fallback
- **WHEN** the viewport is mobile, tablet, or short, or the user prefers reduced motion
- **THEN** all four articles remain readable in normal flow and the step buttons still change the scene

### Requirement: Product preview shows console screens
The product preview SHALL render condensed console screens for the project overview, cluster, and network topology views. Each screen SHALL be labeled as an example, and switching the view SHALL update the screen, route label, and description.

#### Scenario: Switching to the cluster view
- **WHEN** the user selects 클러스터 in the product preview
- **THEN** the preview shows a cluster screen with nodes and their status, the route label reads the cluster route, and the description updates

### Requirement: Landing actions and accessibility remain intact
Every console action on the landing page SHALL link to the supplied console destination. The skip link SHALL move focus to the landing content, the brand SHALL use the runtime site name and logo, and the footer SHALL provide the inquiry e-mail and the repository link. Landing labels SHALL keep AA-safe text colors, and the page SHALL render no raster artwork.

#### Scenario: Console destination is supplied by the route
- **WHEN** the landing page renders with a console destination of `/dashboard`
- **THEN** the navigation, hero, product, and contact console actions all link to `/dashboard`

#### Scenario: Skip link moves focus
- **WHEN** the user activates the skip link
- **THEN** focus moves to the landing content region
