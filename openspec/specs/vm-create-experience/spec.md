# VM Create Experience Specification

## Purpose
Define the VM wizard's image identity and selection, quota additions, verified GitHub reuse, monotonic deployment observations, instance-list completion navigation, and explicit canonical GitHub SSH metadata without changing authentication, allocation, or guest bootstrap ownership.
## Requirements
### Requirement: VM image selection separates repository and tag
The VM wizard SHALL group current image choices by canonical repository name. Selecting a repository SHALL expose its concrete current tags without selecting an unrelated image UUID. OS and search filters SHALL retain the shared catalog identity rules.

#### Scenario: One repository has multiple current tags
- **WHEN** the catalog contains Ubuntu tags `22.04` and `24.04`
- **THEN** the name chooser shows one Ubuntu repository and selecting it shows both concrete tag choices

#### Scenario: A current tag is inactive
- **WHEN** the newest upload for a tag is inactive but an older upload is active
- **THEN** the current choice remains disabled and is not replaced by the older active UUID

#### Scenario: A historical or missing UUID remains selected
- **WHEN** refresh or filtering no longer presents the already-selected UUID as a current choice
- **THEN** the wizard preserves its identity and shows the retained-selection warning rather than silently changing it

### Requirement: Ordinary image choices show useful information in newest-upload order
Repository cards and tag choices SHALL sort by newest upload first, with missing or invalid upload timestamps last. Normal choices SHALL omit SHA, raw format, and active/current decoration while retaining repository, tag, OS, size, upload date, and explicit unavailability information where applicable.

#### Scenario: Newer and undated uploads coexist
- **WHEN** repositories or tags have different upload dates and an undated entry
- **THEN** newer dated entries precede older ones and the undated entry is last

### Requirement: Quota preview distinguishes existing allocation and the requested VM
VM, vCPU, RAM, and finite DISK previews SHALL distinguish existing allocation, requested addition, and unused space with a named legend and current-to-projected values. Meter percentages SHALL stay finite and within the available track. Disk addition SHALL use the configured new boot-volume size, zero for existing-volume reuse, and flavor disk only when a standalone picker omits the boot-volume size. Numeric readouts SHALL remain inside their cells at mobile and wider breakpoints.

#### Scenario: A new boot volume overrides flavor disk
- **WHEN** the selected flavor has 20GB disk but the new boot volume is configured as 80GB and current disk allocation is 1024GB
- **THEN** DISK projects 1104GB and distinguishes the additional 80GB from existing allocation

#### Scenario: An existing boot volume is reused
- **WHEN** the wizard boots from an existing volume
- **THEN** the DISK preview adds zero GB regardless of the selected flavor disk

#### Scenario: A finite limit is zero or exceeded
- **WHEN** an allocation or request reaches or exceeds a finite quota
- **THEN** the meter remains finite and bounded and the displayed requested values and critical state are retained

### Requirement: Re-selecting the same verified GitHub identity retains readiness
A recent-user selection matching the current normalized GitHub login SHALL preserve the verified canonical profile and next-step readiness. Choosing a different login SHALL require verification, and stale responses from a previous identity or scope SHALL NOT replace the active result.

#### Scenario: The same recent login is clicked twice
- **WHEN** a verified recent GitHub login is selected again with equivalent case or leading-at normalization
- **THEN** the canonical profile remains verified and progression stays available

### Requirement: Deployment time is a live monotonic observation
The deployment store SHALL update total elapsed time and the active observed stage every second independently of SSE arrival. Repeated reports of the same stage and older server elapsed values SHALL NOT restart either clock. Completed observed stages SHALL retain their measured duration; pending stages SHALL NOT receive fabricated durations or progress.

#### Scenario: The SSE connection remains silent
- **WHEN** deployment is active and no new SSE event arrives for several seconds
- **THEN** total and active-stage elapsed time continue increasing while the reported stage and percentage remain unchanged

#### Scenario: A new stage reports stale elapsed time
- **WHEN** a stage transition arrives with a server elapsed value below the local total
- **THEN** the previous stage duration freezes, the new stage clock starts, and the total does not decrease

### Requirement: Deployment clocks respect terminal and store lifetime boundaries
Success, failure, stream end, and store destruction SHALL stop the clock. Retry SHALL initialize a new observation. Late completion after destruction SHALL NOT navigate.

#### Scenario: Deployment terminates or is destroyed
- **WHEN** deployment completes, fails, reaches stream end, or its store is destroyed
- **THEN** no further elapsed-time ticks are applied

#### Scenario: The user retries after failure
- **WHEN** a new deployment attempt begins
- **THEN** its total and stage observations start independently of the previous attempt

