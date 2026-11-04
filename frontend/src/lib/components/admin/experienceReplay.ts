export interface ExperienceReplayEvent {
	id: number;
	event_id: string;
	segment_id: string;
	page_view_id: string;
	action_id: string | null;
	caused_by_event_id: string | null;
	trace_id: string | null;
	span_id: string | null;
	parent_span_id: string | null;
	source: 'browser' | 'api' | 'worker';
	actor: { user_id: string | null; project_id: string | null };
	received_at: string;
	occurred_at: string | null;
	client_seq: number | null;
	client_monotonic_ms: number | null;
	route: string;
	feature: string;
	action: string;
	component: string;
	frontend_build: string;
	catalog_revision: string;
	backend_build: string | null;
	redaction_revision: number;
	event_type: string;
	payload: { key?: string | null; locale?: string; tone?: string; restoration?: string; state?: string; step?: number; request_id?: string; http_status?: number; stage?: string; reason?: string; visibility?: string; focused?: boolean };
	request_id: string | null;
	http_status: number | null;
	stage: string | null;
	status: string | null;
	operation_id: string | null;
	resource_ref: string | null;
}
export interface ExperienceReplayResponse {
	schema_version: 2;
	events: ExperienceReplayEvent[];
	has_more: boolean;
	coverage: { partial: boolean; reasons: string[]; remote_spans: 'unavailable'; screen_tail: 'unknown' };
	catalogs: { revision: string; key: string; locale: string; template: string }[];
}
export interface ExperienceReplayQuery { segmentId: string; actionId: string; domainId: string; projectId: string; includeAnonymous: boolean }
export const experienceUuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
export interface ExperienceRecentSegment {
	segment_id: string;
	user_id: string;
	project_id: string;
	last_received_at: string;
	event_count: number;
}
export interface ExperienceRecentResponse {
	schema_version: 2;
	segments: ExperienceRecentSegment[];
	has_more: boolean;
	coverage: { partial: boolean; reasons: string[] };
}
export interface ExperienceRecentQuery {
	userId: string;
	days: 1 | 7 | 30;
	domainId: string;
	projectId: string;
	includeAnonymous: boolean;
}
export function recentReplayQuery(query: ExperienceRecentQuery): string {
	if (query.userId.length > 64 || ![1, 7, 30].includes(query.days)) throw new Error('invalid_filter');
	if (query.includeAnonymous && (query.domainId || query.projectId)) throw new Error('anonymous_scope');
	const params = new URLSearchParams({ days: String(query.days), limit: '20', include_anonymous: String(query.includeAnonymous) });
	if (query.userId) params.set('user_id', query.userId);
	if (query.domainId) params.set('domain_id', query.domainId);
	if (query.projectId) params.set('project_id', query.projectId);
	return `/api/v1/admin/experiences/segments?${params}`;
}
/** Display-only validation; fresh backend scope remains the disclosure authority. */
export function recentReplayRows(response: ExperienceRecentResponse, query: ExperienceRecentQuery): ExperienceRecentSegment[] {
	return response.segments.filter(row => experienceUuid.test(row.segment_id)
		&& typeof row.user_id === 'string' && row.user_id.length <= 64
		&& typeof row.project_id === 'string' && row.project_id.length <= 64
		&& (!query.userId || row.user_id === query.userId)
		&& (!query.projectId || row.project_id === query.projectId)
		&& (query.includeAnonymous || !!row.user_id)
		&& typeof row.last_received_at === 'string' && /(?:Z|[+-]\d{2}:\d{2})$/.test(row.last_received_at)
		&& Number.isFinite(Date.parse(row.last_received_at))
		&& Number.isSafeInteger(row.event_count) && row.event_count > 0);
}
export function replayQuery(query: ExperienceReplayQuery, exporting = false, beforeId?: number): string {
	if (!experienceUuid.test(query.segmentId) || (query.actionId && !experienceUuid.test(query.actionId))) throw new Error('invalid_identifier');
	if (query.includeAnonymous && (query.domainId || query.projectId)) throw new Error('anonymous_scope');
	const params = new URLSearchParams({ segment_id: query.segmentId, limit: exporting ? '2000' : '200', include_anonymous: String(query.includeAnonymous) });
	if (query.actionId) params.set('action_id', query.actionId);
	if (query.domainId) params.set('domain_id', query.domainId);
	if (query.projectId) params.set('project_id', query.projectId);
	if (!exporting && beforeId && Number.isSafeInteger(beforeId)) params.set('before_id', String(beforeId));
	return `/api/v1/admin/experiences${exporting ? '/export' : ''}?${params}`;
}
/** A display-only defense: the backend must independently authorize every row and join. */
export function replayRows(response: ExperienceReplayResponse, query: ExperienceReplayQuery): ExperienceReplayEvent[] {
	return response.events.filter(row => row.segment_id === query.segmentId && (!query.actionId || row.action_id === query.actionId)
		&& (!query.projectId || row.actor.project_id === query.projectId)
		&& (query.includeAnonymous || !!row.actor.user_id));
}
export function retainedReplayMessage(row: ExperienceReplayEvent, catalogs: ExperienceReplayResponse['catalogs']): string | null {
	if (row.event_type !== 'message.presented' || row.payload.restoration !== 'restored' || !row.payload.key) return null;
	return catalogs.find(entry => entry.revision === row.catalog_revision && entry.key === row.payload.key && entry.locale === row.payload.locale)?.template ?? null;
}
export function replayCause(row: ExperienceReplayEvent, rows: ExperienceReplayEvent[]): ExperienceReplayEvent | undefined {
	if (!row.caused_by_event_id) return undefined;
	return rows.find(parent => parent.event_id === row.caused_by_event_id && parent.segment_id === row.segment_id
		&& parent.actor.user_id === row.actor.user_id && parent.actor.project_id === row.actor.project_id);
}
export function replaySource(source: string) {
	switch (source) {
		case 'browser': return 'experience.browser' as const;
		case 'api': return 'experience.api' as const;
		case 'worker': return 'experience.worker' as const;
		default: return 'experience.unknown' as const;
	}
}
export function replayLabel(row: ExperienceReplayEvent) {
	switch (row.event_type) {
		case 'result.applied': return 'experience.applied' as const;
		case 'result.committed': return 'experience.committed' as const;
		case 'view.exposure_changed': return 'experience.exposure' as const;
		case 'message.presented': return 'experience.message' as const;
		case 'result.discarded': return 'experience.discarded' as const;
		case 'telemetry.gap': return 'experience.gap' as const;
		default: return replaySource(row.source);
	}
}
export function replayStatus(status: string | null) {
	switch (status) {
		case 'accepted': return 'experience.statusAccepted' as const;
		case 'running': return 'events.started' as const;
		case 'succeeded': return 'events.success' as const;
		case 'failed': return 'events.failed' as const;
		case 'cancel_requested': return 'experience.statusCancelRequested' as const;
		case 'cancelled': return 'experience.statusCancelled' as const;
		case 'outcome_unknown': return 'experience.statusOutcomeUnknown' as const;
		case 'observed': case null: return 'events.observed' as const;
		default: return 'experience.unknown' as const;
	}
}
const replayValueLabels = {
	'stage:request': 'experience.stageRequest', 'stage:native': 'experience.stageNative', 'stage:readback': 'experience.stageReadback',
	'stage:blocking': 'experience.stageBlocking', 'stage:blocking.drain': 'experience.stageBlockingDrain',
	'stage:native.drain': 'experience.stageNativeDrain',
	'stage:worker': 'experience.stageWorker', 'stage:cleanup': 'experience.stageCleanup', 'stage:build.admission': 'experience.stageBuildAdmission',
	'stage:mail.admission': 'experience.stageMailAdmission', 'stage:mail.dispatch': 'experience.stageMailDispatch',
	'stage:mcp.admission': 'experience.stageMcpAdmission', 'stage:mcp.dispatch': 'experience.stageMcpDispatch', 'stage:notion.sync': 'experience.stageNotionSync',
	'stage:response': 'experience.stageResponse', 'stage:state': 'experience.stageState', 'stage:dom': 'experience.stageDom',
	'state:loading': 'experience.stateLoading', 'state:ready': 'experience.stateReady', 'state:empty': 'experience.stateEmpty',
	'state:error': 'experience.stateError', 'state:disabled': 'experience.stateDisabled',
	'tone:neutral': 'experience.toneNeutral', 'tone:info': 'experience.toneInfo', 'tone:success': 'experience.toneSuccess',
	'tone:warning': 'experience.toneWarning', 'tone:danger': 'experience.toneDanger',
	'visibility:visible': 'experience.visibilityVisible', 'visibility:hidden': 'experience.visibilityHidden',
	'focus:true': 'experience.focusYes', 'focus:false': 'experience.focusNo',
	'reason:aborted': 'experience.reasonAborted', 'reason:lease_lost': 'experience.reasonLeaseLost', 'reason:unlinked': 'experience.reasonUnlinked',
	'reason:transport_complete': 'experience.reasonTransportComplete', 'reason:transport_incomplete': 'experience.reasonTransportIncomplete',
	'reason:smtp_accepted': 'experience.reasonSmtpAccepted', 'reason:pending_cleanup': 'experience.reasonPendingCleanup',
	'reason:required': 'experience.reasonRequired', 'reason:policy': 'experience.reasonPolicy', 'reason:format': 'experience.reasonFormat',
	'reason:quota': 'experience.reasonQuota', 'reason:capacity': 'experience.reasonCapacity', 'reason:authority': 'experience.reasonAuthority',
	'reason:stale': 'experience.reasonStale', 'reason:scope_changed': 'experience.reasonScopeChanged', 'reason:unmounted': 'experience.reasonUnmounted',
	'reason:queue_overflow': 'experience.reasonQueueOverflow', 'reason:transport_failed': 'experience.reasonTransportFailed',
	'reason:deadline': 'experience.reasonDeadline', 'reason:unsupported': 'experience.reasonUnsupported',
	'reason:bounded_window': 'experience.reasonBoundedWindow', 'reason:missing_context': 'experience.reasonMissingContext',
	'reason:clock_order_unknown': 'experience.reasonClockOrderUnknown', 'reason:redacted_reference': 'experience.reasonRedactedReference',
	'reason:catalog_unavailable': 'experience.reasonCatalogUnavailable',
} as const;
export function replayValue(kind: 'stage' | 'state' | 'tone' | 'visibility' | 'focus' | 'reason', value: string | boolean | null | undefined) {
	return replayValueLabels[`${kind}:${value}` as keyof typeof replayValueLabels] ?? 'experience.unknown';
}
export function replayHttpStatus(row: ExperienceReplayEvent): number | null {
	const status = row.source === 'browser' ? row.payload.http_status
		: (row.source === 'api' || row.source === 'worker') && row.event_type === 'request.completed' ? row.http_status : null;
	return typeof status === 'number' && Number.isInteger(status) && status >= 100 && status <= 599 ? status : null;
}
