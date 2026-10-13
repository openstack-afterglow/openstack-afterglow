## ADDED Requirements

### Requirement: Versioned GPU API handoff and separate dashboard lifecycle

The GPU API handoff SHALL link existing native/BFF contracts, immutable Drover source/artifacts and separately recorded test/live evidence. It SHALL distinguish API delivery from downstream dashboard implementation and SHALL leave the dashboard checklist pending and the change unarchived until that implementation is verified. This handoff change SHALL NOT modify Afterglow runtime, version, permissions or existing guest Nodes/CSI installations.

#### Scenario: API release has fresh live receipts but dashboard work remains
- **WHEN** Drover has completed publication, rollout, GPU execution, native CSI mount/I/O, natural scale-in and owned cleanup
- **THEN** the handoff records the exact version, source, operation/resource IDs and observed evidence without reusing older-version success
- **AND** dashboard implementation/verification/deployment tasks remain pending and the change remains unarchived

#### Scenario: A runtime step was not exercised
- **WHEN** a step has only source or synthetic/local verification
- **THEN** the handoff labels that boundary and does not promote it to native GPU, mount or dashboard success

### Requirement: Existing GPU nodegroup configuration and opt-out semantics

The separately implemented dashboard SHALL expose existing nodegroup image, allowed labels and explicit GPU NoSchedule taints without inventing a GPU-only native endpoint. It SHALL preserve explicit Stampede false, node_count/min/max constraints, default server/initial-agent exclusions, reserved GPU labels and existing resource/project ownership. It SHALL NOT imply automatic taints, existing Node retrofit or quota/authority expansion.

#### Scenario: User explicitly disables automatic scaling
- **WHEN** a user selects a GPU flavor and sets Stampede false
- **THEN** the submitted boolean remains false rather than being overwritten by a GPU preset
- **AND** zero capacity is not presented as demand-driven automatic provisioning

#### Scenario: Dedicated GPU preset is chosen
- **WHEN** the user selects a compatible allowed VM image and an explicit dedicated GPU preset
- **THEN** the existing image_id and nvidia.com/gpu=true:NoSchedule taint fields are sent with valid node_count/min/max
- **AND** reserved afterglow.io/gpu labels are not user-overridden and existing guest configuration is not represented as retrofitted

### Requirement: Verified normalized GPU metadata boundary

The dashboard owner SHALL first establish a verified existing metadata path for normalized GPU type display. GPU count, normalized type and actual allocatable capacity SHALL remain distinct. Missing/error/mixed metadata SHALL NOT be rendered as confirmed CPU, an arbitrary GPU type or available capacity. Drover's resolver correction SHALL NOT be assumed to change Afterglow's separate flavor catalog or add a new native response field.

#### Scenario: Flavor metadata cannot be confirmed
- **WHEN** catalog metadata is missing, fails or does not identify one valid GPU type
- **THEN** the dashboard reports the type as unconfirmed and does not synthesize a selector or CPU/GPU capacity claim
- **AND** any needed API/schema expansion remains a separately approved scope

#### Scenario: A single GPU type is verified
- **WHEN** the approved metadata path confirms RTX-3060-LHR as the sole GPU type
- **THEN** the helper uses the shared RTX3060LHR normalization contract while excluding audio/non-GPU PCI functions
- **AND** its selector agrees with the effective nodegroup accelerator label rather than an unverified flavor-name guess

### Requirement: Complete GPU manifest and caller-authorized submission guidance

The separately implemented manifest helper SHALL include normalized accelerator selection, nvidia.com/gpu requests and limits, nvidia RuntimeClass and matching explicit toleration together. It SHALL direct the caller to the standard Kubernetes API with the issued credential grade/RBAC. It SHALL NOT invent Drover Pod/Deployment/PVC creation APIs or elevate a cluster editor to workload/admin authority.

#### Scenario: One GPU workload is requested
- **WHEN** a verified dedicated RTX3060LHR group is used for a one-GPU manifest
- **THEN** the YAML contains accelerator=RTX3060LHR, GPU request/limit1, runtimeClassName nvidia and Equal/true/NoSchedule GPU toleration
- **AND** metadata labels alone are not presented as a device request

#### Scenario: Caller lacks Kubernetes workload write authority
- **WHEN** the caller can edit cluster configuration but lacks the issued grade/RBAC for workload writes
- **THEN** the helper describes the actual credential/permission boundary and does not submit with a service/admin fallback

### Requirement: CSI bootstrap order and honest durable completion

The dashboard guidance SHALL distinguish Pending PVC from capacity demand, GPU Ready from actual allocatable/execution, CSI plugin Ready from successful mount/I/O, and API/SSE acknowledgement from durable operation completion. It SHALL describe any native provider-network prerequisite within the supported VM/API ownership boundary. Cleanup/scale-in guidance SHALL retain existing idle/cooldown/min/max, PDB, local-storage, PVC and control-plane guards without force/reset or quota/authority bypass.

#### Scenario: GPU plus unbound PVC is requested at zero capacity
- **WHEN** a workload is blocked by unbound storage on a zero-sized GPU group
- **THEN** the helper explains that PVC Pending is not Stampede demand and describes PVC-free or explicit-capacity bootstrap before native Cinder RWO/Manila NFS RWX verification
- **AND** it does not claim an unsupported autoscale-node interface endpoint or automatic provider NIC/guest patch

#### Scenario: Operation succeeds before actual workload readiness
- **WHEN** the durable operation is SUCCEEDED but the GPU Pod, allocatable device or CSI mount is not yet verified
- **THEN** the UI preserves those separate states rather than claiming GPU or storage success
- **AND** nullable durable event messages and sequence/phase/payload are preserved rather than fabricated

#### Scenario: Workload and disposable storage have been cleaned
- **WHEN** the owner removes only that test's workload/PVCs and waits for normal scale-in
- **THEN** existing 600-second idle and 300-second cooldown plus min/max/drain guards remain in force
- **AND** success requires the relevant durable result and actual resource absence rather than manually forcing desired count or hiding a blocked reason
