import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { get } from 'svelte/store';
import { auth, authReady, projectSwitching, logoutInProgress } from '$lib/stores/auth';
import type { FlavorAutomationStatus } from '$lib/api/flavorAutomation';
import { t } from '$lib/i18n/ns/compute-pools';
const mocks = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), post: vi.fn() }));
vi.mock('$lib/api/client', () => ({ api: mocks, ApiError: class ApiError extends Error { status = 409; } }));
vi.mock('../FlavorAutomationPolicyPanel.svelte', () => ({ default: () => ({}) }));
import FlavorAutomationPanel from '../FlavorAutomationPanel.svelte';
const original = get(auth);
const status = (): FlavorAutomationStatus => ({ enabled: false, revision: 3, last_run: null, status: 'disabled', error: null, readiness: { verified: true, reason: '' }, items: [], diagnostics: [{ code: 'standard_api_unavailable', message: 'Standard API permissions missing' }] });
beforeEach(() => { vi.resetAllMocks(); auth.set({ ...original, token: 'token', sessionId: 'session-a', userId: 'admin', projectId: 'admin-project', isSystemAdmin: true }); authReady.set(true); projectSwitching.set(false); logoutInProgress.set(false); mocks.get.mockResolvedValue(status()); });
afterEach(() => { cleanup(); auth.set(original); });
describe('flavor automation console', () => {
	it('reports native CPU labels separately and never describes unknown hardware as zero GPUs', async () => {
		mocks.get.mockResolvedValue({ ...status(), items: [
			{ id: 'native-cpu', name: 'm1.small', display_name: 'cpu.2c_4g', origin: 'adopted_cpu', control_state: 'controlled', enforcement: 'native_private_acl', vcpus: 2, ram: 4096, disk: 20, gpu_resource_class: null, gpu_count: 0, status: 'unchanged', projects: 2 },
			{ id: 'native-unknown', name: 'manual.unknown', display_name: null, origin: 'native', control_state: 'unqualified', vcpus: 2, ram: 4096, disk: 20, gpu_resource_class: null, gpu_count: null, status: 'retained', projects: 0, reason: 'Hardware snapshot is unavailable' },
		] } satisfies FlavorAutomationStatus);
		render(FlavorAutomationPanel);
		await screen.findByText('cpu.2c_4g');
		expect(screen.getByText('m1.small')).toBeTruthy();
		expect(screen.getByText('native-cpu')).toBeTruthy();
		const unknown = screen.getByText('manual.unknown').closest('li')!;
		expect(unknown.textContent).toContain(`GPU ${t('unknown')}`);
		expect(unknown.textContent).not.toContain('GPU 0');
		expect(unknown.textContent).toContain('Hardware snapshot is unavailable');
	});
	it('does not reconcile on observation and enables only through explicit revisioned save', async () => {
		mocks.put.mockResolvedValue({ ...status(), enabled: true, revision: 4, status: 'idle' });
		render(FlavorAutomationPanel); await screen.findByText(t('never'));
		expect(mocks.put).not.toHaveBeenCalled(); expect(mocks.post).not.toHaveBeenCalled();
		await fireEvent.click(screen.getByRole('checkbox', { name: t('enableAutomation') }));
		await fireEvent.click(screen.getByRole('button', { name: t('saveAutomation') }));
		await waitFor(() => expect(mocks.put).toHaveBeenCalledWith('/api/v1/admin/flavor-automation', { revision: 3, enabled: true }, 'token', 'admin-project', expect.objectContaining({ replayOnUnauthorized: false })));
	});
	it('reports actual reconciliation diagnostics instead of claiming all shapes were published', async () => {
		mocks.get.mockResolvedValue({ ...status(), enabled: true, status: 'idle' });
		mocks.post.mockResolvedValue({ ...status(), enabled: true, status: 'unavailable', error: 'standard API unavailable', last_run: '2026-10-28T00:00:00Z' });
		render(FlavorAutomationPanel); await screen.findByText(t('never'));
		await fireEvent.click(screen.getByRole('button', { name: t('reconcile') }));
		await screen.findByText('standard API unavailable'); expect(screen.getByText(t('automationStatus.unavailable'))).toBeTruthy();
		expect(mocks.post).toHaveBeenCalledTimes(1);
		expect(screen.queryByText(t('reconciled'))).toBeNull();
	});
	it('shows disabled never-run readiness even with no items and blocks activation', async () => {
		mocks.get.mockResolvedValue({ ...status(), diagnostics: [], readiness: { verified: false, reason: 'Standard API permissions missing' } });
		render(FlavorAutomationPanel);
		await screen.findByText(t('never'));
		expect(screen.getByText(t('automationReadinessBlocked'))).toBeTruthy();
		expect(screen.getByText('Standard API permissions missing')).toBeTruthy();
		expect(screen.getByRole('checkbox').hasAttribute('disabled')).toBe(true);
		expect(screen.getByRole('button', { name: t('reconcile') }).hasAttribute('disabled')).toBe(true);
		await fireEvent.click(screen.getByRole('button', { name: t('saveAutomation') }));
		expect(mocks.put).not.toHaveBeenCalled(); expect(mocks.post).not.toHaveBeenCalled();
	});
	it('permits disabling existing automation while standard API readiness is unavailable', async () => {
		const unavailable = { ...status(), enabled: true, status: 'idle' as const, readiness: { verified: false, reason: 'Standard API permissions missing' } };
		mocks.get.mockResolvedValue(unavailable); mocks.put.mockResolvedValue({ ...unavailable, enabled: false, status: 'disabled', revision: 4 });
		render(FlavorAutomationPanel); await screen.findByText(t('never'));
		expect(screen.getByRole('checkbox').hasAttribute('disabled')).toBe(false);
		await fireEvent.click(screen.getByRole('checkbox'));
		await fireEvent.click(screen.getByRole('button', { name: t('saveAutomation') }));
		await waitFor(() => expect(mocks.put).toHaveBeenCalledWith('/api/v1/admin/flavor-automation', { revision: 3, enabled: false }, 'token', 'admin-project', expect.objectContaining({ replayOnUnauthorized: false })));
		expect(mocks.post).not.toHaveBeenCalled();
	});
	it('discards late results after same-tick session A→B→A and unmount', async () => {
		const pending = Promise.withResolvers<FlavorAutomationStatus>(); mocks.post.mockReturnValue(pending.promise); mocks.get.mockResolvedValue({ ...status(), enabled: true, status: 'idle' });
		const onChanged = vi.fn(); const view = render(FlavorAutomationPanel, { onChanged }); await screen.findByText(t('never'));
		await fireEvent.click(screen.getByRole('button', { name: t('reconcile') })); const prior = get(auth); auth.set({ ...prior, sessionId: 'other' }); auth.set(prior); view.unmount();
		pending.resolve({ ...status(), status: 'complete' }); await Promise.resolve(); expect(onChanged).not.toHaveBeenCalled();
	});
});
