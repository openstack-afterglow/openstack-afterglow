import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { writable } from 'svelte/store';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { secretsApi } = vi.hoisted(() => ({ secretsApi: {
	listSecrets: vi.fn(), listContainers: vi.fn(), listOrders: vi.fn(), getEffectiveQuota: vi.fn(),
	getPayload: vi.fn(), deleteSecret: vi.fn(), deleteContainer: vi.fn(),
	createSecret: vi.fn(), createContainer: vi.fn(), createOrder: vi.fn(),
} }));
vi.mock('$lib/api/secrets', () => ({ secretsApi }));
vi.mock('$lib/stores/auth', () => ({ auth: writable({ token: 'token', projectId: 'project' }) }));
vi.mock('$lib/stores/betaFeatures', () => ({ betaFeatures: writable({ keyManager: true }) }));
vi.mock('$lib/utils/autoRefresh.svelte', () => ({
	createAutoRefresh: () => ({ active: false, intervalSeconds: 30, intervalOptions: [10, 30, 60] }),
}));
vi.mock('$lib/stores/toast', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));
vi.mock('$lib/stores/confirm.svelte', () => ({ confirmDialog: vi.fn().mockResolvedValue(true) }));

import Page from '../+page.svelte';
import { auth } from '$lib/stores/auth';
import { tick } from 'svelte';
import { t as tc } from '$lib/i18n/ns/common';
import { t as td } from '$lib/i18n/ns/dashboard-home';

function deferred<T>() {
	let resolve!: (value: T) => void;
	const promise = new Promise<T>((yes) => { resolve = yes; });
	return { promise, resolve };
}
const secret = (id: string) => ({ id, name: id, secret_type: 'passphrase', status: 'ACTIVE', system_managed: false });

beforeEach(() => {
	vi.clearAllMocks();
	auth.update(state => ({ ...state, token: 'token', userId: 'user', sessionId: 'session', projectId: 'project' }));
	secretsApi.listSecrets.mockResolvedValue([secret('first'), secret('second')]);
	secretsApi.listContainers.mockResolvedValue([]);
	secretsApi.listOrders.mockResolvedValue([]);
	secretsApi.getEffectiveQuota.mockResolvedValue(null);
});
afterEach(cleanup);

