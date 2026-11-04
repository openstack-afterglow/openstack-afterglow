import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { get } from 'svelte/store';
import { tick } from 'svelte';
import ExperienceSupportCode from '../ExperienceSupportCode.svelte';
import { beginExperienceLoad, experienceState, experienceSupportCode, installExperienceCollector, type ExperienceCollectorController } from '$lib/utils/experience';
import type { InteractionOwner } from '$lib/utils/interactionAudit';
import messages from '$lib/i18n/messages/en/shared.json';

vi.mock('$lib/i18n/ns/shared', () => ({ t: (key: keyof typeof messages) => messages[key] }));

const originalFetch = window.fetch;
const originalClipboard = Object.getOwnPropertyDescriptor(navigator, 'clipboard');
let owner: InteractionOwner;
let collector: ExperienceCollectorController;
let changed: () => void;
let enabled: boolean;
let suppressed: boolean;
let route: string;
let fetcher: Mock;
let clipboard: Mock;
const contract = { schema_version: 2, enabled: true, redaction_revision: 1, max_batch_events: 20, max_body_bytes: 32768 };
function install() {
	collector = installExperienceCollector({ getOwner: () => owner, getRoute: () => route, getBaseUrl: () => '', isEnabled: () => enabled, isSuppressed: () => suppressed, subscribeOwner: callback => { changed = callback; return () => {}; } });
}
function storedRows() {
	return fetcher.mock.calls.filter(([url]) => String(url).endsWith('/experience-events')).flatMap(([, init]) => JSON.parse(String(init.body)).events);
}
async function disclose() {
	await tick();
	const summary = screen.getByText(messages['support.label']);
	await fireEvent.click(summary);
	// JSDOM does not implement the native summary activation behavior.
	const details = summary.closest('details')!;
	details.open = true;
	await fireEvent(details, new Event('toggle'));
	return details;
}

beforeEach(() => {
	owner = { token: 'PRIVATE-BEARER-CANARY', sessionId: 'PRIVATE-SESSION-CANARY', userId: 'PRIVATE-USER-CANARY', identityDomainId: 'home', domainId: 'domain', projectId: 'PRIVATE-PROJECT-CANARY' };
	enabled = true;
	suppressed = false;
	route = '/dashboard/account';
	clipboard = vi.fn(async () => {});
	Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: clipboard } });
	fetcher = vi.fn(async (url: string, init?: RequestInit) => {
		if (url.endsWith('/experience-contract')) return Response.json(contract);
		const events = JSON.parse(String(init?.body)).events;
		return Response.json({ schema_version: 2, accepted: events.length, duplicates: 0 }, { status: 201 });
	});
	window.fetch = fetcher as typeof fetch;
	install();
});
afterEach(() => {
	cleanup();
	collector.destroy();
	window.fetch = originalFetch;
	if (originalClipboard) Object.defineProperty(navigator, 'clipboard', originalClipboard);
	else Reflect.deleteProperty(navigator, 'clipboard');
	vi.restoreAllMocks();
});

