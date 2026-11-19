import { setVerifiedLumenActor } from '../../chat/__tests__/lumenPermissionFixture';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { t } from '$lib/i18n/ns/chat-settings';
import { initLocale } from '$lib/i18n/runtime.svelte';
import { ApiError } from '$lib/api/client';
import AdminDomainPoolsPage from '../../../../routes/admin/chat/domain-pools/+page.svelte';
import AdminServiceKeysPage from '../../../../routes/admin/chat/service-keys/+page.svelte';

const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn(), confirm: vi.fn(), success: vi.fn(), error: vi.fn(), dispatch: vi.fn() }));
vi.mock('$lib/api/client', () => ({
	// The real client runs beforeDispatch immediately before the network send.
	api: { get: mocks.get, patch: mocks.patch, post: (...args: unknown[]) => { mocks.dispatch(args[4]); return mocks.post(...args); } },
	ApiError: class extends Error { constructor(public status: number, message: string) { super(message); } }
}));
vi.mock('$lib/stores/confirm.svelte', () => ({ confirmDialog: mocks.confirm }));
vi.mock('$lib/stores/toast', () => ({ toast: { success: mocks.success, error: mocks.error } }));

const base = '/api/v1/chat/admin';
const pool = {
	domain_id: 'domain-a', balance_credits: '2', reserved_credits: '1', monthly_used_credits: '5',
	manager_monthly_limit_credits: '9', admin_ceiling_credits: '10', is_active: true,
};
const domain = { id: 'domain-a', name: 'Research lab', enabled: true };
const unfundedDomain = { id: 'domain-b', name: 'New lab', enabled: true };

function login(isSystemAdmin: boolean, userId = 'admin-fixture') {
	setVerifiedLumenActor({
		token: 'session-token', refreshToken: null, accessExpiresAt: null,
		userId, username: 'admin', projectId: 'project-1', projectName: 'Project',
		availableProjects: [], roles: [], isSystemAdmin, federated: false,
		domainId: 'default', domainName: 'Default', isDomainManager: false,
	});
}

function card(name: string): HTMLElement {
	return screen.getByRole('heading', { name }).closest('.card') as HTMLElement;
}

function pendingKeys(): string[] {
	return Object.keys(localStorage).filter((name) => name.startsWith('afterglow:lumen-topup:v1:'));
}
const lookupPath = `${base}/domain-pools/domain-a/topups/recorded-key`;
let lookup: unknown;

function seedPending() {
	localStorage.setItem('afterglow:lumen-topup:v1:admin-fixture:domain-a', JSON.stringify({
		v: 1, userId: 'admin-fixture', domainId: 'domain-a', key: 'recorded-key', amount_credits: '3', note: null, created_at: '2026-11-18T00:00:00Z',
	}));
}

const slot = 'afterglow:lumen-topup:v1:admin-fixture:domain-a';

/** FIFO exclusive Web Locks double shared by every simulated tab in this document. */
function installLocks(): string[] {
	const requests: string[] = [];
	const tails = new Map<string, Promise<unknown>>();
	const request = (name: string, callback: () => unknown) => {
		requests.push(name);
		const run = (tails.get(name) ?? Promise.resolve()).then(() => callback());
		tails.set(name, run.catch(() => undefined));
		return run;
	};
	Object.defineProperty(navigator, 'locks', { value: { request }, configurable: true });
	return requests;
}

type Tab = { container: HTMLElement };
const researchIn = (tab: Tab) => within(tab.container).getByRole('heading', { name: 'Research lab' }).closest('.card') as HTMLElement;

async function sendFrom(tab: Tab, value: string) {
	await fireEvent.click(within(researchIn(tab)).getByRole('button', { name: t('domainBilling.topup') }));
	// Each simulated tab opens its own dialog; the newest one belongs to this tab.
	const dialog = (await screen.findAllByRole('dialog', { name: t('domainBilling.topup') })).at(-1) as HTMLElement;
	await fireEvent.input(within(dialog).getByLabelText(t('domainBilling.amount')), { target: { value } });
	await fireEvent.click(within(dialog).getByRole('button', { name: t('domainBilling.reviewTopup') }));
}

