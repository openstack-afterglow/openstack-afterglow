import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { tick } from 'svelte';
import { writable } from 'svelte/store';
import type * as TransferModule from '$lib/api/adminVolumeTransfers';
const mocks = vi.hoisted(() => ({ create: vi.fn(), lookup: vi.fn(), accept: vi.fn(), cancel: vi.fn(), pending: vi.fn(), copy: vi.fn() }));
vi.mock('$lib/api/adminVolumeTransfers', async (original) => ({ ...await original<typeof TransferModule>(), adminVolumeTransfers: mocks }));
vi.mock('$lib/api/client', () => ({ getBaseUrl: () => '', clearPrefetchCache: vi.fn(), ApiError: class extends Error { status = 503; } }));
vi.mock('$lib/stores/auth', () => ({ auth: writable({ token: 'human-jwt', userId: 'human', sessionId: 'session', projectId: 'home', identityDomainId: 'accounts', domainId: 'home-domain', isSystemAdmin: true }), projectSwitching: writable(false) }));
vi.mock('$lib/stores/adminInventoryScope', () => ({ adminInventoryScope: writable({ revision: 0, domainId: '', projectId: '' }) }));
vi.mock('$lib/i18n/ns/volume', () => ({ t: (key: string) => key }));
vi.mock('$lib/i18n/ns/admin-storage', () => ({ t: (key: string) => key }));
vi.mock('$lib/i18n/ns/domain-admin', () => ({ t: (key: string) => key }));
vi.mock('$lib/api/domains', () => ({ domainsApi: { list: vi.fn(async () => ({ items: [{ id: 'target-domain', name: 'Foreign domain' }] })) } }));
vi.mock('$lib/stores/projectNames', () => ({ projectNames: { loadMetadata: vi.fn(async () => ({ failed: false, projects: [{ id: 'target-project', name: 'Foreign project', domain_id: 'target-domain' }] })) } }));
import { auth, projectSwitching } from '$lib/stores/auth';
import { adminInventoryScope } from '$lib/stores/adminInventoryScope';
import { VolumeTransferError } from '$lib/api/adminVolumeTransfers';
import Modal from '../AdminVolumeTransferModal.svelte';

const transferId = '11111111-1111-4111-8111-111111111111';
const origin = { id: transferId, volume_id: 'foreign-volume', name: 'transfer', volume_name: 'Foreign volume', size: 12, volume_type: 'fast', status: 'awaiting-transfer', source_domain: { id: 'source-domain', name: 'Source domain' }, source_project: { id: 'source-project', name: 'Source project' } };
const actor = { token: 'human-jwt', userId: 'human', sessionId: 'session', projectId: 'home', identityDomainId: 'accounts', domainId: 'home-domain', isSystemAdmin: true };
function setup(initialMode: 'create' | 'receive' = 'create') {
	const callbacks = { onClose: vi.fn(), onSuccess: vi.fn() };
	return { ...render(Modal, { volume: initialMode === 'create' ? { id: 'foreign-volume', name: 'Foreign volume', status: 'available' } : null, initialMode, ...callbacks }), ...callbacks };
}
async function generate() { await fireEvent.click(screen.getByRole('button', { name: 'transferModal.createTitle' })); await screen.findByText('one-time-key'); await screen.findByText(/Source domain/); }
async function destination() {
	const domain = await screen.findByRole('button', { name: 'scope.domain' });
	await waitFor(() => expect((domain as HTMLButtonElement).disabled).toBe(false));
	await fireEvent.click(domain); await fireEvent.click(screen.getByRole('option', { name: /Foreign domain/ }));
	await fireEvent.click(screen.getByRole('button', { name: 'scope.project' })); await fireEvent.click(screen.getByRole('option', { name: /Foreign project/ }));
}
const receive = () => screen.getByRole('button', { name: 'transferModal.receiveTitle' });
beforeEach(() => {
	vi.clearAllMocks(); auth.set(actor as never); projectSwitching.set(false); adminInventoryScope.set({ revision: 0, domainId: '', projectId: '' } as never);
	mocks.create.mockResolvedValue({ ...origin, auth_key: 'one-time-key' }); mocks.lookup.mockResolvedValue(origin); mocks.accept.mockResolvedValue(origin); mocks.pending.mockResolvedValue([{ id: transferId, volume_id: 'foreign-volume' }]); mocks.cancel.mockResolvedValue(undefined); mocks.copy.mockResolvedValue(undefined);
	Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: mocks.copy } });
});

