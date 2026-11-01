// Afterglow Design System — Semantic status tone map
// Maps OpenStack resource statuses to 5 design-system tones.
// pulse=true on statuses that represent an in-progress transition.
// Labels are getters so every read follows the active interface language (SSR included).

import { t } from '$lib/i18n/ns/status';
import type { SettledSignal } from '$lib/design/characterFormats.js';

export interface StatusStyle {
  tone: 'success' | 'warning' | 'danger' | 'info' | 'neutral';
  pulse?: boolean;
  label?: string;
  /** Settled outcome mark when the status itself means it (e.g. canceled). Tone alone never implies canceled/blocked. */
  signal?: SettledSignal;
}

export type StatusKind = 'resource' | 'server' | 'volume';

export const STATUS_STYLES: Record<string, StatusStyle> = {
  success:             { tone: 'success' },
  started:             { tone: 'info' },
  observed:            { tone: 'neutral' },
  // success — healthy / active
  ACTIVE:              { tone: 'success' },
  active:              { tone: 'success' },
  available:           { tone: 'success' },
  AVAILABLE:           { tone: 'success' },
  Running:             { tone: 'success' },
  running:             { tone: 'success' },
  ENABLED:             { tone: 'success' },
  enabled:             { tone: 'success' },
  ONLINE:              { tone: 'success' },
  UP:                  { tone: 'success' },
  healthy:             { tone: 'success' },
  HEALTHY:             { tone: 'success' },

  // Trove DB 백업 상태
  BUILDING:            { tone: 'warning', pulse: true },
  COMPLETED:           { tone: 'success' },
  NEW:                 { tone: 'info', pulse: true, get label() { return t('waiting'); } },

  // MCP access levels are stable authority scopes, not resource lifecycle states.
  read:                { tone: 'info', get label() { return t('read'); } },
  manage:              { tone: 'warning', get label() { return t('manage'); } },


  // Global Cloud Shell session lifecycle.
  cloud_shell_preparing:   { tone: 'warning', pulse: true, get label() { return t('cloudShellPreparing'); } },
  cloud_shell_authorizing: { tone: 'info', pulse: true, get label() { return t('cloudShellAuthorizing'); } },
  cloud_shell_ready:       { tone: 'success', get label() { return t('cloudShellReady'); } },
  cloud_shell_ending:      { tone: 'warning', pulse: true, get label() { return t('cloudShellEnding'); } },
  cloud_shell_closed:      { tone: 'neutral', get label() { return t('cloudShellClosed'); } },
  cloud_shell_error:       { tone: 'danger', get label() { return t('error'); } },
  // warning + pulse — active transitions (building, deleting, detaching)
  BUILD:               { tone: 'warning', pulse: true },
  PENDING:             { tone: 'warning', pulse: true },
  PENDING_CREATE:      { tone: 'warning', pulse: true },
  PENDING_UPDATE:      { tone: 'warning', pulse: true },
  CREATING:            { tone: 'warning', pulse: true },
  creating:            { tone: 'warning', pulse: true },
  PENDING_DELETE:      { tone: 'warning', pulse: true },
  DELETING:            { tone: 'warning', pulse: true },
  chat_running:        { tone: 'info', pulse: true, get label() { return t('running'); } },
  queued:             { tone: 'neutral', get label() { return t('queued'); } },
  awaiting_input:     { tone: 'warning', pulse: true, get label() { return t('awaitingInput'); } },
  waiting_children:   { tone: 'info', pulse: true, get label() { return t('waitingChildren'); } },
  finalizing:         { tone: 'info', pulse: true, get label() { return t('finalizing'); } },
  complete:           { tone: 'success', get label() { return t('complete'); } },
  completed:          { tone: 'success', get label() { return t('complete'); } },
  canceled:           { tone: 'neutral', signal: 'canceled', get label() { return t('canceled'); } },
  deleting:            { tone: 'warning', pulse: true },
  detaching:           { tone: 'warning', pulse: true },
  DETACHING:           { tone: 'warning', pulse: true },
  retyping:            { tone: 'warning', pulse: true },
  'awaiting-transfer':  { tone: 'warning', get label() { return t('awaitingTransfer'); } },

  // neutral — stopped, non-transitioning
  SHUTOFF:             { tone: 'neutral' },
  stopped:             { tone: 'neutral' },
  stop:                { tone: 'neutral' },

  // neutral + pulse — Trove 비동기 삭제 진행 중 (ACTIVE → SHUTDOWN → 레코드 제거)
  SHUTDOWN:            { tone: 'neutral', pulse: true, get label() { return t('deleting'); } },

  // danger — errors / failures
  ERROR:               { tone: 'danger' },
  error:               { tone: 'danger', get label() { return t('error'); } },
  error_deleting:      { tone: 'danger' },
  error_backing_up:    { tone: 'danger' },
  error_restoring:     { tone: 'danger' },
  error_extending:     { tone: 'danger' },
  FAILED:              { tone: 'danger' },
  DELETE_FAILED:       { tone: 'danger' },
  degraded:            { tone: 'danger' },
  DEGRADED:            { tone: 'danger' },
  unhealthy:           { tone: 'danger' },
  timeout:             { tone: 'danger' },

  // info + pulse — in-progress I/O operations
  attaching:           { tone: 'info', pulse: true },
  ATTACHING:           { tone: 'info', pulse: true },
  extending:           { tone: 'info', pulse: true },
  'backing-up':        { tone: 'info', pulse: true },
  backing_up:          { tone: 'info', pulse: true },
  'restoring-backup':  { tone: 'info', pulse: true },
  restoring_backup:    { tone: 'info', pulse: true },
  downloading:         { tone: 'info', pulse: true, get label() { return t('downloading'); } },
  converting:          { tone: 'info', pulse: true, get label() { return t('converting'); } },
  uploading:           { tone: 'info', pulse: true },

  // info — stable in-use / created states
  in_use:              { tone: 'info' },
  IN_USE:              { tone: 'info' },
  'in-use':            { tone: 'info' },
  Created:             { tone: 'info' },
  ONLINE_STANDBY:      { tone: 'info' },
  NO_MONITOR:          { tone: 'info' },
  SHARED:              { tone: 'info' },

  // neutral — shelved / deleted / revoked or expired authority
  deleted:            { tone: 'neutral' },
  SHELVED:             { tone: 'neutral' },
  SHELVED_OFFLOADED:   { tone: 'neutral' },
  // Octavia 운영 상태 OFFLINE / 라우터 admin-down
  OFFLINE:             { tone: 'neutral' },
  DOWN:                { tone: 'neutral' },
  reserved:            { tone: 'neutral' },
  RESERVED:            { tone: 'neutral' },
  revoked:             { tone: 'neutral', get label() { return t('revoked'); } },
  expired:             { tone: 'neutral', get label() { return t('expired'); } },

  // 라이브러리 빌드 의미 상태
  ready:               { tone: 'success', get label() { return t('buildReady'); } },
  building:            { tone: 'warning', pulse: true, get label() { return t('building'); } },
  failed:              { tone: 'danger',  get label() { return t('buildFailed'); } },
  none:                { tone: 'neutral', get label() { return t('notBuilt'); } },
  PAUSED:              { tone: 'neutral' },
  SUSPENDED:           { tone: 'neutral' },
  REBOOT:              { tone: 'info', pulse: true },
  HARD_REBOOT:         { tone: 'info', pulse: true },
  RESIZE:              { tone: 'info', pulse: true },
  VERIFY_RESIZE:       { tone: 'warning' },
  MIGRATING:           { tone: 'info', pulse: true },
  RESCUE:              { tone: 'warning' },
  SOFT_DELETED:        { tone: 'neutral' },
  saving:              { tone: 'info', pulse: true },
  killed:              { tone: 'danger' },
  deactivated:         { tone: 'neutral' },
};