beforeEach(() => {
	vi.resetAllMocks();
	localStorage.clear();
	initLocale('en');
	login(true);
	lookup = { found: false, entry: null };
	mocks.dispatch.mockImplementation((options?: { beforeDispatch?: () => void }) => options?.beforeDispatch?.());
	mocks.get.mockImplementation(async (path: string) => {
		if (path === '/api/v1/admin/domains') return { items: [domain, unfundedDomain] };
		if (path === `${base}/domain-pools`) return { items: [pool] };
		if (path.startsWith(`${base}/domain-pools/domain-a/topups/`)) return lookup;
		throw new Error(`Unexpected GET ${path}`);
	});
});
afterEach(() => {
	cleanup();
	Reflect.deleteProperty(navigator, 'locks');
});

it('blocks a concurrent tab under the slot lock and clears only the claimed key', async () => {
	const locks = installLocks();
	mocks.confirm.mockResolvedValue(true);
	const replyA = Promise.withResolvers<unknown>();
	mocks.post.mockImplementationOnce(() => replyA.promise);
	const tabA = render(AdminDomainPoolsPage);
	const tabB = render(AdminDomainPoolsPage);
	await within(tabA.container).findByText('Research lab');
	await within(tabB.container).findByText('Research lab');

	await sendFrom(tabA, '7');
	await waitFor(() => expect(mocks.post).toHaveBeenCalledTimes(1));
	const keyA = mocks.post.mock.calls[0][4].idempotencyKey;
	expect(JSON.parse(localStorage.getItem(slot) ?? 'null')).toMatchObject({ key: keyA, amount_credits: '7' });

	// Tab B mounted before A claimed the slot, so its own view starts empty.
	await sendFrom(tabB, '9');
	await within(researchIn(tabB)).findByText(t('domainBilling.pendingElsewhere'));
	expect(within(researchIn(tabB)).getByText(t('domainBilling.pendingTopupTitle'))).toBeTruthy();
	expect(within(researchIn(tabB)).getByText(/\b7\b/)).toBeTruthy();
	expect(mocks.post).toHaveBeenCalledTimes(1);
	expect(locks.filter((name) => name === 'afterglow-topup:admin-fixture:domain-a').length).toBeGreaterThanOrEqual(2);

	replyA.resolve({ ...pool, balance_credits: '9' });
	await waitFor(() => expect(localStorage.getItem(slot)).toBeNull());
	expect(within(researchIn(tabA)).queryByText(t('domainBilling.pendingTopupTitle'))).toBeNull();
	// A real browser notifies the other tab with a storage event.
	window.dispatchEvent(new StorageEvent('storage', { key: slot }));
	await waitFor(() => expect(within(researchIn(tabB)).queryByText(t('domainBilling.pendingTopupTitle'))).toBeNull());
	expect(mocks.post).toHaveBeenCalledTimes(1);
});

it('never lets a stale tab resolving an older key delete the current record', async () => {
	installLocks();
	localStorage.setItem(slot, JSON.stringify({
		v: 1, userId: 'admin-fixture', domainId: 'domain-a', key: 'stale-key', amount_credits: '3', note: null, created_at: '2026-11-18T00:00:00Z',
	}));
	lookup = { found: true, entry: { kind: 'topup', amount_credits: '3.00000000', balance_after: '5.00000000', note: null, created_at: '2026-11-18T00:00:01+00:00', actor_user_id: null } };
	render(AdminDomainPoolsPage);
	const row = (await screen.findByText(t('domainBilling.pendingTopupTitle'))).closest('.card') as HTMLElement;
	// Another tab resolved the stale key and claimed the slot with key A; no event reached this tab yet.
	localStorage.setItem(slot, JSON.stringify({
		v: 1, userId: 'admin-fixture', domainId: 'domain-a', key: 'recorded-key', amount_credits: '5', note: null, created_at: '2026-11-18T00:01:00Z',
	}));
	await fireEvent.click(within(row).getByRole('button', { name: t('domainBilling.recheck') }));
	await waitFor(() => expect(mocks.success).toHaveBeenCalled());
	expect(mocks.get).toHaveBeenCalledWith(`${base}/domain-pools/domain-a/topups/stale-key`, 'session-token', 'project-1', expect.anything());
	await within(card('Research lab')).findByText(/^5 credits · /);
	expect(JSON.parse(localStorage.getItem(slot) ?? 'null')).toMatchObject({ key: 'recorded-key' });
	expect(mocks.post).not.toHaveBeenCalled();
});

