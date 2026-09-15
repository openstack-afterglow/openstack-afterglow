export interface Volume {
  id: string;
  name: string;
  status: string;
  size: number;
  volume_type: string | null;
  attachments: Record<string, unknown>[];
  bootable?: boolean;
  volume_image_metadata?: Record<string, string> | null;
}

export interface VolumeBackup {
  id: string;
  name: string;
  description: string | null;
  volume_id: string;
  status: string;
  size: number;
  created_at: string | null;
  is_incremental: boolean;
  has_dependent_backups: boolean;
}

export interface Snapshot {
  id: string;
  name: string;
  status: string;
  volume_id: string;
  size: number;
  description: string;
  created_at: string | null;
}

export interface VolumeSnapshot {
  id: string;
  name: string;
  status: string;
  volume_id: string;
  size: number;
  description: string;
  created_at: string | null;
  project_id?: string;
}

export interface AdminVolume {
  id: string;
  name: string;
  status: string;
  size: number;
  project_id: string | null;
  created_at: string | null;
  bootable?: boolean;
  project_name?: string;
}

export interface AdminVolumeStatusCount {
  status: string;
  count: number;
}

export interface AdminVolumeStatusSummary {
  total: number;
  statuses: AdminVolumeStatusCount[];
}

export interface AdminVolumeDetail {
  id: string;
  name: string;
  status: string;
  size: number;
  volume_type: string;
  project_id: string | null;
  attachments: { server_id: string; device: string; id: string }[];
  created_at: string | null;
  description: string;
  bootable: boolean | null;
  encrypted: boolean | null;
  multiattach: boolean | null;
  metadata: Record<string, string>;
}

export type VolumeDeleteRootCause =
  | 'already_deleted'
  | 'api_absent_backend_present'
  | 'attached_volume_delete_blocked'
  | 'dependent_resource_present'
  | 'authentication_scope_failed'
  | 'authorization_denied'
  | 'dependency_unknown'
  | 'deleting_in_progress'
  | 'backend_lookup_unknown'
  | 'backend_inconsistent'
  | 'backend_present_consistent'
  | 'backend_absent_record_only'
  | 'rbd_name_mapping_missing'
  | 'recoverable_backend_unverified'
  | 'normal_delete_possible'
  | 'not_recoverable_status';

export type VolumeDeleteRecoveryStatus =
  | 'deleted'
  | 'already_deleted'
  | 'delete_submitted'
  | 'backend_residue'
  | 'backend_unverified'
  | 'blocked'
  | 'failed';

export type VolumeDeleteRecoveryAction =
  | 'diagnose'
  | 'restore_name_mapping'
  | 'verify_name_mapping'
  | 'recheck_state'
  | 'force_delete'
  | 'reset_attach_status'
  | 'verify_after_force_delete'
  | 'backend_verify'
  | 'cleanup_stale_name_mapping'
  | 'quota_verify';

export type VolumeDeleteRecoveryStepStatus = 'success' | 'skipped' | 'failed';
export type VolumeDeleteCheckState = 'present' | 'absent' | 'unknown';
export type VolumeDeleteCheckName =
  | 'auth_preflight'
  | 'volume_attachments'
  | 'cinder_attachments'
  | 'nova_attachments'
  | 'snapshots'
  | 'backups'
  | 'clone_volumes'
  | 'group_or_migration'
  | 'backend_fsid'
  | 'rbd_name_mapping'
  | 'rbd_directory_entry'
  | 'rbd_image_by_name'
  | 'rbd_image_by_id'
  | 'rbd_header'
  | 'rbd_object_map'
  | 'rbd_watchers'
  | 'rbd_snapshots'
  | 'rbd_parent_child_link'
  | 'rbd_trash'
  | 'rbd_data_objects';

export interface VolumeDeleteMessage {
  id: string | null;
  event_id: string | null;
  request_id: string | null;
  message_level: string | null;
  resource_uuid: string | null;
  resource_type: string | null;
  user_message: string | null;
  created_at: string | null;
}

export interface VolumeDeleteDependency {
  id: string;
  status: string | null;
  name: string | null;
  kind: 'snapshot' | 'backup';
}

export interface VolumeDeleteCheck {
  name: VolumeDeleteCheckName;
  state: VolumeDeleteCheckState;
  detail: string | null;
}

export interface VolumeDeleteBackendInspection {
  mode: 'unavailable' | 'inspected' | 'unknown';
  classification:
    | 'not_inspected'
    | 'consistent'
    | 'name_mapping_missing'
    | 'absent'
    | 'stale_name_mapping_only'
    | 'inconsistent'
    | 'unknown';
  pool: string | null;
  image_name: string | null;
  image_id: string | null;
  size_bytes: number | null;
  order: number | null;
  parent_spec: string | null;
}

export interface VolumeDeleteDiagnostic {
  volume_id: string;
  status: string | null;
  project_id: string | null;
  name: string | null;
  size_gb: number | null;
  backend_host: string | null;
  updated_at: string | null;
  attachments: Record<string, unknown>[];
  dependencies: VolumeDeleteDependency[];
  messages: VolumeDeleteMessage[];
  checks: VolumeDeleteCheck[];
  backend: VolumeDeleteBackendInspection;
  root_cause_code: VolumeDeleteRootCause;
  confidence: 'high' | 'medium' | 'low';
  summary: string;
  evidence: string[];
  recommended_action: string;
  recovery_available: boolean;
}

export interface VolumeDeleteRecoveryStep {
  action: VolumeDeleteRecoveryAction;
  status: VolumeDeleteRecoveryStepStatus;
  detail: string | null;
}

export interface VolumeDeleteRecoveryResult {
  volume_id: string;
  status: VolumeDeleteRecoveryStatus;
  verified_deleted: boolean;
  final_status: string | null;
  backend_verification: 'verified' | 'unavailable' | 'residue' | 'unknown';
  quota_verification: 'verified' | 'mismatch' | 'unavailable';
  diagnostic: VolumeDeleteDiagnostic;
  steps: VolumeDeleteRecoveryStep[];
}
