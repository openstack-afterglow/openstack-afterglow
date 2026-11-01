import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from 'vitest';
import { get } from 'svelte/store';
import { auditRoute, installInteractionAudit, interactionAuditHealth, type InteractionAuditController, type InteractionOwner } from '../interactionAudit';

let collector: InteractionAuditController;
let owner: InteractionOwner;
let route: string;
let suppressed: boolean;
let ownerChanged: () => void;
let transport: Mock;
const nativeFetch = window.fetch;
function mount() {
	collector = installInteractionAudit({
		getOwner: () => owner,
		getRoute: () => route,
		getBaseUrl: () => 'http://localhost:8000',
		isSuppressed: () => suppressed,
		subscribeOwner: (changed) => { ownerChanged = changed; return () => {}; },
	});
}
function sentEvents() {
	return transport.mock.calls.filter(([url]) => String(url).endsWith('/activity/interactions')).flatMap(([, init]) => JSON.parse(init.body).events);
}
beforeEach(() => {
	vi.useFakeTimers();
	owner = { token: null, userId: null, projectId: null, domainId: null };
	route = '/login'; suppressed = false;
	transport = vi.fn().mockResolvedValue({ ok: true, status: 202 });
	window.fetch = transport as typeof fetch;
	document.body.innerHTML = '';
	mount();
});
afterEach(() => { collector.destroy(); window.fetch = nativeFetch; document.body.innerHTML = ''; vi.useRealTimers(); });