it('updates the pending UI live from storage events and focus', async () => {
	render(AdminDomainPoolsPage);
	await screen.findByText('Research lab');
	expect(screen.queryByText(t('domainBilling.pendingTopupTitle'))).toBeNull();
	seedPending();
	window.dispatchEvent(new StorageEvent('storage', { key: slot }));
	await within(card('Research lab')).findByText(t('domainBilling.pendingTopupTitle'));
	expect((within(card('Research lab')).getByRole('button', { name: t('domainBilling.topup') }) as HTMLButtonElement).disabled).toBe(true);
	localStorage.removeItem(slot);
	window.dispatchEvent(new Event('focus'));
	await waitFor(() => expect(screen.queryByText(t('domainBilling.pendingTopupTitle'))).toBeNull());
});

it('without Web Locks, read-back compare-and-set never overwrites another uncertain key', async () => {
	mocks.confirm.mockResolvedValue(true);
	mocks.post.mockRejectedValueOnce(new ApiError(503, 'lost reply'));
	const first = render(AdminDomainPoolsPage);
	const second = render(AdminDomainPoolsPage);
	await within(first.container).findByText('Research lab');
	await within(second.container).findByText('Research lab');
	await sendFrom(first, '7');
	await within(researchIn(first)).findByText(t('domainBilling.pendingTopupTitle'));
	const originalKey = mocks.post.mock.calls[0][4].idempotencyKey;

	await sendFrom(second, '9');
	await within(researchIn(second)).findByText(t('domainBilling.pendingElsewhere'));
	expect(within(researchIn(second)).getByText(/\b7\b/)).toBeTruthy();
	expect(mocks.post).toHaveBeenCalledTimes(1);
	expect(JSON.parse(localStorage.getItem(slot) ?? 'null')).toMatchObject({ key: originalKey, amount_credits: '7' });
});

it('keeps no record for a first send aborted before dispatch', async () => {
	mocks.confirm.mockResolvedValue(true);
	mocks.dispatch.mockImplementationOnce(() => { throw new DOMException('Billing authority changed', 'AbortError'); });
	render(AdminDomainPoolsPage);
	await screen.findByText('Research lab');
	await fireEvent.click(within(card('Research lab')).getByRole('button', { name: t('domainBilling.topup') }));
	const dialog = await screen.findByRole('dialog', { name: t('domainBilling.topup') });
	await fireEvent.input(within(dialog).getByLabelText(t('domainBilling.amount')), { target: { value: '7' } });
	await fireEvent.click(within(dialog).getByRole('button', { name: t('domainBilling.reviewTopup') }));
	await within(dialog).findByText(t('domainBilling.saveFailed'));
	expect(mocks.post).not.toHaveBeenCalled();
	expect(screen.queryByText(t('domainBilling.pendingTopupTitle'))).toBeNull();
	expect(pendingKeys()).toEqual([]);
});

it('never requests admin inventory for a non-admin', () => {
	login(false);
	render(AdminDomainPoolsPage);
	render(AdminServiceKeysPage);
	expect(screen.getAllByText(t('domainBilling.adminDenied'))).toHaveLength(2);
	expect(mocks.get).not.toHaveBeenCalled();
});

