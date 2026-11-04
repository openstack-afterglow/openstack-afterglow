import { writable } from 'svelte/store';

export type InteractionKind = 'click' | 'submit' | 'navigation' | 'client_error' | 'request_failed';
export interface InteractionEvent {
	kind: InteractionKind;
	page: string;
	control?: 'button' | 'link' | 'form' | 'summary' | 'combobox' | 'checkbox' | 'switch' | 'option' | 'other';
	ordinal?: number;
	destination?: string;
	interaction_id: string;
}
export interface InteractionOwner {
	token: string | null;
	userId: string | null;
	projectId: string | null;
	domainId: string | null;
	sessionId?: string;
	identityDomainId?: string | null;
}
export interface InteractionHealth { queued: number; sent: number; dropped: number; failedBatches: number }
const health = writable<InteractionHealth>({ queued: 0, sent: 0, dropped: 0, failedBatches: 0 });
export const interactionAuditHealth = { subscribe: health.subscribe };
const endpoint = '/api/v1/activity/interactions';
const selector = 'button,a[href],input[type="button"],input[type="submit"],input[type="reset"],input[type="image"],input[type="checkbox"],input[type="radio"],summary,[role="button"],[role="link"],[role="combobox"],[role="checkbox"],[role="switch"],[role="option"]';

// Shared finite source-segment policy with the ingestion validator. Unknown segments never leave the browser.
const segments = new Set('dashboard admin account activity auth callback login logout signup recover invitations registrations docs select-project select-domain oauth claude mcp authorize settings create palimpsest packages volumes snapshots backups compute instances console-log images keypairs network networks topology loadbalancers new routers floating-ips security-groups waygate usage observability drover notifications sessions beta usage-report iam projects users my-resources secrets containers clusters database file-storage security-services manage project-settings chat tools realtime audio object-storage buckets quotas flavors domains libraries monitoring traffic aodh gnocchi logins rabbitmq proxysql openstack node mysql memcached libvirt haproxy etcd ceph resources orphans ports system-admins hypervisors announcements roles subnets events stats models groups user-credentials application-credentials infrastructure-topology services notion layers gpu'.split(' '));
export function auditRoute(route: string | null | undefined): string {
	if (!route || route.length > 255 || !route.startsWith('/')) return '/:id';
	const parts = route.split('/').filter(Boolean).filter(part => !/^\([^)]*\)$/.test(part));
	if (parts.length > 12 || !/^\/[A-Za-z0-9_:/\[\]{}.=\-]*$/.test('/' + parts.join('/'))) return '/:id';
	return '/' + parts.map(part => segments.has(part) ? part : ':id').join('/');
}
const publicRoots: Partial<Record<string, true>> = { login: true, signup: true, recover: true, invitations: true, registrations: true, docs: true, auth: true, oauth: true };
/** Diagnostic observation permission only; this does not grant route/API access. */
export function publicAuditRoute(route: string): boolean {
	return route === '/' || route === '/logout' || publicRoots[route.split('/')[1] ?? ''] === true;
}
function ownerKey(owner: InteractionOwner): string {
	return JSON.stringify([!!owner.token, owner.sessionId ?? (owner.token ? owner.token : null), owner.userId, owner.identityDomainId, owner.domainId, owner.projectId]);
}

export interface InteractionAuditController {
	syncOwner: () => void;
	flush: () => Promise<void>;
	prepareNavigation: () => void;
	navigate: (route: string | null, destination?: string | null) => void;
	destroy: () => void;
}

