// Afterglow Design System — Semantic status tone map
// Maps OpenStack resource statuses to 5 design-system tones.
// pulse=true on statuses that represent an in-progress transition.

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
  NEW:                 { tone: 'info', pulse: true, label: '대기 중' },

  // MCP access levels are stable authority scopes, not resource lifecycle states.
  read:                { tone: 'info', label: '읽기' },
  manage:              { tone: 'warning', label: '관리' },

  // warning + pulse — active transitions (building, deleting, detaching)
  BUILD:               { tone: 'warning', pulse: true },
  PENDING:             { tone: 'warning', pulse: true },
  PENDING_CREATE:      { tone: 'warning', pulse: true },
  PENDING_UPDATE:      { tone: 'warning', pulse: true },
  CREATING:            { tone: 'warning', pulse: true },
  creating:            { tone: 'warning', pulse: true },
  PENDING_DELETE:      { tone: 'warning', pulse: true },
  DELETING:            { tone: 'warning', pulse: true },
  chat_running:        { tone: 'info', pulse: true, label: '실행 중' },
  queued:             { tone: 'neutral', label: '대기 중' },
  awaiting_input:     { tone: 'warning', pulse: true, label: '입력 대기' },
  waiting_children:   { tone: 'info', pulse: true, label: '하위 작업 대기' },
  finalizing:         { tone: 'info', pulse: true, label: '마무리 중' },
  complete:           { tone: 'success', label: '완료' },
  completed:          { tone: 'success', label: '완료' },
  canceled:           { tone: 'neutral', label: '취소됨' },
  deleting:            { tone: 'warning', pulse: true },
  detaching:           { tone: 'warning', pulse: true },
  DETACHING:           { tone: 'warning', pulse: true },
  retyping:            { tone: 'warning', pulse: true },

  // warning — stopped, non-transitioning
  SHUTOFF:             { tone: 'warning' },
  stopped:            { tone: 'warning' },
  stop:               { tone: 'warning', label: 'stopped' },

  // neutral + pulse — Trove 비동기 삭제 진행 중 (ACTIVE → SHUTDOWN → 레코드 제거)
  SHUTDOWN:            { tone: 'neutral', pulse: true, label: '삭제 중' },

  // danger — errors / failures
  ERROR:               { tone: 'danger' },
  error:               { tone: 'danger', label: '오류' },
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
  downloading:         { tone: 'info', pulse: true, label: '다운로드 중' },
  converting:          { tone: 'info', pulse: true, label: '변환 중' },
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
  revoked:             { tone: 'neutral', label: '폐기됨' },
  expired:             { tone: 'neutral', label: '만료됨' },

  // 라이브러리 빌드 의미 상태
  ready:               { tone: 'success', label: '빌드 완료' },
  building:            { tone: 'warning', pulse: true, label: '빌드 중' },
  failed:              { tone: 'danger',  label: '빌드 실패' },
  none:                { tone: 'neutral', label: '미빌드' },
};

const FALLBACK: StatusStyle = { tone: 'neutral' };

export function getStatusStyle(status: string | null | undefined): StatusStyle {
  if (!status) return FALLBACK;
  return STATUS_STYLES[status] ?? FALLBACK;
}