it('confirms exact intent, persists a lost reply, and retries after remount with the original key', async () => {
	mocks.confirm.mockResolvedValueOnce(false).mockResolvedValue(true);
	mocks.post.mockRejectedValueOnce(new ApiError(503, 'unknown from native service'))
		.mockResolvedValueOnce({ ...pool, domain_id: 'domain-b', balance_credits: '40.125' });
	const first = render(AdminDomainPoolsPage);
	await screen.findByText('New lab');
	await fireEvent.click(within(card('New lab')).getByRole('button', { name: t('domainBilling.topup') }));
	const dialog = await screen.findByRole('dialog', { name: t('domainBilling.topup') });
	const amount = within(dialog).getByLabelText(t('domainBilling.amount'));
	await fireEvent.input(amount, { target: { value: '0' } });
	await fireEvent.click(within(dialog).getByRole('button', { name: t('domainBilling.reviewTopup') }));
	await within(dialog).findByText(t('domainBilling.invalidAmount'));
	expect(mocks.confirm).not.toHaveBeenCalled();
	await fireEvent.input(amount, { target: { value: '40.125' } });
	await fireEvent.input(within(dialog).getByLabelText(t('domainBilling.note')), { target: { value: 'Lab allocation' } });
	const review = within(dialog).getByRole('button', { name: t('domainBilling.reviewTopup') });
	await fireEvent.click(review);
	expect(mocks.confirm).toHaveBeenCalledWith(
		t('domainBilling.confirmTopup', { amount: '40.125', domain: 'domain-b', note: 'Lab allocation' }),
		{ confirmLabel: t('domainBilling.topup'), confirmVariant: 'accent' },
	);
	expect(mocks.post).not.toHaveBeenCalled();
	await fireEvent.click(review);
	await within(card('New lab')).findByText(t('domainBilling.pendingTopupTitle'));
	const [path, body, token, project, request] = mocks.post.mock.calls[0];
	expect([path, body, token, project]).toEqual([
		`${base}/domain-pools/domain-b/topups`, { amount_credits: '40.125', note: 'Lab allocation' }, 'session-token', 'project-1',
	]);
	expect(request).toMatchObject({ idempotencyKey: expect.stringMatching(/^[\w-]{36}$/), replayOnUnauthorized: false });
	expect(pendingKeys()).toHaveLength(1);

	// Reload: a fresh component must recover the recorded operation, not mint a new key.
	first.unmount();
	render(AdminDomainPoolsPage);
	const recovered = await screen.findByText(t('domainBilling.pendingTopupTitle'));
	const row = recovered.closest('.card') as HTMLElement;
	expect(within(row).getByRole('heading', { name: 'New lab' })).toBeTruthy();
	expect(within(row).getByText(/40\.125/)).toBeTruthy();
	expect((within(row).getByRole('button', { name: t('domainBilling.topup') }) as HTMLButtonElement).disabled).toBe(true);
	expect(mocks.post).toHaveBeenCalledTimes(1);
	await fireEvent.click(within(row).getByRole('button', { name: t('domainBilling.resumeTopup') }));
	await waitFor(() => expect(within(card('New lab')).queryByText(t('domainBilling.pendingTopupTitle'))).toBeNull());
	expect(mocks.post).toHaveBeenCalledTimes(2);
	// The remounted component owns a new dispatch guard; the operation identity must not change.
	expect(mocks.post.mock.calls[1].slice(0, 4)).toEqual(mocks.post.mock.calls[0].slice(0, 4));
	expect(mocks.post.mock.calls[1][4]).toMatchObject({ idempotencyKey: request.idempotencyKey, replayOnUnauthorized: false });
	expect(pendingKeys()).toEqual([]);
});

it('shows a pending top-up only to the same admin on the same domain', async () => {
	mocks.post.mockRejectedValueOnce(new ApiError(504, 'gateway timeout'));
	mocks.confirm.mockResolvedValue(true);
	const first = render(AdminDomainPoolsPage);
	await screen.findByText('Research lab');
	await fireEvent.click(within(card('Research lab')).getByRole('button', { name: t('domainBilling.topup') }));
	const dialog = await screen.findByRole('dialog', { name: t('domainBilling.topup') });
	await fireEvent.input(within(dialog).getByLabelText(t('domainBilling.amount')), { target: { value: '7' } });
	await fireEvent.click(within(dialog).getByRole('button', { name: t('domainBilling.reviewTopup') }));
	await within(card('Research lab')).findByText(t('domainBilling.pendingTopupTitle'));
	expect(within(card('New lab')).queryByText(t('domainBilling.pendingTopupTitle'))).toBeNull();
	expect((within(card('New lab')).getByRole('button', { name: t('domainBilling.topup') }) as HTMLButtonElement).disabled).toBe(false);
	first.unmount();

	login(true, 'other-admin');
	render(AdminDomainPoolsPage);
	await screen.findByText('Research lab');
	expect(screen.queryByText(t('domainBilling.pendingTopupTitle'))).toBeNull();
	expect((within(card('Research lab')).getByRole('button', { name: t('domainBilling.topup') }) as HTMLButtonElement).disabled).toBe(false);
	expect(pendingKeys()).toHaveLength(1);
	expect(mocks.post).toHaveBeenCalledTimes(1);
});

