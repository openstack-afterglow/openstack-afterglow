import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock('$lib/api/client', () => ({ api: mocks }));
import { initLocale } from '$lib/i18n/runtime.svelte';
import { t } from '$lib/i18n/ns/admin-system';
import PersonalQuotaConvergence from '../PersonalQuotaConvergence.svelte';
const path = '/api/v1/admin/personal-project-quotas';
const preview = { project_id: 'personal-project', owner_user_id: 'owner', policy_revision: 2, preview_id: 'a'.repeat(64),
	limits: { cores: 2, ram: 4096, gigabytes: 1024 }, current: { cores: { limit: 0, in_use: 0, reserved: 0 }, ram: { limit: 0, in_use: 0, reserved: 0 }, gigabytes: { limit: 0, in_use: 0, reserved: 0 } }, can_apply: true, blocked_fields: [] };
const page = { items: [{ id: 'personal-project', name: 'Own workspace', user_id: 'owner', enabled: true }], next_cursor: 'personal-project' };
const props = { token: 'admin', projectId: 'observation', current: () => true };
beforeEach(() => {
	vi.resetAllMocks(); initLocale('en');
	mocks.get.mockImplementation((url: string) => Promise.resolve(url.endsWith('/preview') ? preview : page));
	mocks.post.mockResolvedValue({ status: 'updated', operation_id: 'operation-id', errors: {} });
});
afterEach(() => { cleanup(); initLocale('ko'); });
async function inspect() {
	await fireEvent.click(screen.getByRole('button', { name: t('enrollment.convergeLoad') }));
	await fireEvent.change(await screen.findByRole('combobox'), { target: { value: 'personal-project' } });
	await fireEvent.click(screen.getByRole('button', { name: t('enrollment.convergePreview') }));
	await screen.findByRole('checkbox');
}
describe('explicit existing personal quota application', () => {
	it('does not read or mutate until explicit request; preview requires a separate confirmation and one apply', async () => {
		render(PersonalQuotaConvergence, props); expect(mocks.get).not.toHaveBeenCalled(); await inspect();
		expect(mocks.post).not.toHaveBeenCalled();
		const apply = screen.getByRole('button', { name: t('enrollment.convergeApply') }) as HTMLButtonElement;
		expect(apply.disabled).toBe(true);
		await fireEvent.click(screen.getByRole('checkbox')); await fireEvent.click(apply); await fireEvent.click(apply);
		expect(mocks.post).toHaveBeenCalledExactlyOnceWith(`${path}/personal-project/apply`, { preview_id: preview.preview_id }, 'admin', 'observation', { cache: 'no-store', replayOnUnauthorized: false });
		await screen.findByText(/operation-id/); expect(screen.queryByRole('checkbox')).toBeNull();
	});
	it('blocks over-use and preserves measured usage visibly', async () => {
		mocks.get.mockImplementation((url: string) => Promise.resolve(url.endsWith('/preview') ? { ...preview, can_apply: false, blocked_fields: ['cores'], current: { ...preview.current, cores: { limit: 8, in_use: 4, reserved: 1 } } } : page));
		render(PersonalQuotaConvergence, props); await inspect();
		expect((screen.getByRole('checkbox') as HTMLInputElement).disabled).toBe(true);
		expect(screen.getByText(/8 → 2/).textContent).toContain('4 + 1'); expect(mocks.post).not.toHaveBeenCalled();
	});
	it('paginates the full directory and clears a selected preview before loading another page', async () => {
		render(PersonalQuotaConvergence, props); await inspect();
		await fireEvent.click(screen.getByRole('button', { name: t('enrollment.next') }));
		await waitFor(() => expect(mocks.get).toHaveBeenLastCalledWith(`${path}?cursor=personal-project`, 'admin', 'observation', expect.objectContaining({ refresh: true, replayOnUnauthorized: false })));
		expect(screen.queryByRole('checkbox')).toBeNull(); expect(mocks.post).not.toHaveBeenCalled();
	});
	it('does not replay an uncertain application and requires a new preview', async () => {
		mocks.post.mockRejectedValue(new Error('private'));
		render(PersonalQuotaConvergence, props); await inspect();
		await fireEvent.click(screen.getByRole('checkbox')); await fireEvent.click(screen.getByRole('button', { name: t('enrollment.convergeApply') }));
		await screen.findByRole('alert'); expect(mocks.post).toHaveBeenCalledTimes(1);
		expect(screen.queryByRole('checkbox')).toBeNull(); expect(document.body.textContent).not.toContain('private');
	});
	it('rejects a late preview after synchronous owner/authority invalidation', async () => {
		let current = true; const result = Promise.withResolvers<typeof preview>();
		mocks.get.mockImplementation((url: string) => url.endsWith('/preview') ? result.promise : Promise.resolve(page));
		render(PersonalQuotaConvergence, { ...props, current: () => current });
		await fireEvent.click(screen.getByRole('button', { name: t('enrollment.convergeLoad') }));
		await fireEvent.change(await screen.findByRole('combobox'), { target: { value: 'personal-project' } });
		await fireEvent.click(screen.getByRole('button', { name: t('enrollment.convergePreview') }));
		current = false; result.resolve(preview); await Promise.resolve();
		expect(screen.queryByRole('checkbox')).toBeNull(); expect(mocks.post).not.toHaveBeenCalled();
	});
});
