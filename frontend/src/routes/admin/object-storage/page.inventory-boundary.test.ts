import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { get } from 'svelte/store';
import { auth } from '$lib/stores/auth';
import { setAdminInventoryScope } from '$lib/stores/adminInventoryScope';
import Page from './+page.svelte';

const media = vi.hoisted(() => {
	const events = new EventTarget();
	const query = {
		matches: true,
		media: '(min-width: 1024px)',
		onchange: null,
		addEventListener: events.addEventListener.bind(events),
		removeEventListener: events.removeEventListener.bind(events),
		addListener: () => undefined,
		removeListener: () => undefined,
		dispatchEvent: events.dispatchEvent.bind(events),
	};
	vi.stubGlobal('matchMedia', () => query);
	return query;
});
const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), delete: vi.fn(), confirm: vi.fn() }));
vi.mock('$lib/api/client', () => ({
	api: mocks,
	ApiError: class ApiError extends Error {},
}));
vi.mock('$lib/stores/confirm.svelte', () => ({ confirmDialog: mocks.confirm }));

const initial = get(auth);
const buckets = [
	{ name: 'same-name', project_id: 'project-a', project_name: 'Alpha', count: 1, bytes: 10 },
	{ name: 'same-name', project_id: 'project-b', project_name: 'Beta', count: 2, bytes: 20 },
];

beforeEach(() => {
	vi.resetAllMocks();
	auth.set({ ...initial, token: 'human-token', sessionId: 'session', userId: 'human', projectId: 'project-a', domainId: 'domain-a', isSystemAdmin: true });
	setAdminInventoryScope('', '');
	mocks.get.mockResolvedValue({ items: buckets, project_count: 2, partial: false, unavailable_projects: [] });
	mocks.delete.mockResolvedValue(undefined);
	mocks.confirm.mockResolvedValue(true);
});
afterEach(() => { auth.set(initial); });

describe.each([true, false])('administrator Swift account inventory (desktop=%s)', desktop => {
	beforeEach(() => {
		media.matches = desktop;
		media.dispatchEvent(new Event('change'));
	});
	it('renders duplicate account-local bucket names and retains each exact owner in detail links', async () => {
		render(Page);
		const links = await screen.findAllByRole('link', { name: 'same-name' });
		expect(links.map(link => link.getAttribute('href'))).toEqual([
			'/admin/object-storage/same-name?project_id=project-a',
			'/admin/object-storage/same-name?project_id=project-b',
		]);
		expect(mocks.get).toHaveBeenCalledWith('/api/v1/admin/object-storage?include_quarantine=true&include_trash=true&include_deleted=true', 'human-token', 'project-a', expect.any(Object));
	});

	it('never deletes the same-name bucket through a foreign row and sends the current row exact owner', async () => {
		render(Page);
		await screen.findAllByRole('link', { name: 'same-name' });
		const buttons = screen.getAllByRole('button', { name: '삭제' }) as HTMLButtonElement[];
		expect(buttons[0].disabled).toBe(false);
		expect(buttons[1].disabled).toBe(true);
		await fireEvent.click(buttons[1]);
		expect(mocks.delete).not.toHaveBeenCalled();
		expect(mocks.confirm).not.toHaveBeenCalled();
		await fireEvent.click(buttons[0]);
		await waitFor(() => expect(mocks.delete).toHaveBeenCalledWith('/api/v1/object-storage/same-name', 'human-token', 'project-a'));
		expect(mocks.delete).toHaveBeenCalledTimes(1);
	});

	it('keeps projectless whole-cloud reads available but disables unowned create and delete', async () => {
		auth.update(value => ({ ...value, projectId: null }));
		render(Page);
		await screen.findAllByRole('link', { name: 'same-name' });
		const create = screen.getByRole('button', { name: '+ 버킷 생성' }) as HTMLButtonElement;
		expect(create.disabled).toBe(true);
		for (const button of screen.getAllByRole('button', { name: '삭제' }) as HTMLButtonElement[]) {
			expect(button.disabled).toBe(true);
			await fireEvent.click(button);
		}
		expect(mocks.post).not.toHaveBeenCalled();
		expect(mocks.delete).not.toHaveBeenCalled();
		expect(mocks.get).toHaveBeenCalledWith('/api/v1/admin/object-storage?include_quarantine=true&include_trash=true&include_deleted=true', 'human-token', undefined, expect.any(Object));
	});
	it('retains readable accounts and discloses missing accounts without presenting global totals', async () => {
		mocks.get.mockResolvedValue({ items: [buckets[0]], project_count: 2, partial: true, unavailable_projects: [{ project_id: 'project-b', project_name: 'Beta', reason: 'denied' }] });
		render(Page);
		await screen.findByRole('link', { name: 'same-name' });
		expect(screen.queryByTestId('inventory-totals')).toBeNull();
		await fireEvent.click(screen.getByText('조회하지 못한 프로젝트'));
		expect(screen.getByText('project-b')).toBeTruthy();
		expect(screen.getByText(/네이티브 접근 거부/)).toBeTruthy();
		expect(screen.getAllByRole('link', { name: 'same-name' })).toHaveLength(1);
	});
	it('does not show a successful empty list when every selected account is unavailable', async () => {
		mocks.get.mockResolvedValue({ items: [], project_count: 1, partial: true, unavailable_projects: [{ project_id: 'project-b', project_name: 'Beta', reason: 'denied' }] });
		render(Page);
		await screen.findByText('조회 가능한 계정에서 표시할 버킷이 없습니다. 전체 목록은 확인되지 않았습니다.');
		expect(screen.queryByText('생성된 버킷이 없습니다.')).toBeNull();
	});
});
