## ADDED Requirements

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