describe('support-code disclosure with the real collector', () => {
	it('renders nothing when disabled, suppressed, destroyed or unsupported', async () => {
		enabled = false; changed();
		const view = render(ExperienceSupportCode);
		await tick();
		expect(view.container.textContent).toBe('');
		expect(get(experienceSupportCode)).toBeNull();
		enabled = true; suppressed = true; changed(); await tick();
		expect(view.container.textContent).toBe('');
		suppressed = false; changed();
		experienceState(beginExperienceLoad('account', 'page'), 'ready');
		fetcher.mockImplementation(async () => new Response(null, { status: 404 }));
		await collector.flush(); await tick();
		expect(get(experienceSupportCode)).toBeNull();
		expect(view.container.textContent).toBe('');
		collector.destroy(); await tick();
		expect(view.container.textContent).toBe('');
	});

	it('exposes only the anonymous failed-login segment and copies only on explicit activation without recording its UI', async () => {
		owner = { token: null, userId: null, domainId: null, projectId: null }; route = '/login'; changed();
		const login = beginExperienceLoad('auth', 'auth.login')!;
		experienceState(login, 'error');
		await collector.flush();
		const rowsBefore = storedRows().length;
		const localWrite = vi.spyOn(Storage.prototype, 'setItem');
		const view = render(ExperienceSupportCode);
		const details = await disclose();
		expect(details.querySelector('code')?.textContent).toBe(login.segmentId);
		expect(clipboard).not.toHaveBeenCalled();
		await fireEvent.click(screen.getByRole('button', { name: messages['support.copy'] }));
		await tick();
		expect(clipboard).toHaveBeenCalledExactlyOnceWith(login.segmentId);
		expect(screen.getByRole('status').textContent).toBe(messages['support.copied']);
		await collector.flush();
		expect(storedRows()).toHaveLength(rowsBefore);
		expect(localWrite).not.toHaveBeenCalled();
		expect(view.container.querySelector('a, input, textarea')).toBeNull();
		expect(view.container.textContent).not.toContain('PRIVATE-');
		expect(view.container.textContent).not.toContain(login.pageViewId);
	});

	it('preserves code on credential renewal but clears copied feedback and replaces code across project ABA', async () => {
		render(ExperienceSupportCode); await disclose();
		const first = get(experienceSupportCode)!;
		await fireEvent.click(screen.getByRole('button', { name: messages['support.copy'] })); await tick();
		owner = { ...owner, token: 'RENEWED-PRIVATE-BEARER' }; changed(); await tick();
		expect(get(experienceSupportCode)).toBe(first);
		expect(screen.getByRole('status').textContent).toBe(messages['support.copied']);
		const project = owner.projectId;
		owner = { ...owner, projectId: 'other' }; changed();
		owner = { ...owner, projectId: project }; changed(); await tick();
		expect(get(experienceSupportCode)).not.toBe(first);
		expect(screen.getByRole('status').textContent).toBe('');
		expect(screen.getByRole('button', { name: messages['support.copy'] })).toBeTruthy();
		expect(screen.queryByText(first)).toBeNull();
	});

	it('does not publish late clipboard completion after a scope fence or unmount', async () => {
		const pending = Promise.withResolvers<void>();
		clipboard.mockImplementationOnce(() => pending.promise);
		const view = render(ExperienceSupportCode); await disclose();
		await fireEvent.click(screen.getByRole('button', { name: messages['support.copy'] }));
		owner = { ...owner, userId: 'other-user' }; changed(); await tick();
		pending.resolve(); await tick();
		expect(screen.getByRole('status').textContent).toBe('');
		const afterUnmount = Promise.withResolvers<void>();
		clipboard.mockImplementationOnce(() => afterUnmount.promise);
		await fireEvent.click(screen.getByRole('button', { name: messages['support.copy'] }));
		view.unmount(); afterUnmount.resolve(); await tick();
		expect(screen.queryByRole('status')).toBeNull();
	});

	it.each(['missing', 'denied'])('retains selectable code and explicit manual-copy guidance when clipboard is %s', async kind => {
		if (kind === 'missing') Object.defineProperty(navigator, 'clipboard', { configurable: true, value: undefined });
		else clipboard.mockRejectedValue(new Error('PRIVATE-CLIPBOARD-ERROR'));
		render(ExperienceSupportCode); const details = await disclose();
		const code = get(experienceSupportCode);
		await fireEvent.click(screen.getByRole('button', { name: messages['support.copy'] })); await tick();
		expect(screen.getByRole('status').textContent).toBe(messages['support.unavailable']);
		expect(details.querySelector('code')?.textContent).toBe(code);
		expect(details.textContent).not.toContain('PRIVATE-CLIPBOARD-ERROR');
	});

	it('explains incomplete and unavailable delivery without treating the code as stored-record proof', async () => {
		fetcher.mockImplementation(async () => new Response(null, { status: 503 }));
		experienceState(beginExperienceLoad('account', 'page'), 'error');
		await collector.flush();
		render(ExperienceSupportCode); await disclose();
		expect(screen.getByText(messages['support.partial'])).toBeTruthy();
		expect(screen.getByText(messages['support.help'])).toBeTruthy();
		expect(get(experienceSupportCode)).toMatch(/^[0-9a-f-]{36}$/);
	});

	it('ignores stale collector destruction after a replacement collector owns the code', async () => {
		const previous = collector;
		const oldCode = get(experienceSupportCode);
		install();
		const current = get(experienceSupportCode);
		expect(current).not.toBe(oldCode);
		previous.destroy();
		expect(get(experienceSupportCode)).toBe(current);
		render(ExperienceSupportCode); const details = await disclose();
		expect(details.querySelector('code')?.textContent).toBe(current);
		collector.destroy(); await tick();
		expect(get(experienceSupportCode)).toBeNull();
		expect(screen.queryByText(messages['support.label'])).toBeNull();
	});

	it('does not clear the replacement code when an old collector receives a late unsupported response', async () => {
		const pending = Promise.withResolvers<Response>();
		fetcher.mockImplementationOnce(() => pending.promise);
		experienceState(beginExperienceLoad('account', 'page'), 'ready');
		const oldFlush = collector.flush();
		install();
		const replacement = get(experienceSupportCode);
		render(ExperienceSupportCode); const details = await disclose();
		pending.resolve(new Response(null, { status: 404 }));
		await oldFlush; await tick();
		expect(get(experienceSupportCode)).toBe(replacement);
		expect(details.querySelector('code')?.textContent).toBe(replacement);
	});
});
