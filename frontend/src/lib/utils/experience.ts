import { tick } from 'svelte';
import { writable } from 'svelte/store';
import { auditRoute, publicAuditRoute, type InteractionOwner } from './interactionAudit';
import type { ExperienceMessageMetadata } from '$lib/i18n/experienceMessages';
import { LOCALES } from '$lib/i18n/locales';
export type { ExperienceMessageMetadata } from '$lib/i18n/experienceMessages';

export type ExperienceFeature = 'auth' | 'account' | 'mcp' | 'compute' | 'block_storage' | 'file_storage' | 'object_storage' | 'network' | 'container' | 'database' | 'k3s' | 'waygate' | 'lumen' | 'palimpsest' | 'iam' | 'admin' | 'monitoring' | 'settings' | 'activity' | 'docs';
export type ExperienceAction = 'view' | 'load' | 'submit' | 'create' | 'update' | 'delete' | 'start' | 'stop' | 'restart' | 'attach' | 'detach' | 'select' | 'approve' | 'deny' | 'cancel' | 'sign_in' | 'sign_out' | 'refresh' | 'verify' | 'recover' | 'change_password' | 'export' | 'inspect' | 'navigate' | 'open' | 'close' | 'retry';
export type ExperienceComponent = 'app.shell' | 'app.navigation' | 'page' | 'resource.list' | 'resource.detail' | 'auth.login' | 'auth.callback' | 'auth.recover' | 'auth.signup' | 'auth.invitation' | 'auth.password' | 'auth.verification' | 'auth.provider' | 'mcp.consent' | 'compute.create' | 'block_storage.create' | 'shared.button' | 'shared.form' | 'shared.field' | 'shared.modal' | 'shared.alert' | 'shared.toast' | 'shared.wizard' | 'shared.table' | 'shared.stream' | 'admin.events';
export type ExperienceEventType = 'view.entered' | 'view.state_changed' | 'action.started' | 'validation.rejected' | 'message.presented' | 'result.received' | 'result.applied' | 'result.committed' | 'result.discarded' | 'view.exposure_changed' | 'telemetry.gap';
export type ExperienceDiscardReason = 'stale' | 'aborted' | 'scope_changed' | 'unmounted' | 'unknown';
export interface ExperienceRequestReference { request_id?: string; http_status?: number; transport?: 'network' | 'cache' | 'shared'; physical_span_id?: string }
export type ExperiencePayload = ExperienceRequestReference & { state?: 'loading' | 'ready' | 'empty' | 'error' | 'disabled'; step?: number; access?: 'none' | 'read' | 'manage' | 'mixed'; selection?: 'none' | 'some' | 'all'; selection_kind?: ExperienceSelectionKind; reason?: ExperienceDiscardReason | 'required' | 'policy' | 'format' | 'quota' | 'capacity' | 'authority' | 'queue_overflow' | 'transport_failed' | 'deadline' | 'unsupported'; count?: number; stage?: 'response' | 'state' | 'dom'; visibility?: 'visible' | 'hidden'; focused?: boolean; key?: string | null; locale?: string; catalog_revision?: string; tone?: ExperienceMessageMetadata['tone']; restoration?: ExperienceMessageMetadata['restoration'] };
export type ExperienceSelectionKind = 'domain' | 'project' | 'home';
export interface ExperienceContext {
	readonly segmentId: string;
	readonly pageViewId: string;
	readonly actionId?: string;
	readonly traceId: string;
	readonly spanId: string;
	readonly parentSpanId?: string;
	readonly rootEventId?: string;
	readonly feature: ExperienceFeature;
	readonly action: ExperienceAction;
	readonly component: ExperienceComponent;
	readonly route: string;
}
interface WireEvent { schema_version: 2; event_id: string; event_type: ExperienceEventType; segment_id: string; page_view_id: string; action_id?: string; caused_by_event_id?: string; trace_id: string; span_id: string; parent_span_id?: string; client_seq: number; client_monotonic_ms: number; occurred_at: string; route: string; feature: ExperienceFeature; action: ExperienceAction; component: ExperienceComponent; frontend_build: string; catalog_revision: string; redaction_revision: 1; payload: ExperiencePayload }
export interface ExperienceHealth { status: 'disabled' | 'checking' | 'ready' | 'unsupported' | 'unavailable'; queued: number; sent: number; dropped: number; failedBatches: number }
const health = writable<ExperienceHealth>({ status: 'disabled', queued: 0, sent: 0, dropped: 0, failedBatches: 0 });
export const experienceHealth = { subscribe: health.subscribe };
const supportCode = writable<string | null>(null);
/** Opaque diagnostic correlation only; never a credential or query authority. */
export const experienceSupportCode = { subscribe: supportCode.subscribe };
const owners = new WeakMap<ExperienceContext, { collector: Collector; revision: number }>();
let active: Collector | undefined;
let cleanupActive: (() => void) | undefined;
const endpoint = '/api/v1/activity/experience-events';
const contractEndpoint = '/api/v1/activity/experience-contract';
const encoder = new TextEncoder();
const batchEnvelopeBytes = JSON.stringify({ schema_version: 2, events: [] }).length;
const uuid = () => crypto.randomUUID();
const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const revisionPattern = /^(?:[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?|[a-f0-9]{7,64})$/;
function revision(value: string | undefined) { return value && value.length <= 80 && revisionPattern.test(value) ? value : 'unknown'; }
function ownerKey(owner: InteractionOwner): string {
	// No credential is serialized or used as a segment ID. Token-less transitions fence ABA.
	return JSON.stringify([!!owner.token, owner.sessionId ?? owner.token ?? null, owner.userId, owner.identityDomainId ?? null, owner.domainId, owner.projectId]);
}
const routeFeatures: Partial<Record<string, ExperienceFeature>> = {
	auth: 'auth', login: 'auth', logout: 'auth', signup: 'auth', recover: 'auth', invitations: 'auth', registrations: 'auth',
	account: 'account', notifications: 'account', mcp: 'mcp', oauth: 'mcp',
	compute: 'compute', instances: 'compute', images: 'compute', keypairs: 'compute', flavors: 'compute',
	volumes: 'block_storage', snapshots: 'block_storage', backups: 'block_storage', 'file-storage': 'file_storage',
	'object-storage': 'object_storage', buckets: 'object_storage',
	network: 'network', networks: 'network', routers: 'network', topology: 'network', loadbalancers: 'network',
	'floating-ips': 'network', 'security-groups': 'network',
	containers: 'container', database: 'database', drover: 'k3s', clusters: 'k3s', waygate: 'waygate',
	chat: 'lumen', lumen: 'lumen', palimpsest: 'palimpsest',
	iam: 'iam', users: 'iam', projects: 'iam', domains: 'iam', secrets: 'iam', 'select-domain': 'iam', 'select-project': 'iam',
	admin: 'admin', monitoring: 'monitoring', observability: 'monitoring', usage: 'monitoring', 'usage-report': 'monitoring',
	settings: 'settings', 'project-settings': 'settings', activity: 'activity', docs: 'docs',
};
function featureFromRoute(route: string): ExperienceFeature {
	const parts = route.split('/');
	return routeFeatures[(parts[1] === 'dashboard' ? parts[2] : parts[1]) ?? ''] ?? 'activity';
}
export interface ExperienceCollectorOptions {
	getOwner: () => InteractionOwner;
	getRoute: () => string | null;
	getBaseUrl: () => string;
	isSuppressed: () => boolean;
	isEnabled: () => boolean;
	subscribeOwner: (changed: () => void) => () => void;
	frontendBuild?: string;
	catalogRevision?: string;
}
export interface ExperienceCollectorController { syncOwner: () => void; navigate: (route: string | null) => void; flush: () => Promise<void>; destroy: () => void }
function live(ctx: ExperienceContext | undefined): Collector | undefined {
	if (!ctx) return;
	const bound = owners.get(ctx);
	bound?.collector.syncOwner();
	return bound && bound.collector.current(bound.revision) ? bound.collector : undefined;
}
export function beginExperienceAction(feature: ExperienceFeature, action: ExperienceAction, component: ExperienceComponent): ExperienceContext | undefined {
	return active?.begin(feature, action, component, true);
}
/** A mount, polling tick or another source-owned load is not a human action. */
export function beginExperienceLoad(feature: ExperienceFeature, component: ExperienceComponent): ExperienceContext | undefined {
	return active?.begin(feature, 'load', component, false);
}
/** An unlinked API load is not evidence of a click or a rendered result. */
export function beginExperienceRequest(method = 'GET', component: 'page' | 'shared.stream' = 'page'): ExperienceContext | undefined {
	return active?.beginRoute(['GET', 'HEAD'].includes(method.toUpperCase()) ? 'load' : 'submit', component);
}
export function recordExperience(ctx: ExperienceContext | undefined, type: ExperienceEventType, payload: ExperiencePayload = {}): string | undefined {
	return live(ctx)?.record(ctx!, type, payload);
}
export function experienceState(ctx: ExperienceContext | undefined, state: NonNullable<ExperiencePayload['state']>, step?: number): void {
	recordExperience(ctx, 'view.state_changed', { state, ...(step !== undefined ? { step } : {}) });
}
export async function experienceApplied(ctx: ExperienceContext | undefined, requestRef: ExperienceRequestReference = {}, isCurrentState?: () => boolean): Promise<void> {
	if (!live(ctx)) return;
	recordExperience(ctx, 'result.applied', { ...requestRef, stage: 'state' });
	// Assignment is source-owned; without an explicit assertion its post-tick DOM tail is unknown.
	if (!isCurrentState) return;
	await tick();
	if (!live(ctx)) return;
	if (!isCurrentState()) {
		recordExperience(ctx, 'result.discarded', { ...requestRef, stage: 'dom', reason: 'stale' });
		return;
	}
	recordExperience(ctx, 'result.committed', { ...requestRef, stage: 'dom' });
}
export function experienceDiscarded(ctx: ExperienceContext | undefined, reason: ExperienceDiscardReason): void { recordExperience(ctx, 'result.discarded', { reason }); }
export function experienceMessage(ctx: ExperienceContext | undefined, metadata: ExperienceMessageMetadata): void { recordExperience(ctx, 'message.presented', metadata); }
export function experienceRequestReference(response: Response): ExperienceRequestReference {
	const requestId = response.headers.get('X-Request-Id');
	return { ...(requestId && /^req-[a-f0-9]{32}$/.test(requestId) ? { request_id: requestId } : {}), http_status: response.status, transport: 'network' };
}
export function experienceRequest(ctx: ExperienceContext | undefined, attempt = 1): { headers: Record<string, string>; context: ExperienceContext | undefined } {
	const collector = live(ctx);
	if (!collector || !ctx) return { headers: {}, context: undefined };
	const child = collector.child(ctx);
	const headers: Record<string, string> = {
		'X-Afterglow-Experience-Segment': child.segmentId, 'X-Afterglow-Experience-Page-View': child.pageViewId,
		'X-Afterglow-Experience-Trace': child.traceId, 'X-Afterglow-Experience-Span': child.spanId,
		'X-Afterglow-Experience-Attempt': String(Math.min(32, Math.max(1, Math.trunc(attempt)))), 'X-Afterglow-Page': child.route,
	};
	if (child.actionId) headers['X-Afterglow-Experience-Action'] = child.actionId;
	if (child.rootEventId) headers['X-Afterglow-Experience-Event'] = child.rootEventId;
	return { headers, context: child };
}
function sanitize(type: ExperienceEventType, value: ExperiencePayload, ctx: ExperienceContext): ExperiencePayload {
	const out: ExperiencePayload = {};
	if (type.startsWith('result.')) {
		if (value.request_id && /^req-[a-f0-9]{32}$/.test(value.request_id)) out.request_id = value.request_id;
		if (Number.isInteger(value.http_status) && value.http_status! >= 100 && value.http_status! <= 599) out.http_status = value.http_status;
		if (value.transport && ['network', 'cache', 'shared'].includes(value.transport)) out.transport = value.transport;
		if (value.physical_span_id && uuidPattern.test(value.physical_span_id)) out.physical_span_id = value.physical_span_id;
		out.stage = value.stage && ['response', 'state', 'dom'].includes(value.stage) ? value.stage : type === 'result.received' ? 'response' : type === 'result.committed' ? 'dom' : 'state';
		if (type === 'result.discarded') out.reason = ['stale', 'aborted', 'scope_changed', 'unmounted', 'unknown'].includes(value.reason ?? '') ? value.reason : 'unknown';
	} else if (type === 'view.state_changed') {
		if (value.state && ['loading', 'ready', 'empty', 'error', 'disabled'].includes(value.state)) out.state = value.state;
		if (Number.isInteger(value.step) && value.step! >= 0 && value.step! <= 32) out.step = value.step;
		if (ctx.feature === 'mcp' && ctx.component === 'mcp.consent') {
			if (value.access && ['none', 'read', 'manage', 'mixed'].includes(value.access)) out.access = value.access;
			if (value.selection && ['none', 'some', 'all'].includes(value.selection)) out.selection = value.selection;
		}
		if (ctx.feature === 'iam' && ctx.component === 'page' && ctx.action === 'select' && value.selection_kind && ['domain', 'project', 'home'].includes(value.selection_kind)) out.selection_kind = value.selection_kind;
	} else if (type === 'validation.rejected') {
		out.reason = ['required', 'policy', 'format', 'quota', 'capacity', 'authority', 'unknown'].includes(value.reason ?? '') ? value.reason : 'unknown';
	} else if (type === 'view.exposure_changed') {
		out.visibility = value.visibility === 'hidden' ? 'hidden' : 'visible';
		if (typeof value.focused === 'boolean') out.focused = value.focused;
	} else if (type === 'message.presented') {
		out.key = typeof value.key === 'string' && value.key.length <= 180 && /^[A-Za-z0-9_.-]+:[A-Za-z0-9_.-]+$/.test(value.key) ? value.key : null;
		out.locale = LOCALES.some(locale => locale === value.locale) ? value.locale : 'unknown';
		out.tone = value.tone && ['neutral', 'info', 'success', 'warning', 'danger'].includes(value.tone) ? value.tone : 'neutral';
		out.restoration = value.restoration && ['restored', 'redacted', 'unavailable'].includes(value.restoration) ? value.restoration : 'unavailable';
	} else if (type === 'telemetry.gap') {
		out.reason = ['queue_overflow', 'transport_failed', 'deadline', 'unsupported', 'scope_changed'].includes(value.reason ?? '') ? value.reason : 'transport_failed';
		out.count = Math.max(1, Math.min(2147483647, Math.trunc(value.count ?? 1)));
	}
	return out;
}
class Collector {
	private revision = 0;
	private key: string;
	private baseUrl: string;
	private suppressed: boolean;
	private enabled: boolean;
	private disposed = false;
	private segment = uuid();
	private page = uuid();
	private route: string;
	private routeFeature: ExperienceFeature;
	private entered = false;
	private seq = 0;
	private started = performance.now();
	private queue: { event: WireEvent; bytes: number; attempts: number; deadline: number }[] = [];
	private sending = false;
	private gap = 0;
	private capability: ExperienceHealth['status'] = 'disabled';
	private contractPromise: Promise<void> | undefined;
	private capabilityRetryAt = 0;
	private capabilityDelayMs = 1500;
	private controller: AbortController | undefined;
	private counts = { sent: 0, dropped: 0, failedBatches: 0 };
	private send: typeof fetch;
	constructor(private options: ExperienceCollectorOptions) {
		this.key = ownerKey(options.getOwner()); this.baseUrl = options.getBaseUrl();
		this.suppressed = options.isSuppressed(); this.enabled = options.isEnabled();
		this.route = auditRoute(options.getRoute());
		this.routeFeature = featureFromRoute(this.route);
		this.send = window.fetch.bind(window);
		this.publish();
	}
	private publish() {
		if (active && active !== this) return;
		health.set({ status: this.capability, ...this.counts, queued: this.queue.length });
		supportCode.set(!this.disposed && this.enabled && !this.suppressed && this.capability !== 'unsupported' ? this.segment : null);
	}
	current(rev: number) { this.syncOwner(); return !this.disposed && !this.suppressed && this.enabled && this.capability !== 'unsupported' && rev === this.revision; }
	syncOwner = () => {
		const key = ownerKey(this.options.getOwner()), base = this.options.getBaseUrl(), suppressed = this.options.isSuppressed(), enabled = this.options.isEnabled();
		if (key !== this.key || base !== this.baseUrl || suppressed !== this.suppressed || enabled !== this.enabled) {
			this.controller?.abort(); this.controller = undefined;
			this.counts.dropped += this.queue.length; this.queue = []; this.gap = 0;
			this.key = key; this.baseUrl = base; this.suppressed = suppressed; this.enabled = enabled;
			++this.revision; this.segment = uuid(); this.page = uuid(); this.entered = false; this.seq = 0; this.started = performance.now();
			this.capability = 'disabled'; this.contractPromise = undefined;
			this.capabilityRetryAt = 0; this.capabilityDelayMs = 1500; this.publish();
		}
	};
	private syncRoute() {
		this.prepare(this.options.getRoute());
	}
	prepare = (route: string | null) => {
		const canonical = auditRoute(route);
		if (canonical === this.route) return;
		this.route = canonical;
		this.routeFeature = featureFromRoute(canonical);
		this.page = uuid();
		this.entered = false;
	};
	beginRoute(action: ExperienceAction, component: ExperienceComponent): ExperienceContext | undefined {
		this.syncRoute();
		return this.begin(this.routeFeature, action, component, false);
	}
	begin(feature: ExperienceFeature, action: ExperienceAction, component: ExperienceComponent, actionStarted: boolean): ExperienceContext | undefined {
		this.syncOwner();
		this.syncRoute();
		if (!this.current(this.revision) || this.capability === 'unsupported'
			|| (!this.options.getOwner().token && !publicAuditRoute(this.route))) return;
		let ctx: ExperienceContext = Object.freeze({ segmentId: this.segment, pageViewId: this.page, ...(actionStarted ? { actionId: uuid() } : {}), traceId: uuid(), spanId: uuid(), feature, action, component, route: this.route });
		owners.set(ctx, { collector: this, revision: this.revision });
		if (actionStarted) {
			const rootEventId = this.record(ctx, 'action.started', {});
			ctx = Object.freeze({ ...ctx, rootEventId }); owners.set(ctx, { collector: this, revision: this.revision });
		}
		return ctx;
	}
	child(ctx: ExperienceContext): ExperienceContext {
		const child = Object.freeze({ ...ctx, spanId: uuid(), parentSpanId: ctx.spanId });
		owners.set(child, { collector: this, revision: this.revision }); return child;
	}
	record(ctx: ExperienceContext, type: ExperienceEventType, payload: ExperiencePayload): string | undefined {
		if (!this.options.getOwner().token && !publicAuditRoute(ctx.route)) return;
		if (this.seq >= 2147483647 || performance.now() - this.started > 604800000) return;
		if (this.queue.length >= 200) { ++this.counts.dropped; ++this.gap; this.publish(); return; }
		const event: WireEvent = { schema_version: 2, event_id: uuid(), event_type: type, segment_id: ctx.segmentId, page_view_id: ctx.pageViewId,
			...(ctx.actionId ? { action_id: ctx.actionId } : {}), ...(ctx.rootEventId ? { caused_by_event_id: ctx.rootEventId } : {}), trace_id: ctx.traceId, span_id: ctx.spanId,
			...(ctx.parentSpanId ? { parent_span_id: ctx.parentSpanId } : {}), client_seq: ++this.seq, client_monotonic_ms: Math.max(0, Math.trunc(performance.now() - this.started)), occurred_at: new Date().toISOString(), route: ctx.route,
			feature: ctx.feature, action: ctx.action, component: ctx.component, frontend_build: revision(this.options.frontendBuild), catalog_revision: revision(payload.catalog_revision ?? this.options.catalogRevision), redaction_revision: 1, payload: sanitize(type, payload, ctx) };
		this.queue.push({ event, bytes: encoder.encode(JSON.stringify(event)).byteLength, attempts: 0, deadline: Date.now() + 60000 }); this.publish(); return event.event_id;
	}
	private async qualify(): Promise<void> {
		if (this.capability === 'ready' || this.capability === 'unsupported') return;
		if (this.contractPromise) return this.contractPromise;
		if (Date.now() < this.capabilityRetryAt) return;
		const rev = this.revision; this.capability = 'checking'; this.publish();
		this.controller = new AbortController();
		const pending = (async () => {
			try {
				const response = await this.send(`${this.baseUrl}${contractEndpoint}`, { credentials: 'omit', signal: AbortSignal.any([this.controller!.signal, AbortSignal.timeout(10000)]) });
				if (!this.current(rev)) return;
				if (response.status === 404) { this.capability = 'unsupported'; this.counts.dropped += this.queue.length; this.queue = []; return; }
				if (!response.ok) throw new Error('contract_unavailable');
				const data = await response.json();
				if (!this.current(rev)) return;
				if (data.schema_version !== 2 || data.enabled !== true || data.redaction_revision !== 1 || data.max_batch_events !== 20 || data.max_body_bytes !== 32768) { this.capability = 'unsupported'; this.counts.dropped += this.queue.length; this.queue = []; return; }
				this.capability = 'ready'; this.capabilityRetryAt = 0; this.capabilityDelayMs = 1500;
			} catch {
				if (this.current(rev)) {
					this.capability = 'unavailable';
					this.capabilityRetryAt = Date.now() + this.capabilityDelayMs;
					this.capabilityDelayMs = Math.min(60000, this.capabilityDelayMs * 2);
				}
			}
			finally { if (rev === this.revision) { this.contractPromise = undefined; this.publish(); } }
		})();
		this.contractPromise = pending; return pending;
	}
	flush = async () => {
		this.syncOwner(); if (!this.current(this.revision) || this.sending || !this.queue.length) return;
		const expiredBeforeContract = this.queue.filter(row => row.deadline <= Date.now());
		this.queue = this.queue.filter(row => row.deadline > Date.now()); this.counts.dropped += expiredBeforeContract.length;
		const expiredEvents = expiredBeforeContract.filter(row => row.event.event_type !== 'telemetry.gap').length;
		if (expiredEvents) this.recordGap('deadline', expiredEvents);
		if (!this.queue.length) { this.publish(); return; }
		const rev = this.revision; this.sending = true;
		try {
			await this.qualify(); if (!this.current(rev) || this.capability !== 'ready') return;
			const expired = this.queue.filter(row => row.deadline <= Date.now());
			this.queue = this.queue.filter(row => row.deadline > Date.now()); this.counts.dropped += expired.length;
			const lostExpired = expired.filter(row => row.event.event_type !== 'telemetry.gap').length;
			if (lostExpired) this.recordGap('deadline', lostExpired);
			if (this.gap && this.queue.length < 200) { const count = this.gap; this.gap = 0; this.recordGap('queue_overflow', count); }
			const batch: typeof this.queue = [];
			let bytes = batchEnvelopeBytes;
			for (const row of this.queue) {
				if (batch.length >= 20) break;
				const nextBytes = bytes + row.bytes + (batch.length ? 1 : 0);
				if (nextBytes > 32768) break;
				batch.push(row);
				bytes = nextBytes;
			}
			if (!batch.length) return;
			const credential = this.options.getOwner();
			const headers: Record<string, string> = { 'Content-Type': 'application/json' };
			if (credential.token) headers.Authorization = `Bearer ${credential.token}`;
			if (credential.projectId) headers['X-Project-Id'] = credential.projectId;
			for (const row of batch) ++row.attempts;
			this.controller = new AbortController();
			const timeoutMs = Math.max(1, Math.min(10000, batch.reduce((deadline, row) => Math.min(deadline, row.deadline), Infinity) - Date.now()));
			let retryable = true;
			try {
				const response = await this.send(`${this.baseUrl}${endpoint}`, { method: 'POST', headers, body: JSON.stringify({ schema_version: 2, events: batch.map(row => row.event) }), credentials: 'omit', keepalive: true, signal: AbortSignal.any([this.controller.signal, AbortSignal.timeout(timeoutMs)]) });
				if (!this.current(rev)) return;
				if (response.status === 404) {
					this.capability = 'unsupported'; this.counts.dropped += this.queue.length; this.queue = []; return;
				}
				retryable = response.status === 429 || response.status >= 500;
				if (!response.ok) throw new Error('delivery_failed');
				const receipt = await response.json();
				if (!this.current(rev)) return;
				if (receipt.schema_version !== 2 || !Number.isInteger(receipt.accepted) || !Number.isInteger(receipt.duplicates) || receipt.accepted < 0 || receipt.duplicates < 0 || receipt.accepted + receipt.duplicates !== batch.length) throw new Error('invalid_receipt');
				const sent = new Set(batch); this.queue = this.queue.filter(row => !sent.has(row)); this.counts.sent += batch.length;
			} catch {
				if (!this.current(rev)) return;
				++this.counts.failedBatches;
				const dropped = new Set(batch.filter(row => !retryable || row.attempts >= 2 || row.deadline <= Date.now()));
				this.queue = this.queue.filter(row => !dropped.has(row)); this.counts.dropped += dropped.size;
				// Never recursively create transport-failed gaps for a failed gap itself.
				const lost = [...dropped].filter(row => row.event.event_type !== 'telemetry.gap').length;
				if (lost && this.capability !== 'unsupported') this.recordGap('transport_failed', lost);
				if (this.capability === 'unsupported') { this.counts.dropped += this.queue.length; this.queue = []; }
			}
		} finally { this.sending = false; this.publish(); }
	};
	private recordGap(reason: ExperiencePayload['reason'], count: number) { const ctx = this.beginRoute('load', 'app.shell'); if (ctx) this.record(ctx, 'telemetry.gap', { reason, count }); }
	navigate = (route: string | null) => {
		this.syncOwner(); this.prepare(route);
		if (this.entered) return;
		const ctx = this.beginRoute('view', 'page');
		if (ctx) { this.entered = true; this.record(ctx, 'view.entered', {}); this.exposure(); }
	};
	exposure = () => { const ctx = this.beginRoute('view', 'page'); if (ctx) this.record(ctx, 'view.exposure_changed', { visibility: document.visibilityState === 'hidden' ? 'hidden' : 'visible', focused: document.hasFocus() }); };
	destroy = () => { if (this.disposed) return; this.disposed = true; ++this.revision; this.controller?.abort(); this.counts.dropped += this.queue.length; this.queue = []; this.capability = 'disabled'; this.publish(); };
}
export function installExperienceCollector(options: ExperienceCollectorOptions): ExperienceCollectorController {
	cleanupActive?.();
	const collector = new Collector(options);
	active = collector;
	const unsubscribe = options.subscribeOwner(collector.syncOwner);
	const timer = setInterval(() => { void collector.flush(); }, 1500);
	document.addEventListener('visibilitychange', collector.exposure);
	window.addEventListener('focus', collector.exposure);
	window.addEventListener('blur', collector.exposure);
	window.addEventListener('pagehide', collector.flush);
	let disposed = false;
	const destroy = () => {
		if (disposed) return;
		disposed = true;
		clearInterval(timer);
		unsubscribe();
		collector.destroy();
		if (active === collector) { active = undefined; cleanupActive = undefined; }
		document.removeEventListener('visibilitychange', collector.exposure);
		window.removeEventListener('focus', collector.exposure);
		window.removeEventListener('blur', collector.exposure);
		window.removeEventListener('pagehide', collector.flush);
	};
	cleanupActive = destroy;
	return { syncOwner: collector.syncOwner, navigate: collector.navigate, flush: collector.flush, destroy };
}
