import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { get } from 'svelte/store';
import { tick } from 'svelte';
import AdminEventsPage from '../AdminEventsPage.svelte';
import { auth } from '$lib/stores/auth';
import { adminInventoryScope, setAdminInventoryScope } from '$lib/stores/adminInventoryScope';
import { t as common } from '$lib/i18n/ns/common';
import { initLocale } from '$lib/i18n/runtime.svelte';

const mocks = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('$lib/api/client', async () => ({ api: mocks, ...(await vi.importActual('$lib/api/errors')) }));
async function selectNative(column: string, value: string) {
	const name = common('table.filterColumn', { column });
	await fireEvent.click(screen.getByRole('button', { name }));
	const popup = screen.getByRole('dialog', { name });
	await fireEvent.click(within(popup).getByRole('checkbox', { name: value }));
	await fireEvent.click(within(popup).getByRole('button', { name: common('actions.close') }));
}
const initial = get(auth);
const event = (id: number, source = 'browser') => ({
	id, created_at: `2026-11-01T00:00:0${id}Z`, project_id: 'project-a', user_id: 'actor', username: 'operator',
	service: 'console', page: '/dashboard/compute/instances', source, resource_type: 'interaction', resource_id: null, resource_name: null,
	action: source === 'browser' ? 'click' : 'request', status: source === 'browser' ? 'observed' : 'started', error_message: null,
	request_id: source === 'browser' ? null : 'server-request',
	extra: { control: source === 'browser' ? 'button' : null, ordinal: source === 'browser' ? 7 : null, destination: '/dashboard/compute/instances/:id', interaction_id: 'client-interaction', method: source === 'browser' ? null : 'GET', route: '/api/v1/instances', stage: source === 'browser' ? null : 'started', duration_ms: 12, secret: 'never-render-me' },
});
const stats = { total: 1, success: 0, failed: 0, started: 0, observed: 1, by_service: [], by_project: [], by_action: [], by_page: [] };
beforeEach(() => {
	vi.resetAllMocks(); initLocale('en');
	auth.set({ ...initial, token: 'admin-token', userId: 'operator', projectId: 'operator-project', domainId: 'operator-home', sessionId: 'login-a', isSystemAdmin: true });
	setAdminInventoryScope('', '');
	mocks.get.mockImplementation((path: string) => Promise.resolve(path.includes('/stats?') ? stats : /\/events\/\d+$/.test(path) ? event(1) : [event(1)]));
});
afterEach(() => { cleanup(); auth.set(initial); setAdminInventoryScope('', ''); initLocale('ko'); });

describe('operational event viewer', () => {
	it('filters browser observations and both distinct correlation identifiers without changing caller scope', async () => {
		render(AdminEventsPage);
		await screen.findAllByRole('button', { name: 'View details for click event 1' });
		await selectNative('Status', 'Observed');
		await selectNative('Source', 'browser');
		await fireEvent.input(screen.getByLabelText('Request ID'), { target: { value: 'server-request' } });
		await fireEvent.input(screen.getByLabelText('Client interaction ID'), { target: { value: 'client-interaction' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Apply filters' }));
		await waitFor(() => expect(mocks.get.mock.calls.some(([path]) => path.includes('source=browser') && path.includes('status=observed') && path.includes('request_id=server-request') && path.includes('interaction_id=client-interaction'))).toBe(true));
		expect(get(auth).projectId).toBe('operator-project');
		expect(screen.getByText('Observed 1 · not business outcomes')).toBeTruthy();
	});

	it('shows allowlisted structural details and a bounded source-filterable chronological timeline', async () => {
		mocks.get.mockImplementation((path: string) => Promise.resolve(path.includes('/stats?') ? stats : /\/events\/\d+$/.test(path) ? event(1) : path.includes('interaction_id=') ? [event(2, 'afterglow'), event(1)] : [event(1)]));
		render(AdminEventsPage);
		await fireEvent.click((await screen.findAllByRole('button', { name: 'View details for click event 1' }))[0]);
		await screen.findByText('Control ordinal');
		expect(screen.getByText('7')).toBeTruthy();
		expect(screen.queryByText('never-render-me')).toBeNull();
		const timeline = await screen.findByRole('region', { name: 'Correlation timeline' });
		expect(within(timeline).getAllByRole('listitem')).toHaveLength(2);
		expect(within(timeline).getAllByRole('listitem')[0].textContent).toContain('Browser');
		const timelineSection = screen.getByRole('heading', { name: 'Correlation timeline' }).closest('section')!;
		const filterName = common('table.filterColumn', { column: 'Source' });
		await fireEvent.click(within(timelineSection).getByRole('button', { name: filterName }));
		const popup = screen.getByRole('dialog', { name: filterName });
		await fireEvent.click(within(popup).getByRole('button', { name: common('table.selectNone') }));
		await fireEvent.click(within(popup).getByRole('checkbox', { name: 'afterglow' }));
		await fireEvent.click(within(popup).getByRole('button', { name: common('actions.close') }));
		const filteredTimeline = screen.getByRole('region', { name: 'Correlation timeline' });
		expect(within(filteredTimeline).getAllByRole('listitem')).toHaveLength(1);
		expect(within(filteredTimeline).getByText(/GET \/api\/v1\/instances/)).toBeTruthy();
		expect(within(filteredTimeline).getByRole('button', { name: 'View details for request event 2' })).toBeTruthy();
	});

	it('discards stale detail and timeline responses across scope ABA and logout', async () => {
		const oldDetail = Promise.withResolvers<object>();
		mocks.get.mockImplementation((path: string) => path.endsWith('/events/1') ? oldDetail.promise : Promise.resolve(path.includes('/stats?') ? stats : [event(1)]));
		render(AdminEventsPage);
		await fireEvent.click((await screen.findAllByRole('button', { name: 'View details for click event 1' }))[0]);
		setAdminInventoryScope('domain-b', 'project-b'); await tick();
		setAdminInventoryScope('', ''); await tick();
		oldDetail.resolve({ ...event(1), resource_name: 'stale-owner-detail' });
		await tick(); await Promise.resolve(); await tick();
		expect(screen.queryByText('stale-owner-detail')).toBeNull();
		expect(screen.queryByRole('region', { name: 'Correlation timeline' })).toBeNull();
		auth.set(initial); await tick();
		expect(screen.queryAllByRole('button', { name: 'View details for click event 1' })).toHaveLength(0);
		expect(get(adminInventoryScope).projectId).toBe('');
	});

	it('fences a late correlation timeline across scope ABA without leaving previous rows visible', async () => {
		const oldTimeline = Promise.withResolvers<object[]>();
		mocks.get.mockImplementation((path: string) => path.includes('/stats?') ? Promise.resolve(stats)
			: path.endsWith('/events/1') ? Promise.resolve(event(1))
			: path.includes('interaction_id=') ? oldTimeline.promise : Promise.resolve([event(1)]));
		render(AdminEventsPage);
		await fireEvent.click((await screen.findAllByRole('button', { name: 'View details for click event 1' }))[0]);
		await waitFor(() => expect(mocks.get.mock.calls.some(([path]) => path.includes('interaction_id=client-interaction'))).toBe(true));
		setAdminInventoryScope('domain-b', 'project-b'); await tick();
		setAdminInventoryScope('', ''); await tick();
		oldTimeline.resolve([{ ...event(2, 'afterglow'), action: 'stale-timeline-row' }]);
		await tick(); await Promise.resolve(); await tick();
		expect(screen.queryByText('stale-timeline-row')).toBeNull();
		expect(screen.queryByRole('region', { name: 'Correlation timeline' })).toBeNull();
	});
});
