## ADDED Requirements

### Requirement: Admin can change compute scheduling state without changing host liveness
The system SHALL let a system administrator enable or disable only the `nova-compute` service associated with a selected hypervisor. Disabling SHALL require a reason; changing service status SHALL NOT change the host's `up/down` state or automatically move workloads. The list and detail views SHALL distinguish liveness from scheduling.

#### Scenario: Disable a live compute host
- **WHEN** a system administrator confirms disabling an `up/enabled` hypervisor and provides a nonblank reason
- **THEN** the matching `nova-compute` service becomes disabled, the reason is retained, the view refreshes, and workloads remain in place until a separate operation is requested

#### Scenario: Unauthorized or mismatched service
- **WHEN** a non-admin requests service control or a selected hypervisor has no matching `nova-compute` service
- **THEN** no Nova service state is changed and the operation reports the appropriate denial or missing-service error

### Requirement: Admin can request migration of all instances on a live disabled host
The system SHALL expose a separate confirmed whole-host migration action only for `up/disabled` source hosts. It SHALL enumerate all current source instances, request live migration for eligible active instances and cold migration for eligible stopped instances, and report each requested, skipped, or failed operation without claiming completion.

#### Scenario: Host contains more than one API page of instances
- **WHEN** a system administrator confirms a whole-host migration on an `up/disabled` hypervisor whose instances span multiple Nova pages
- **THEN** every page is processed and each current source instance has a visible per-instance outcome

#### Scenario: Source is not eligible
- **WHEN** a migration request targets an enabled or down host
- **THEN** the server rejects the whole-host operation without dispatching instance migrations

### Requirement: Evacuating a down host requires fencing acknowledgement
The system SHALL expose whole-host evacuation for `down` source hosts only after the administrator confirms that the source is fenced. It SHALL NOT infer fencing from Nova heartbeat state, force Nova `forced_down`, or imply an accepted evacuation request has completed.

#### Scenario: Down host is not confirmed fenced
- **WHEN** a system administrator attempts whole-host evacuation without explicitly acknowledging source fencing
- **THEN** no evacuation is submitted and the risk is explained

#### Scenario: Fenced down host has eligible and ineligible instances
- **WHEN** an administrator confirms fencing and evacuation for a down hypervisor with mixed instance states
- **THEN** eligible instances receive individual evacuation requests, unsupported or stale instances are skipped, failures are shown per instance, and accepted requests are labeled as pending relocation rather than completion