export function installInteractionAudit(options: {
	getOwner: () => InteractionOwner;
	getRoute: () => string | null;
	getBaseUrl: () => string;
	isSuppressed: () => boolean;
	subscribeOwner: (changed: () => void) => () => void;
}): InteractionAuditController {
	const originalFetch = window.fetch;
	const send = originalFetch.bind(window);
	let revision = 0;
	let key = ownerKey(options.getOwner());
	let suppressed = options.isSuppressed();
	let disposed = false;
	let inFlight = false;
	let context: { id: string; revision: number } | null = null;
	let navigationContext: { id: string; revision: number } | null = null;
	let contextTimer: number | undefined;
	let queue: { event: InteractionEvent; projectId: string | null }[] = [];
	const counters: InteractionHealth = { queued: 0, sent: 0, dropped: 0, failedBatches: 0 };
	const publish = () => health.set({ ...counters, queued: queue.length });
	function syncOwner() {
		const next = ownerKey(options.getOwner());
		const nextSuppressed = options.isSuppressed();
		if (key !== next || suppressed !== nextSuppressed) {
			key = next; suppressed = nextSuppressed; ++revision;
			counters.dropped += queue.length; queue = []; context = null; navigationContext = null; publish();
		}
	}
	function record(kind: InteractionKind, fields: Partial<InteractionEvent> = {}, expectedRevision?: number) {
		syncOwner();
		if (disposed || suppressed || (expectedRevision !== undefined && expectedRevision !== revision)) return;
		if (queue.length >= 200) { ++counters.dropped; publish(); return; }
		const owner = options.getOwner();
		queue.push({ event: { kind, page: auditRoute(options.getRoute()), interaction_id: crypto.randomUUID(), ...fields }, projectId: owner.projectId });
		publish();
	}
	function beginAction() {
		syncOwner();
		const id = crypto.randomUUID();
		context = { id, revision };
		clearTimeout(contextTimer);
		contextTimer = window.setTimeout(() => { context = null; }, 0);
		return id;
	}
	function click(event: MouseEvent) {
		const target = event.composedPath().find(node => node instanceof Element && node.matches(selector)) as Element | undefined;
		if (!target || target.matches(':disabled,[aria-disabled="true"]')) return;
		if (event.type === 'auxclick' ? event.button !== 1 || !target.matches('a[href],[role="link"]') : event.button !== 0) return;
		const role = target.getAttribute('role');
		const control: InteractionEvent['control'] = target.matches('a[href],[role="link"]') ? 'link'
			: target.matches('summary') ? 'summary'
			: target.matches('input[type="checkbox"]') ? 'checkbox'
			: target.matches('input[type="radio"]') ? 'option'
			: role && ['combobox', 'checkbox', 'switch', 'option'].includes(role) ? role as InteractionEvent['control'] : 'button';
		const ordinal = Math.min(10000, Array.from(document.querySelectorAll(selector)).indexOf(target));
		let destination: string | undefined;
		if (target.matches('a[href]')) {
			try {
				const url = new URL((target as HTMLAnchorElement).href, window.location.origin);
				destination = url.origin === window.location.origin ? auditRoute(url.pathname) : 'external';
			} catch { destination = 'external'; }
		}
		record('click', { control, ordinal: Math.max(0, ordinal), ...(destination ? { destination } : {}), interaction_id: beginAction() });
	}
	function submit(event: SubmitEvent) {
		if (!(event.target instanceof HTMLFormElement)) return;
		const id = context?.revision === revision ? context.id : beginAction();
		record('submit', { control: 'form', ordinal: Math.min(10000, Array.from(document.forms).indexOf(event.target)), interaction_id: id });
	}
	function clientError() { record('client_error'); }
	async function flush() {
		syncOwner();
		if (disposed || inFlight || suppressed || !queue.length) return;
		const first = queue[0];
		let count = 0;
		while (count < 20 && count < queue.length && queue[count].projectId === first.projectId) ++count;
		const batch = queue.splice(0, count);
		const batchRevision = revision;
		const credential = options.getOwner();
		// A renewal may supply a new credential only inside the same fenced logical owner.
		if (ownerKey(credential) !== key) { counters.dropped += batch.length; syncOwner(); publish(); return; }
		inFlight = true; publish();
		try {
			const headers: Record<string, string> = { 'Content-Type': 'application/json' };
			if (credential.token) headers.Authorization = `Bearer ${credential.token}`;
			if (first.projectId) headers['X-Project-Id'] = first.projectId;
			const response = await send(`${options.getBaseUrl()}${endpoint}`, { method: 'POST', headers, body: JSON.stringify({ events: batch.map(row => row.event) }), keepalive: true, credentials: 'omit', signal: AbortSignal.timeout(10000) });
			if (!response.ok) throw new Error('audit_delivery_failed');
			counters.sent += batch.length;
		} catch {
			++counters.failedBatches; counters.dropped += batch.length;
		} finally {
			inFlight = false;
			// Never replay a failed/ambiguous POST, including after authentication recovery.
			if (batchRevision !== revision) syncOwner();
			publish();
		}
	}
	const wrappedFetch: typeof fetch = async (input, init) => {
		syncOwner();
		let eligible = false;
		try {
			const url = new URL(input instanceof Request ? input.url : String(input), window.location.origin);
			const api = new URL(options.getBaseUrl(), window.location.origin);
			eligible = url.origin === api.origin && url.pathname.startsWith('/api/v1/') && url.pathname !== endpoint
				&& !/^\/api\/v1\/activity\/experience-(?:events|contract)\/?$/.test(url.pathname);
		} catch { /* Unknown destinations are not telemetry inputs. */ }
		const captured = !suppressed && eligible ? { revision, page: auditRoute(options.getRoute()), id: context?.revision === revision ? context.id : undefined } : null;
		let requestInit = init;
		if (captured?.id) {
			const headers = new Headers(init?.headers ?? (input instanceof Request ? input.headers : undefined));
			headers.set('X-Afterglow-Interaction-Id', captured.id);
			requestInit = { ...init, headers };
		}
		try {
			const response = await originalFetch.call(window, input, requestInit);
			if (captured && !response.ok) record('request_failed', { page: captured.page, interaction_id: captured.id ?? crypto.randomUUID() }, captured.revision);
			return response;
		} catch (error) {
			if (captured) record('request_failed', { page: captured.page, interaction_id: captured.id ?? crypto.randomUUID() }, captured.revision);
			throw error;
		}
	};
	window.fetch = wrappedFetch;
	document.addEventListener('click', click, true);
	document.addEventListener('auxclick', click, true);
	document.addEventListener('submit', submit, true);
	window.addEventListener('error', clientError);
	window.addEventListener('unhandledrejection', clientError);
	window.addEventListener('pagehide', flush);
	const timer = setInterval(() => { void flush(); }, 1500);
	const unsubscribe = options.subscribeOwner(syncOwner);
	publish();
	return {
		syncOwner,
		flush,
		prepareNavigation() {
			syncOwner();
			navigationContext = context?.revision === revision ? { ...context } : null;
		},
		navigate(route: string | null, destination: string | null = route) {
			syncOwner();
			const id = navigationContext?.revision === revision ? navigationContext.id : context?.revision === revision ? context.id : crypto.randomUUID();
			navigationContext = null;
			record('navigation', { page: auditRoute(route), destination: destination === 'external' ? 'external' : auditRoute(destination), interaction_id: id });
		},
		destroy() {
			if (disposed) return;
			void flush();
			disposed = true; ++revision;
			counters.dropped += queue.length; queue = []; publish();
			clearInterval(timer); clearTimeout(contextTimer); unsubscribe();
			document.removeEventListener('click', click, true); document.removeEventListener('submit', submit, true);
			document.removeEventListener('auxclick', click, true);
			window.removeEventListener('error', clientError); window.removeEventListener('unhandledrejection', clientError); window.removeEventListener('pagehide', flush);
			if (window.fetch === wrappedFetch) window.fetch = originalFetch;
		},
	};
}
