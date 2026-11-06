import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { writable } from 'svelte/store';
import { tick } from 'svelte';
import type * as SvelteReactivity from 'svelte/reactivity';
import type { UserUsageDetail } from '$lib/api/chatQuotas';
import { setLocale } from '$lib/i18n/runtime.svelte';
import { t } from '$lib/i18n/ns/admin-chat-usage';
import { t as commonT } from '$lib/i18n/ns/common';

const mocks = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('$lib/api/client', () => ({ api: { get: mocks.get }, ApiError: class extends Error {} }));
vi.mock('$lib/stores/auth', () => ({ auth: writable({ token: 'admin-token', projectId: 'admin-project' }) }));
vi.mock('svelte/reactivity', async importOriginal => ({
	...await importOriginal<typeof SvelteReactivity>(),
	MediaQuery: class { get current() { return true; } },
}));

import UserUsageDetailModal from './UserUsageDetailModal.svelte';

const userA = { id: 'user-a', name: 'User A', email: 'a@example.test' };
const userB = { id: 'user-b', name: 'User B', email: 'b@example.test' };
function detail(userId: string, model: string): UserUsageDetail {
	const aggregate = { model_name: model, prompt_tokens: 3, completion_tokens: 4, total_tokens: 7, credited_cost: '1', raw_cost: '0.1', request_count: 1 };
	return {
		user_id: userId, range: '30d', period_start: null, period_end: '2026-11-06T00:00:00Z',
		overview: aggregate, by_model: [aggregate], by_source: [], next_before_id: null,
		records: [{ ...aggregate, id: 1, created_at: '2026-11-05T00:00:00Z', provider: null, source: 'web', api_key_id: null, pricing_status: 'priced' }],
	};
}

beforeEach(() => {
	setLocale('en');
	mocks.get.mockReset().mockImplementation((path: string) => Promise.resolve(path.includes('/user-b?') ? detail(userB.id, 'model-b') : detail(userA.id, 'model-a')));
});
afterEach(() => { cleanup(); setLocale('ko'); });

describe('mounted user usage view ownership', () => {
	it.each(['modelUsage', 'ledger'] as const)('retains %s conditions during same-user reads and clears them after close and another user opens', async section => {
		const onClose = vi.fn();
		const { rerender } = render(UserUsageDetailModal, { open: true, user: userA, onClose });
		const ui = () => within(screen.getByRole('region', { name: t(section) }));
		await waitFor(() => expect(ui().getByRole('table')).toBeTruthy());
		const filterLabel = commonT('table.filterColumn', { column: t('model') });
		await fireEvent.click(ui().getByRole('button', { name: filterLabel }));
		const popup = screen.getByRole('dialog', { name: filterLabel });
		await fireEvent.click(within(popup).getByRole('checkbox', { name: 'model-a' }));
		await fireEvent.click(within(popup).getByRole('button', { name: commonT('table.ascending') }));
		await fireEvent.keyDown(popup, { key: 'Escape' });
		await fireEvent.input(ui().getByLabelText(commonT('table.search')), { target: { value: 'model-a' } });
		await fireEvent.change(screen.getByLabelText(t('periodLabel')), { target: { value: '7d' } });
		await waitFor(() => expect(mocks.get).toHaveBeenCalledTimes(2));
		await tick();
		expect((ui().getByLabelText(commonT('table.search')) as HTMLInputElement).value).toBe('model-a');
		expect(ui().getByText(commonT('table.noMatches'))).toBeTruthy();
		expect(ui().getByRole('button', { name: filterLabel }).closest('th')?.getAttribute('aria-sort')).toBe('ascending');

		await rerender({ open: false, user: null, onClose });
		await rerender({ open: true, user: userB, onClose });
		await waitFor(() => expect(ui().getByText('model-b')).toBeTruthy());
		expect((ui().getByLabelText(commonT('table.search')) as HTMLInputElement).value).toBe('');
		expect(ui().queryByText(commonT('table.noMatches'))).toBeNull();
		expect(ui().getByRole('button', { name: filterLabel }).hasAttribute('aria-describedby')).toBe(false);
		expect(ui().getByRole('button', { name: filterLabel }).closest('th')?.getAttribute('aria-sort')).toBe('none');
	});

	it('does not republish a late A response after the kept-mounted modal closes and opens B then A', async () => {
		const old = Promise.withResolvers<UserUsageDetail>();
		mocks.get.mockReturnValueOnce(old.promise);
		const onClose = vi.fn();
		const { rerender } = render(UserUsageDetailModal, { open: true, user: userA, onClose });
		await waitFor(() => expect(mocks.get).toHaveBeenCalledTimes(1));
		await rerender({ open: false, user: null, onClose });
		await rerender({ open: true, user: userB, onClose });
		await screen.findAllByText('model-b');
		await rerender({ open: true, user: userA, onClose });
		await screen.findAllByText('model-a');
		old.resolve(detail(userA.id, 'stale-model-a'));
		await old.promise;
		await tick();
		expect(screen.queryByText('stale-model-a')).toBeNull();
		expect(screen.queryAllByText('model-a').length).toBeGreaterThan(0);
	});
});