describe('mounted privacy-safe interaction collector', () => {
	it('captures nested mouse and keyboard-generated clicks once, and submits without any content', async () => {
		document.body.innerHTML = '<form><input type="password" value="private-password"><button type="button" aria-label="private-email"><span>private-label</span></button></form><a href="/recover/private-code?secret=private-query#private-hash">private-link</a>';
		document.querySelector('form')!.addEventListener('submit', event => event.preventDefault());
		document.querySelector('span')!.dispatchEvent(new MouseEvent('click', { bubbles: true, composed: true, cancelable: true }));
		document.querySelector('form')!.dispatchEvent(new SubmitEvent('submit', { bubbles: true, cancelable: true }));
		document.querySelector('a')!.addEventListener('click', event => event.preventDefault());
		document.querySelector('a')!.dispatchEvent(new MouseEvent('click', { bubbles: true, composed: true, detail: 0, cancelable: true }));
		await collector.flush();
		const rows = sentEvents();
		expect(rows.filter(row => row.kind === 'click')).toHaveLength(2);
		expect(rows.filter(row => row.kind === 'submit')).toHaveLength(1);
		expect(rows.find(row => row.control === 'link')).toMatchObject({ destination: '/recover/:id', ordinal: 1 });
		expect(JSON.stringify(rows)).not.toContain('private');
		expect(JSON.stringify(rows)).not.toContain('secret');
	});

	it('sanitizes source templates and external destinations, and never listens to key or input values', async () => {
		expect(auditRoute('/(console)/dashboard/compute/instances/[id]')).toBe('/dashboard/compute/instances/:id');
		expect(auditRoute('/recover/secret?token=private')).toBe('/:id');
		document.body.innerHTML = '<a href="https://private.example/secret?token=private">external</a><input value="private">';
		document.querySelector('a')!.addEventListener('click', event => event.preventDefault());
		document.querySelector('a')!.click();
		document.querySelector('input')!.dispatchEvent(new Event('input', { bubbles: true }));
		document.dispatchEvent(new KeyboardEvent('keydown', { key: 'private', bubbles: true }));
		collector.navigate('/login', '/dashboard/instances/[id]');
		window.dispatchEvent(new ErrorEvent('error', { message: 'private', error: new Error('private-stack') }));
		await collector.flush();
		expect(sentEvents()).toHaveLength(3);
		expect(sentEvents()[0]).toMatchObject({ control: 'link', destination: 'external' });
		expect(JSON.stringify(sentEvents())).not.toContain('private');
	});

	it('correlates same-task API calls transparently, separates failures, and excludes ingestion recursion', async () => {
		document.body.innerHTML = '<button>read</button>';
		const failure = { ok: false, status: 503 };
		transport.mockImplementation((url: string) => Promise.resolve(url.endsWith('/activity/interactions') ? { ok: true } : failure));
		const body = new FormData(); body.set('credential', 'private');
		const controller = new AbortController();
		let returned: Response | undefined;
		document.querySelector('button')!.addEventListener('click', () => { void window.fetch('http://localhost:8000/api/v1/instances?secret=private', { method: 'POST', body, signal: controller.signal }).then(value => { returned = value; }); });
		document.querySelector('button')!.click();
		await Promise.resolve(); await Promise.resolve();
		await collector.flush();
		expect(returned).toBe(failure);
		const request = transport.mock.calls.find(([url]) => String(url).includes('/instances'))!;
		expect(request[1].body).toBe(body);
		expect(request[1].signal).toBe(controller.signal);
		const id = new Headers(request[1].headers).get('X-Afterglow-Interaction-Id');
		expect(sentEvents().find(row => row.kind === 'request_failed')).toMatchObject({ interaction_id: id, page: '/login' });
		expect(sentEvents().filter(row => row.kind === 'request_failed')).toHaveLength(1);
		expect(JSON.stringify(sentEvents())).not.toContain('private');
	});

	it('uses renewed credentials only within the original owner, discards owner ABA queues and fences old in-flight failures', async () => {
		owner = { token: 'old', userId: 'a', projectId: 'a', domainId: 'a', sessionId: 'login-a' }; ownerChanged();
		document.body.innerHTML = '<button>act</button>';
		document.querySelector('button')!.click();
		owner = { ...owner, token: 'renewed' }; ownerChanged();
		await collector.flush();
		expect(transport.mock.calls[0][1].headers.Authorization).toBe('Bearer renewed');
		const pending = Promise.withResolvers<Response>();
		transport.mockImplementationOnce(() => pending.promise);
		const request = window.fetch('http://localhost:8000/api/v1/instances');
		document.querySelector('button')!.click();
		owner = { ...owner, projectId: 'b' }; ownerChanged();
		owner = { ...owner, projectId: 'a' }; ownerChanged();
		pending.resolve({ ok: false } as Response); await request;
		await collector.flush();
		expect(sentEvents()).toHaveLength(1);
		expect(get(interactionAuditHealth).dropped).toBe(1);
	});

	it('preserves rejected fetch identity and records no exception data or telemetry replay', async () => {
		const failure = new Error('private credential and stack');
		transport.mockRejectedValueOnce(failure);
		await expect(window.fetch('http://localhost:8000/api/v1/instances?private=secret')).rejects.toBe(failure);
		await collector.flush();
		expect(sentEvents()).toHaveLength(1);
		expect(sentEvents()[0].kind).toBe('request_failed');
		expect(JSON.stringify(sentEvents())).not.toContain('private');
		await collector.flush();
		expect(transport).toHaveBeenCalledTimes(2);
	});

	it('keeps explicit navigation correlation beyond the click task without leaking it into later API calls', async () => {
		document.body.innerHTML = '<button>navigate</button>';
		document.querySelector('button')!.click();
		collector.prepareNavigation();
		vi.advanceTimersByTime(1);
		collector.navigate('/login', '/dashboard/compute/instances/[id]');
		await window.fetch('http://localhost:8000/api/v1/instances');
		await collector.flush();
		const rows = sentEvents();
		expect(rows.find(row => row.kind === 'navigation').interaction_id).toBe(rows.find(row => row.kind === 'click').interaction_id);
		const request = transport.mock.calls.find(([url]) => String(url).endsWith('/instances'))!;
		expect(new Headers(request[1]?.headers).has('X-Afterglow-Interaction-Id')).toBe(false);
	});

	it('captures middle-link activation once and native toggles structurally without reading their values', async () => {
		document.body.innerHTML = '<a href="/dashboard/instances/private-id?secret=private-query">link</a><input type="checkbox" value="private-checkbox"><input type="radio" name="private-name" value="private-radio"><input type="image" alt="private-alt" src="/private-source">';
		const link = document.querySelector('a')!;
		link.addEventListener('auxclick', event => event.preventDefault());
		link.dispatchEvent(new MouseEvent('auxclick', { bubbles: true, composed: true, button: 1, cancelable: true }));
		link.dispatchEvent(new MouseEvent('auxclick', { bubbles: true, composed: true, button: 0 }));
		link.dispatchEvent(new MouseEvent('auxclick', { bubbles: true, composed: true, button: 2 }));
		document.querySelector<HTMLInputElement>('input[type="checkbox"]')!.click();
		document.querySelector<HTMLInputElement>('input[type="radio"]')!.click();
		document.querySelector<HTMLInputElement>('input[type="image"]')!.click();
		await collector.flush();
		const rows = sentEvents();
		expect(rows).toHaveLength(4);
		expect(rows.map(row => row.control)).toEqual(['link', 'checkbox', 'option', 'button']);
		expect(rows[0].destination).toBe('/dashboard/instances/:id');
		expect(JSON.stringify(rows)).not.toContain('private');
	});

	it('bounds the queue and batches, exposes failures, never replays and suppresses mock/tutorial actions', async () => {
		document.body.innerHTML = '<button>act</button>';
		for (let i = 0; i < 205; ++i) document.querySelector('button')!.click();
		expect(get(interactionAuditHealth)).toMatchObject({ queued: 200, dropped: 5 });
		transport.mockResolvedValueOnce({ ok: false, status: 401 });
		await collector.flush();
		expect(get(interactionAuditHealth)).toMatchObject({ queued: 180, dropped: 25, failedBatches: 1 });
		expect(sentEvents()).toHaveLength(20);
		suppressed = true; ownerChanged();
		document.querySelector('button')!.click();
		await collector.flush();
		expect(get(interactionAuditHealth).queued).toBe(0);
		expect(sentEvents()).toHaveLength(20);
	});

	it('restores only its own fetch wrapper and removes all delegated listeners on disposal', async () => {
		const replacement = vi.fn(); window.fetch = replacement;
		collector.destroy();
		expect(window.fetch).toBe(replacement);
		document.body.innerHTML = '<button>later</button>';
		document.querySelector('button')!.click();
		window.dispatchEvent(new Event('unhandledrejection'));
		expect(get(interactionAuditHealth).queued).toBe(0);
	});
});