### Requirement: Successful creation navigates to the matching instance list
User SSE, mock, and squashfs success SHALL navigate to `/dashboard/compute/instances`; administrator success SHALL navigate to `/admin/instances`. Success SHALL NOT navigate to either overview page.

#### Scenario: Creation succeeds in either mode
- **WHEN** the current creation reports a completed instance
- **THEN** the wizard closes and the matching user or administrator instance list is the destination

### Requirement: GitHub SSH identity is explicit Nova metadata
User synchronous and SSE creation, administrator SSE creation, and squashfs consumption SHALL persist the verified canonical login in `afterglow_github_login` and declare `afterglow_ssh_access_mode="github"`. Shared Nova projection SHALL expose `ssh_access_mode` and `github_login` to instance responses. Basic information SHALL display `GitHub SSH` and the full `@login` only for a declared nonempty GitHub identity, wrapping long values within the cell. Existing keypair, owner, health, library, and scheduling metadata SHALL remain intact. Readers SHALL NOT infer a GitHub login from old user-data or an absent/unknown mode, and SSH key material SHALL NOT be persisted in these metadata keys.

#### Scenario: Verified canonical case is retained
- **WHEN** verification resolves the requested username to `OctoCat` before any supported creation path
- **THEN** Nova metadata and list/detail projection retain `OctoCat` and basic information displays `@OctoCat`

#### Scenario: An old or keypair-only instance is read
- **WHEN** the instance has no recognized GitHub mode and login
- **THEN** the GitHub fields do not declare an identity and basic information retains its keypair or empty placeholder

### Requirement: Preparation owns the entire VM panel surface
The VM creation preparation state SHALL display the existing authored glyph scene edge-to-edge across the available panel width and height, without preparation-only outer padding, a framed artwork card, visible external heading, or help/footer row. The loaded wizard and administrator target-selection layout SHALL retain their existing chrome and spacing. The existing accessible panel close action SHALL remain available as a 44px integrated overlay with the existing keyboard dismissal and focus lifecycle.

#### Scenario: Initial dependencies are pending
- **WHEN** the current-scope VM composer resources, GPU snapshot, history or create-capacity catalog are not ready
- **THEN** the scene fills the preparation surface, the form/stepper/progression footer are absent, and actual pending work remains readable at the exact analytic ring center

#### Scenario: Preparation completes or the user closes it
- **WHEN** the final required dependency settles successfully
- **THEN** the ordinary wizard appears with its existing heading, spacing, stepper and footer
- **WHEN** the user activates the overlay close or Escape while preparation is pending
- **THEN** the existing close lifecycle runs without issuing a cloud mutation

### Requirement: Authored scene follows live semantic appearance
The scene SHALL derive its base, glyph and status colors from the existing semantic surface/accent/ink tokens and the current light/dark appearance. Root class/style updates SHALL refresh cached canvas colors and redraw the current elapsed frame without remounting, resetting elapsed time, or reading computed styles per animation frame. The authored source assets, glyph algorithm, analytic geometry and bounded rendering cadence/storage SHALL remain unchanged.

#### Scenario: Appearance or palette changes during a pending scene
- **WHEN** the console applies a light/dark class change or root semantic palette style update
- **THEN** canvas and DOM status update in place using the same geometry and dependency state

#### Scenario: Motion is reduced or the scene is settled
- **WHEN** an appearance update arrives while animation is paused by reduced motion or settled work
- **THEN** the current static frame updates without enabling a repeating animation
- **WHEN** the component unmounts
- **THEN** RAF, palette/size/intersection observations and media/visibility listeners are released and subsequent palette changes do not redraw it

### Requirement: Full-surface preparation retains genuine accessible lifecycle state
The decorative canvas SHALL remain hidden from assistive technology. The actual first pending task SHALL remain a polite atomic DOM status at the shared analytic center; every lane SHALL retain its accessible pending/complete/failed state. Failure details and explicit retry SHALL remain reachable inside the scene without moving the status center or waiting for other busy lanes to settle. Only failed lanes SHALL retry on explicit user action, and same-scope background refresh SHALL NOT replace an already editable form. Scope/readiness loss and reopen SHALL require fresh preparation. Canvas unavailability and forced colors SHALL retain real text, errors, retry and close.

#### Scenario: A dependency fails while another remains pending
- **WHEN** one lane fails and another is still pending
- **THEN** the status names genuine pending work, the failure Alert names the failed lane, and neither live region is under an aria-busy ancestor

#### Scenario: Preparation has already completed
- **WHEN** same-scope background refresh becomes pending or fails
- **THEN** the existing editable form and draft remain mounted rather than showing preparation again

#### Scenario: Rendering is unavailable
- **WHEN** canvas context creation fails or forced colors hides decoration
- **THEN** the real status, accessible name/description, task states, explicit error/retry and integrated close remain available