it('keeps retry-only recovery after found:false and clears a late commit without a new key', async () => {
	seedPending();
	render(AdminDomainPoolsPage);
	const row = (await screen.findByText(t('domainBilling.pendingTopupTitle'))).closest('.card') as HTMLElement;
	await fireEvent.click(within(row).getByRole('button', { name: t('domainBilling.recheck') }));
	await within(card('Research lab')).findByText(t('domainBilling.recheckNotFound'));
	expect(mocks.get).toHaveBeenCalledWith(lookupPath, 'session-token', 'project-1', { cache: 'no-store', suppressAuthRedirect: true });
	const current = card('Research lab');
	expect((within(current).getByRole('button', { name: t('domainBilling.discardPending') }) as HTMLButtonElement).disabled).toBe(true);
	expect((within(current).getByRole('button', { name: t('domainBilling.resumeTopup') }) as HTMLButtonElement).disabled).toBe(false);
	expect((within(current).getByRole('button', { name: t('domainBilling.topup') }) as HTMLButtonElement).disabled).toBe(true);
	expect(pendingKeys()).toHaveLength(1);

	// The delayed original POST commits after the first lookup.
	lookup = { found: true, entry: { kind: 'topup', amount_credits: '3.00000000', balance_after: '5.00000000', note: null, created_at: '2026-11-18T00:00:09+00:00', actor_user_id: null } };
	await fireEvent.click(within(current).getByRole('button', { name: t('domainBilling.recheck') }));
	await waitFor(() => expect(screen.queryByText(t('domainBilling.pendingTopupTitle'))).toBeNull());
	expect(mocks.get.mock.calls.filter(([path]) => path === lookupPath)).toHaveLength(2);
	expect(mocks.post).not.toHaveBeenCalled();
	expect(pendingKeys()).toEqual([]);
});

it('unlocks discard only after a definite same-key rejection, a later lookup, and typed risk acceptance', async () => {
	seedPending();
	mocks.confirm.mockResolvedValue(true);
	mocks.post.mockRejectedValueOnce(new ApiError(422, 'invalid amount'));
	render(AdminDomainPoolsPage);
	const row = (await screen.findByText(t('domainBilling.pendingTopupTitle'))).closest('.card') as HTMLElement;
	await fireEvent.click(within(row).getByRole('button', { name: t('domainBilling.resumeTopup') }));
	await waitFor(() => expect(mocks.post).toHaveBeenCalledTimes(1));
	const discard = () => within(card('Research lab')).getByRole('button', { name: t('domainBilling.discardPending') }) as HTMLButtonElement;
	await waitFor(() => expect((within(card('Research lab')).getByRole('button', { name: t('domainBilling.resumeTopup') }) as HTMLButtonElement).disabled).toBe(false));
	expect(discard().disabled).toBe(true);
	expect(pendingKeys()).toHaveLength(1);
	await fireEvent.click(within(card('Research lab')).getByRole('button', { name: t('domainBilling.recheck') }));
	await within(card('Research lab')).findByText(t('domainBilling.recheckNotFound'));
	expect(discard().disabled).toBe(false);
	await fireEvent.click(discard());
	await waitFor(() => expect(screen.queryByText(t('domainBilling.pendingTopupTitle'))).toBeNull());
	expect(mocks.confirm).toHaveBeenLastCalledWith(t('domainBilling.discardConfirm'), {
		confirmLabel: t('domainBilling.discardPending'), requiredText: t('domainBilling.discardPhrase'),
	});
	expect(mocks.post).toHaveBeenCalledTimes(1);
	expect(pendingKeys()).toEqual([]);
});

it('clears a pending top-up as confirmed when Lumen finds its ledger entry', async () => {
	seedPending();
	lookup = { found: true, entry: {
		kind: 'topup', amount_credits: '3.00000000', balance_after: '5.00000000', note: null, created_at: '2026-11-18T00:00:01+00:00', actor_user_id: 'admin-fixture',
	} };
	render(AdminDomainPoolsPage);
	const row = (await screen.findByText(t('domainBilling.pendingTopupTitle'))).closest('.card') as HTMLElement;
	await fireEvent.click(within(row).getByRole('button', { name: t('domainBilling.recheck') }));
	await waitFor(() => expect(screen.queryByText(t('domainBilling.pendingTopupTitle'))).toBeNull());
	expect(mocks.success).toHaveBeenCalledWith(expect.stringMatching(/^Lumen confirmed the 3-credit top-up\. Balance after: 5 · /));
	expect(mocks.post).not.toHaveBeenCalled();
	expect(mocks.confirm).not.toHaveBeenCalled();
	expect(pendingKeys()).toEqual([]);
});

it('keeps discard disabled when the ledger lookup fails', async () => {
	seedPending();
	lookup = { unexpected: true };
	render(AdminDomainPoolsPage);
	const row = (await screen.findByText(t('domainBilling.pendingTopupTitle'))).closest('.card') as HTMLElement;
	await fireEvent.click(within(row).getByRole('button', { name: t('domainBilling.recheck') }));
	await within(card('Research lab')).findByText(t('domainBilling.recheckFailed'));
	expect((within(card('Research lab')).getByRole('button', { name: t('domainBilling.discardPending') }) as HTMLButtonElement).disabled).toBe(true);
	expect(pendingKeys()).toHaveLength(1);
});

