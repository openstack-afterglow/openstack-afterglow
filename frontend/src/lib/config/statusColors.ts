// Afterglow Design System — Semantic status tone map
// Maps OpenStack resource statuses to 5 design-system tones.
// pulse=true on statuses that represent an in-progress transition.
// Labels are getters so every read follows the active interface language (SSR included).

import { t } from '$lib/i18n/ns/status';

export interface StatusStyle {
  tone: 'success' | 'warning' | 'danger' | 'info' | 'neutral';
  pulse?: boolean;
  label?: string;
}

export const STATUS_STYLES: Record<string, StatusStyle> = {
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
  canceled:           { tone: 'neutral', get label() { return t('canceled'); } },
  deleting:            { tone: 'warning', pulse: true },
  detaching:           { tone: 'warning', pulse: true },
  DETACHING:           { tone: 'warning', pulse: true },
  retyping:            { tone: 'warning', pulse: true },

  // warning — stopped, non-transitioning
  SHUTOFF:             { tone: 'warning' },
  stopped:            { tone: 'warning' },
  stop:               { tone: 'warning', label: 'stopped' },

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
  timeout:             { tone: 'danger', label: 'timeout' },

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
};

const FALLBACK: StatusStyle = { tone: 'neutral' };

export function getStatusStyle(status: string | null | undefined): StatusStyle {
  if (!status) return FALLBACK;
  return STATUS_STYLES[status] ?? FALLBACK;
}