describe('Key Manager operation status', () => {
	it.each([
		['secrets', 'secrets.tabs.secrets', 'secrets.empty.secrets'],
		['containers', 'secrets.tabs.containers', 'secrets.empty.containers'],
		['orders', 'secrets.tabs.orders', 'secrets.empty.orders'],
	] as const)('distinguishes %s read failure, verified empty, filtered rows and retained successful data', async (tab, tabKey, emptyKey) => {
		const getter = tab === 'secrets' ? secretsApi.listSecrets : tab === 'containers' ? secretsApi.listContainers : secretsApi.listOrders;
		getter.mockRejectedValue(new Error('native read unavailable'));
		render(Page);
		if (tab !== 'secrets') await fireEvent.click(screen.getByRole('button', { name: td(tabKey) }));
		await screen.findByRole('alert');
		expect(screen.queryByText(td(emptyKey))).toBeNull();
		expect(screen.queryByText(tc('table.noMatches'))).toBeNull();
		getter.mockResolvedValue([]);
		await fireEvent.click(screen.getByTitle('지금 새로고침'));
		await waitFor(() => expect(screen.queryByRole('alert')).toBeNull());
		expect(screen.getByText(td(emptyKey))).toBeTruthy();
		await fireEvent.input(screen.getByRole('searchbox'), { target: { value: '^not-present$' } });
		expect(screen.getByText(td(emptyKey))).toBeTruthy();
		expect(screen.queryByText(tc('table.noMatches'))).toBeNull();
		await fireEvent.input(screen.getByRole('searchbox'), { target: { value: '' } });
		const rows = tab === 'secrets' ? [secret('retained')] : tab === 'containers'
			? [{ id: 'retained', name: 'retained', type: 'generic', status: 'ACTIVE', secret_refs: [] }]
			: [{ id: 'retained', type: 'key', status: 'ACTIVE', created: null, secret_ref: null, error_reason: null }];
		getter.mockResolvedValue(rows);
		await fireEvent.click(screen.getByTitle('지금 새로고침'));
		expect((await screen.findAllByText('retained')).length).toBeGreaterThan(0);
		await fireEvent.input(screen.getByRole('searchbox'), { target: { value: '^not-present$' } });
		expect(screen.getByText(tc('table.noMatches'))).toBeTruthy();
		expect(screen.queryByText(td(emptyKey))).toBeNull();
		await fireEvent.input(screen.getByRole('searchbox'), { target: { value: '' } });
		getter.mockRejectedValue(new Error('refresh unavailable'));
		await fireEvent.click(screen.getByTitle('지금 새로고침'));
		await screen.findByRole('alert');
		expect(screen.getByText(tc('table.lastSuccessfulRead'))).toBeTruthy();
		expect(screen.getAllByText('retained').length).toBeGreaterThan(0);
		expect(screen.queryByText(td(emptyKey))).toBeNull();
	});

	it('retains regex, column filters and sorting on token renewal but resets on a new logical session', async () => {
		render(Page);
		await screen.findByText('first', { selector: 'span' });
		const search = screen.getByRole('searchbox') as HTMLInputElement;
		await fireEvent.input(search, { target: { value: '^first$' } });
		const name = td('secrets.form.name');
		await fireEvent.click(screen.getByRole('button', { name: tc('table.sortColumn', { column: name, direction: tc('table.none') }) }));
		const statusFilter = tc('table.filterColumn', { column: td('secrets.table.status') });
		await fireEvent.click(screen.getByRole('button', { name: statusFilter }));
		await fireEvent.click(screen.getByRole('button', { name: tc('table.selectNone') }));
		await fireEvent.keyDown(screen.getByRole('dialog', { name: statusFilter }), { key: 'Escape' });
		auth.update(state => ({ ...state, token: 'renewed-token', refreshToken: 'renewed-refresh' }));
		await tick();
		expect(search.value).toBe('^first$');
		expect(screen.getByRole('button', { name: tc('table.sortColumn', { column: name, direction: tc('table.ascending') }) })).toBeTruthy();
		expect(screen.queryByText('first', { selector: 'span' })).toBeNull();
		await fireEvent.click(screen.getByRole('button', { name: statusFilter }));
		await fireEvent.click(screen.getByRole('button', { name: tc('table.resetFilter') }));
		await fireEvent.keyDown(screen.getByRole('dialog', { name: statusFilter }), { key: 'Escape' });
		expect(screen.getByText('first', { selector: 'span' })).toBeTruthy();
		expect(screen.queryByText('second', { selector: 'span' })).toBeNull();
		auth.update(state => ({ ...state, sessionId: 'different-session' }));
		await tick();
		expect(search.value).toBe('');
		expect(await screen.findByText('second', { selector: 'span' })).toBeTruthy();
		expect(screen.getByRole('button', { name: tc('table.sortColumn', { column: name, direction: tc('table.none') }) })).toBeTruthy();
	});

	it('serializes pending payload requests and reveals their results', async () => {
		const pending = deferred<string>();
		secretsApi.getPayload.mockReturnValue(pending.promise);
		render(Page);
		const firstRow = (await screen.findByText('first', { selector: 'span' })).closest('tr')!;
		const secondRow = screen.getByText('second', { selector: 'span' }).closest('tr')!;
		await fireEvent.click(within(firstRow).getByRole('button', { name: '값 보기' }));
		expect((within(secondRow).getByRole('button', { name: '값 보기' }) as HTMLButtonElement).disabled).toBe(true);
		pending.resolve('payload-value');
		expect(await within(firstRow).findByText('payload-value')).toBeTruthy();
		expect((within(secondRow).getByRole('button', { name: '값 보기' }) as HTMLButtonElement).disabled).toBe(false);
		await fireEvent.click(within(firstRow).getByRole('button', { name: '숨기기' }));
		expect(within(firstRow).queryByText('payload-value')).toBeNull();
	});

	it('hides an already revealed secret while another payload is pending', async () => {
		const pending = deferred<string>();
		secretsApi.getPayload.mockResolvedValueOnce('first-sensitive-value').mockReturnValueOnce(pending.promise);
		render(Page);
		const firstRow = (await screen.findByText('first', { selector: 'span' })).closest('tr')!;
		const secondRow = screen.getByText('second', { selector: 'span' }).closest('tr')!;
		await fireEvent.click(within(firstRow).getByRole('button', { name: '값 보기' }));
		await within(firstRow).findByText('first-sensitive-value');
		await fireEvent.click(within(secondRow).getByRole('button', { name: '값 보기' }));
		const hide = within(firstRow).getByRole('button', { name: '숨기기' }) as HTMLButtonElement;
		expect(hide.disabled).toBe(false);
		await fireEvent.click(hide);
		expect(within(firstRow).queryByText('first-sensitive-value')).toBeNull();
		pending.resolve('second-sensitive-value');
		await within(secondRow).findByText('second-sensitive-value');
		expect(within(firstRow).queryByText('first-sensitive-value')).toBeNull();
	});

	it('ends a secret deletion indicator after the API settles', async () => {
		const pending = deferred<void>();
		secretsApi.deleteSecret.mockReturnValue(pending.promise);
		render(Page);
		const row = (await screen.findByText('first', { selector: 'span' })).closest('tr')!;
		await fireEvent.click(within(row).getByRole('button', { name: '삭제' }));
		expect((within(row).getByRole('button', { name: /삭제/ }) as HTMLButtonElement).disabled).toBe(true);
		pending.resolve();
		await waitFor(() => expect((within(row).getByRole('button', { name: /삭제/ }) as HTMLButtonElement).disabled).toBe(false));
	});

	it('ends a container deletion indicator after the API settles', async () => {
		secretsApi.listContainers.mockResolvedValue([{ id: 'container-1', name: 'Stored container', type: 'generic', status: 'ACTIVE', secret_refs: [] }]);
		const pending = deferred<void>();
		secretsApi.deleteContainer.mockReturnValue(pending.promise);
		render(Page);
		await screen.findByText('first', { selector: 'span' });
		await fireEvent.click(screen.getByRole('button', { name: '컨테이너' }));
		const button = await screen.findByRole('button', { name: '삭제' });
		await fireEvent.click(button);
		expect((button as HTMLButtonElement).disabled).toBe(true);
		pending.resolve();
		await waitFor(() => expect((button as HTMLButtonElement).disabled).toBe(false));
	});

	it('keeps keyed Order rows through refresh and stops work at a terminal result', async () => {
		const order = { id: 'order-1', type: 'key', status: 'PENDING', secret_ref: null, error_reason: null };
		secretsApi.listOrders.mockResolvedValueOnce([order]).mockResolvedValue([{ ...order, status: 'ACTIVE', secret_ref: 'secret-ref' }]);
		render(Page);
		await screen.findByText('first', { selector: 'span' });
		await fireEvent.click(screen.getByRole('button', { name: 'Key Orders' }));
		const originalRow = (await screen.findByText('order-1')).closest('tr')!;
		expect(within(originalRow).getByRole('status')).toBeTruthy();
		await fireEvent.click(screen.getByTitle('지금 새로고침'));
		expect(screen.getByText('order-1').closest('tr')).toBe(originalRow);
		await waitFor(() => expect(within(originalRow).queryByRole('status')).toBeNull());
	});
});
