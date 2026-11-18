import { setVerifiedLumenActor } from '../../chat/__tests__/lumenPermissionFixture';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { t } from '$lib/i18n/ns/chat-settings';
import { initLocale } from '$lib/i18n/runtime.svelte';
import { ApiError } from '$lib/api/client';
import AdminDomainPoolsPage from '../../../../routes/admin/chat/domain-pools/+page.svelte';
import AdminServiceKeysPage from '../../../../routes/admin/chat/service-keys/+page.svelte';

const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn(), confirm: vi.fn() }));
vi.mock('$lib/api/client', () => ({
	api: mocks,
	ApiError: class extends Error { constructor(public status: number, message: string) { super(message); } }
}));
vi.mock('$lib/stores/confirm.svelte', () => ({ confirmDialog: mocks.confirm }));

const base = '/api/v1/chat/admin';
const pool = {
	domain_id: 'domain-a', balance_credits: '2', reserved_credits: '1', monthly_used_credits: '5',
	manager_monthly_limit_credits: '9', admin_ceiling_credits: '10', is_active: true,
};
const domain = { id: 'domain-a', name: 'Research lab', enabled: true };
const unfundedDomain = { id: 'domain-b', name: 'New lab', enabled: true };

function login(isSystemAdmin: boolean) {
	setVerifiedLumenActor({
		token: 'session-token', refreshToken: null, accessExpiresAt: null,
		userId: 'admin-fixture', username: 'admin', projectId: 'project-1', projectName: 'Project',
		availableProjects: [], roles: [], isSystemAdmin, federated: false,
		domainId: 'default', domainName: 'Default', isDomainManager: false,
	});
}

beforeEach(() => {
	vi.resetAllMocks();
	initLocale('en');
	login(true);
	mocks.get.mockImplementation(async (path: string) => {
		if (path === '/api/v1/admin/domains') return { items: [domain, unfundedDomain] };
		if (path === `${base}/domain-pools`) return { items: [pool] };
		throw new Error(`Unexpected GET ${path}`);
	});
});
afterEach(cleanup);

it('never requests admin inventory for a non-admin', () => {
	login(false);
	render(AdminDomainPoolsPage);
	render(AdminServiceKeysPage);
	expect(screen.getAllByText(t('domainBilling.adminDenied'))).toHaveLength(2);
	expect(mocks.get).not.toHaveBeenCalled();
});

it('confirms exact top-up intent, funds an unconfigured domain, and reuses the key on an uncertain retry', async () => {
	mocks.confirm.mockResolvedValueOnce(false).mockResolvedValue(true);
	mocks.post.mockRejectedValueOnce(new ApiError(503, 'unknown from native service'))
		.mockResolvedValueOnce({ ...pool, domain_id: 'domain-b', balance_credits: '40.125' });
	render(AdminDomainPoolsPage);
	await screen.findByText('New lab');
	const cards = screen.getAllByRole('button', { name: t('domainBilling.topup') });
	await fireEvent.click(cards[1]);
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
	await within(dialog).findByText(t('domainBilling.topupUnconfirmed'));
	expect(amount.hasAttribute('disabled')).toBe(true);
	const [path, body, token, project, request] = mocks.post.mock.calls[0];
	expect([path, body, token, project]).toEqual([
		`${base}/domain-pools/domain-b/topups`, { amount_credits: '40.125', note: 'Lab allocation' }, 'session-token', 'project-1',
	]);
	expect(request).toMatchObject({ idempotencyKey: expect.stringMatching(/^[\w-]{36}$/), replayOnUnauthorized: false });
	await fireEvent.click(within(dialog).getByRole('button', { name: t('domainBilling.resumeTopup') }));
	await screen.findByText('40.125');
	expect(mocks.post).toHaveBeenCalledTimes(2);
	expect(mocks.post.mock.calls[1]).toEqual(mocks.post.mock.calls[0]);
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