const FALLBACK: StatusStyle = { tone: 'neutral' };

export function getStatusStyle(status: string | null | undefined, kind: StatusKind = 'resource'): StatusStyle {
  if (!status) return FALLBACK;
  if (kind === 'volume' && status.toLowerCase() === 'available') return { tone: 'neutral' };
  return STATUS_STYLES[status] ?? FALLBACK;
}

const NATIVE_STATUS_LABELS: Record<string, Parameters<typeof t>[0]> = {
  active: 'active', running: 'running', available: 'ready',
  enabled: 'enabled', online: 'online', up: 'online', healthy: 'healthy',
  build: 'creating', building: 'creating', pending: 'waiting', new: 'waiting',
  pending_create: 'creating', creating: 'creating', pending_update: 'updating',
  pending_delete: 'deleting', deleting: 'deleting', detaching: 'detaching',
  retyping: 'retyping', shutoff: 'stopped', stopped: 'stopped', stop: 'stopped',
  error: 'error', error_deleting: 'errorDeleting', error_backing_up: 'errorBackup',
  error_restoring: 'errorRestoring', error_extending: 'errorExtending',
  failed: 'failed', delete_failed: 'errorDeleting', degraded: 'degraded',
  unhealthy: 'unhealthy', timeout: 'timeout', attaching: 'attaching',
  extending: 'extending', backing_up: 'backingUp', restoring_backup: 'restoring',
  uploading: 'uploading', in_use: 'connected', created: 'created',
  online_standby: 'standby', no_monitor: 'notMonitored', shared: 'shared',
  deleted: 'deleted', shelved: 'shelved', shelved_offloaded: 'shelvedOffloaded',
  offline: 'offline', down: 'offline', reserved: 'reserved',
  paused: 'paused', suspended: 'suspended', reboot: 'rebooting', hard_reboot: 'rebooting',
  resize: 'resizing', verify_resize: 'verifyResize', migrating: 'migrating',
  rescue: 'rescue', soft_deleted: 'softDeleted', saving: 'saving',
  killed: 'killed', deactivated: 'deactivated',
};

/** Friendly interface text; callers keep the exact native code separately for diagnosis. */
export function getStatusLabel(status: string | null | undefined, kind: StatusKind = 'resource'): string {
  if (!status?.trim()) return t('unknown');
  const normalized = status.toLowerCase().replaceAll('-', '_');
  if (kind === 'server' && normalized === 'active') return t('running');
  if (kind === 'volume' && normalized === 'available') return t('available');
  const explicit = STATUS_STYLES[status]?.label;
  if (explicit) return explicit;
  const key = NATIVE_STATUS_LABELS[normalized];
  return key ? t(key) : kind === 'resource' ? status : t('unknownCode', { code: status });
}