it.each([
	['throws', () => { throw new DOMException('Storage blocked', 'SecurityError'); }],
	['silently drops the write', () => undefined],
])('sends no top-up when browser storage %s', async (_case, setItem) => {
	const storage = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(setItem);
	try {
		mocks.confirm.mockResolvedValue(true);
		render(AdminDomainPoolsPage);
		await screen.findByText('Research lab');
		await fireEvent.click(within(card('Research lab')).getByRole('button', { name: t('domainBilling.topup') }));
		const dialog = await screen.findByRole('dialog', { name: t('domainBilling.topup') });
		await fireEvent.input(within(dialog).getByLabelText(t('domainBilling.amount')), { target: { value: '7' } });
		await fireEvent.click(within(dialog).getByRole('button', { name: t('domainBilling.reviewTopup') }));
		await within(dialog).findByText(t('domainBilling.recoveryUnavailable'));
		expect(mocks.post).not.toHaveBeenCalled();
		expect(screen.queryByText(t('domainBilling.pendingTopupTitle'))).toBeNull();
	} finally {
		storage.mockRestore();
	}
});

it('keeps an uncertain record when a resend is refused before reaching Lumen', async () => {
	seedPending();
	mocks.confirm.mockResolvedValue(true);
	mocks.post.mockRejectedValueOnce(new ApiError(401, 'token rotated'));
	render(AdminDomainPoolsPage);
	const row = (await screen.findByText(t('domainBilling.pendingTopupTitle'))).closest('.card') as HTMLElement;
	await fireEvent.click(within(row).getByRole('button', { name: t('domainBilling.resumeTopup') }));
	const resume = within(row).getByRole('button', { name: t('domainBilling.resumeTopup') }) as HTMLButtonElement;
	await waitFor(() => expect(mocks.post).toHaveBeenCalledTimes(1));
	await waitFor(() => expect(resume.disabled).toBe(false));
	expect(mocks.post.mock.calls[0][4]).toMatchObject({ idempotencyKey: 'recorded-key' });
	expect((within(card('Research lab')).getByRole('button', { name: t('domainBilling.discardPending') }) as HTMLButtonElement).disabled).toBe(true);
	expect(within(card('Research lab')).getByText(t('domainBilling.pendingTopupTitle'))).toBeTruthy();
	expect((within(card('Research lab')).getByRole('button', { name: t('domainBilling.topup') }) as HTMLButtonElement).disabled).toBe(true);
	expect(pendingKeys()).toHaveLength(1);
});

it('edits admin ceiling and active state on the exact domain', async () => {
	mocks.patch.mockResolvedValue({ ...pool, admin_ceiling_credits: '12', is_active: false });
	render(AdminDomainPoolsPage);
	await screen.findByText('Research lab');
	await fireEvent.click(screen.getAllByRole('button', { name: t('domainBilling.editPool') })[0]);
	const dialog = await screen.findByRole('dialog', { name: t('domainBilling.editPool') });
	await fireEvent.input(within(dialog).getByLabelText(t('domainBilling.adminCeiling')), { target: { value: '12' } });
	await fireEvent.click(within(dialog).getByRole('checkbox', { name: t('domainBilling.active') }));
	await fireEvent.click(within(dialog).getByRole('button', { name: t('apiKeys.save') }));
	await screen.findByText(t('domainBilling.inactiveLabel'));
	expect(mocks.patch).toHaveBeenCalledWith(`${base}/domain-pools/domain-a`, { admin_ceiling_credits: '12', is_active: false }, 'session-token', 'project-1', expect.anything());
});

it('shows metadata-only inventory and uses the native next cursor', async () => {
	mocks.get.mockResolvedValueOnce({ items: [{ id: 8, key_kind: 'service', owner_domain_id: 'domain-a', created_by_user_id: 'creator', key_prefix: 'prefix-fixture', name: 'Background job', is_active: true, key: 'not-listable' }], next_before_id: 8 });
	mocks.get.mockResolvedValueOnce({ items: [], next_before_id: null });
	render(AdminServiceKeysPage);
	await screen.findByText('Background job');
	expect(screen.getByText('prefix-fixture…')).toBeTruthy();
	expect(screen.queryByText('not-listable')).toBeNull();
	await fireEvent.click(screen.getByRole('button', { name: t('domainBilling.loadMore') }));
	await waitFor(() => expect(mocks.get).toHaveBeenLastCalledWith(`${base}/service-keys?limit=50&before_id=8`, 'session-token', 'project-1', expect.anything()));
});