describe('administrator volume transfer task and secret boundaries', () => {
	it('generates copyable credentials without claiming acceptance, then accepts into selected actual project', async () => {
		const view = setup(); await generate();
		expect(mocks.accept).not.toHaveBeenCalled(); expect(view.onClose).not.toHaveBeenCalled();
		await fireEvent.click(screen.getByRole('button', { name: 'transferModal.copyKey' })); expect(mocks.copy).toHaveBeenCalledWith('one-time-key');
		await destination(); await fireEvent.click(receive());
		await waitFor(() => expect(view.onClose).toHaveBeenCalledOnce());
		expect(mocks.accept).toHaveBeenCalledWith(expect.objectContaining({ token: 'human-jwt', projectId: 'home' }), transferId, 'one-time-key', 'target-domain', 'target-project');
	});
	it('distinguishes successful issuance from failed source detail lookup', async () => {
		mocks.lookup.mockRejectedValue(new VolumeTransferError(503, false)); setup();
		await fireEvent.click(screen.getByRole('button', { name: 'transferModal.createTitle' }));
		await screen.findByText('transferModal.lookupFailed'); expect(screen.getByText('one-time-key')).toBeTruthy();
		expect(screen.queryByText('transferModal.createFailed')).toBeNull(); expect(mocks.create).toHaveBeenCalledOnce();
	});
	it('accepts a supplied ID/key without a source-volume row or a second create', async () => {
		setup('receive'); await fireEvent.input(screen.getByLabelText('transferModal.idLabel'), { target: { value: transferId } }); await fireEvent.click(screen.getByRole('button', { name: 'transferModal.search' }));
		await screen.findByText(/Source domain/); await destination();
		await fireEvent.input(screen.getByLabelText('transferModal.authKeyLabel'), { target: { value: 'supplied-key' } }); await fireEvent.click(receive());
		await waitFor(() => expect(mocks.accept).toHaveBeenCalledOnce()); expect(mocks.create).not.toHaveBeenCalled(); expect(mocks.accept.mock.calls[0].slice(1)).toEqual([transferId, 'supplied-key', 'target-domain', 'target-project']);
	});
	it('leaves the generated ID/key copyable after native scope denial and never cancels', async () => {
		mocks.accept.mockRejectedValue(new VolumeTransferError(403, false)); const view = setup(); await generate(); await destination(); await fireEvent.click(receive());
		await screen.findByText('volumeTransfer.denied'); expect(screen.getByText('one-time-key')).toBeTruthy(); expect(mocks.cancel).not.toHaveBeenCalled(); expect(view.onClose).not.toHaveBeenCalled();
	});
	it('does not replay or offer acceptance again after an uncertain write', async () => {
		mocks.accept.mockRejectedValue(new VolumeTransferError(503, true)); setup(); await generate(); await destination(); await fireEvent.click(receive());
		await screen.findByText('volumeTransfer.uncertain'); expect((receive() as HTMLButtonElement).disabled).toBe(true); expect(mocks.accept).toHaveBeenCalledOnce(); expect(mocks.cancel).not.toHaveBeenCalled(); expect(screen.getByText('one-time-key')).toBeTruthy();
	});
	it.each(['auth', 'inventory', 'switch'])('discards secrets synchronously on %s boundary including ABA restoration', async (boundary) => {
		setup(); await generate();
		if (boundary === 'auth') { auth.set({ ...actor, sessionId: 'replacement-login' } as never); auth.set(actor as never); }
		else if (boundary === 'inventory') { adminInventoryScope.set({ revision: 1 } as never); adminInventoryScope.set({ revision: 0 } as never); }
		else { projectSwitching.set(true); projectSwitching.set(false); }
		await tick(); expect(screen.queryByText('one-time-key')).toBeNull(); expect(screen.getByText('transferModal.scopeChanged')).toBeTruthy(); expect(mocks.accept).not.toHaveBeenCalled();
	});
	it('keeps once-only keys through a routine bearer rotation and uses the current token to accept', async () => {
		const view = setup(); await generate();
		auth.set({ ...actor, token: 'renewed-human-jwt' } as never);
		await tick(); expect(screen.getByText('one-time-key')).toBeTruthy();
		await destination(); await fireEvent.click(receive());
		await waitFor(() => expect(view.onClose).toHaveBeenCalledOnce());
		expect(mocks.accept.mock.calls[0][0].token).toBe('renewed-human-jwt');
	});
	it('derives the explicit destination domain when selecting a project from all domains', async () => {
		setup(); await generate();
		const project = await screen.findByRole('button', { name: 'scope.project' });
		await waitFor(() => expect((project as HTMLButtonElement).disabled).toBe(false));
		await fireEvent.click(project); await fireEvent.click(screen.getByRole('option', { name: /Foreign project/ }));
		await waitFor(() => expect((receive() as HTMLButtonElement).disabled).toBe(false));
		await fireEvent.click(receive());
		await waitFor(() => expect(mocks.accept).toHaveBeenCalledOnce());
		expect(mocks.accept.mock.calls[0].slice(3)).toEqual(['target-domain', 'target-project']);
	});

	it('recovers only the pending ID, with explicit cancellation before recreation', async () => {
		setup(); await fireEvent.click(screen.getByRole('button', { name: 'volumeTransfer.recover' })); await screen.findByText('volumeTransfer.recoveryHelp'); expect(mocks.cancel).not.toHaveBeenCalled();
		await fireEvent.click(screen.getByRole('button', { name: 'transferModal.cancel' })); await waitFor(() => expect(mocks.cancel).toHaveBeenCalledOnce()); expect(mocks.create).not.toHaveBeenCalled();
	});
	it('drops late issued secrets when the mounted source changes', async () => {
		const { promise, resolve } = Promise.withResolvers<unknown>(); mocks.create.mockReturnValue(promise);
		const view = setup(); await fireEvent.click(screen.getByRole('button', { name: 'transferModal.createTitle' }));
		await view.rerender({ volume: { id: 'other-volume', name: 'Other', status: 'available' } });
		resolve({ ...origin, auth_key: 'late-key' }); await tick(); expect(screen.queryByText('late-key')).toBeNull(); expect(mocks.lookup).not.toHaveBeenCalled(); expect(view.onSuccess).not.toHaveBeenCalled();
	});
});
