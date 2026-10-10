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

function deferred<T>() {
	let resolve!: (value: T) => void;
	const promise = new Promise<T>((yes) => { resolve = yes; });
	return { promise, resolve };
}
const secret = (id: string) => ({ id, name: id, secret_type: 'passphrase', status: 'ACTIVE', system_managed: false });

beforeEach(() => {
	vi.clearAllMocks();
	secretsApi.listSecrets.mockResolvedValue([secret('first'), secret('second')]);
	secretsApi.listContainers.mockResolvedValue([]);
	secretsApi.listOrders.mockResolvedValue([]);
	secretsApi.getEffectiveQuota.mockResolvedValue(null);
});
afterEach(cleanup);

describe('Key Manager operation status', () => {
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
