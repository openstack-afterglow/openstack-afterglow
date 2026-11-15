import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { get } from 'svelte/store';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { auth, authReady, logoutInProgress, projectSwitching } from '$lib/stores/auth';
import { initLocale } from '$lib/i18n/runtime.svelte';
import en from '$lib/i18n/messages/en/admin-email.json';
import system from '$lib/i18n/messages/en/admin-system.json';
import type { AnnouncementAdmin } from '$lib/types/announcements';
import type * as Reactivity from 'svelte/reactivity';
const viewport = vi.hoisted(() => ({ desktop: true }));
vi.mock('svelte/reactivity', async original => ({
	...await original<typeof Reactivity>(),
	MediaQuery: class { get current() { return viewport.desktop; } },
}));
const mocks = vi.hoisted(() => ({ create: vi.fn(), load: vi.fn(), loadOptions: vi.fn(), loadDomains: vi.fn(), invalidateOwner: vi.fn(), dispose: vi.fn(), selectDomain: vi.fn(), toggleActive: vi.fn(), announcements: [] as AnnouncementAdmin[] }));
vi.mock('$lib/stores/adminAnnouncementsController.svelte', () => ({
	createAdminAnnouncementsController: () => ({
		...mocks, createError: '', error: '', loading: false, refreshing: false, creating: false, deleting: false,
		togglingId: null, domainId: '', allProjects: [], allUsers: [], announcements: mocks.announcements, options: null,
		domains: [], domainsLoading: false, domainsError: '', projectsLoading: false, projectsError: '', usersLoading: false, usersError: '', emailOperation: null,
	}),
}));
vi.mock('$lib/stores/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
import AnnouncementsPage from '../../../../routes/admin/announcements/+page.svelte';
const operationId = 'd06803e9-63c6-4a4f-a1ad-af62f2b08250';
beforeEach(() => {
	vi.resetAllMocks(); initLocale('en'); viewport.desktop = true; mocks.announcements = [];
	auth.set({ ...get(auth), sessionId: 'logical-login', token: 'admin-token', userId: 'admin', identityDomainId: 'home', domainId: 'home', projectId: 'project', roles: ['admin'], isSystemAdmin: true });
	authReady.set(true); logoutInProgress.set(false); projectSwitching.set(false); mocks.create.mockResolvedValue({ status: 'ok' });
	vi.spyOn(crypto, 'randomUUID').mockReturnValue(operationId);
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); initLocale('ko'); });
describe('announcement create email controls', () => {
	it.each([false, true])('only attaches a durable email operation when explicitly selected: %s', async selected => {
		render(AnnouncementsPage);
		await fireEvent.input(document.getElementById('announcement-title')!, { target: { value: 'Maintenance' } });
		await fireEvent.input(document.getElementById('announcement-body')!, { target: { value: 'Announcement body' } });
		expect(screen.getByText(en.schedule)).toBeTruthy();
		const checkbox = screen.getByRole('checkbox', { name: en.sendWithAnnouncement }) as HTMLInputElement;
		expect(checkbox.checked).toBe(false);
		if (selected) await fireEvent.click(checkbox);
		expect(mocks.create).not.toHaveBeenCalled();
		await fireEvent.click(screen.getByRole('button', { name: system['announcements.actions.send'] }));
		expect(mocks.create).toHaveBeenCalledWith(expect.objectContaining({ title: 'Maintenance', body: 'Announcement body', target_type: 'all', target_id: null, send_email: selected }));
		if (selected) expect(mocks.create.mock.calls[0][0].email_operation_id).toBe(operationId);
		else expect(mocks.create.mock.calls[0][0]).not.toHaveProperty('email_operation_id');
	});
	it('leaves email-enabled creation editable when a project target is missing, without posting or claiming unknown', async () => {
		render(AnnouncementsPage);
		await fireEvent.input(document.getElementById('announcement-title')!, { target: { value: 'Maintenance' } });
		await fireEvent.input(document.getElementById('announcement-body')!, { target: { value: 'Announcement body' } });
		await fireEvent.change(document.getElementById('announcement-target-type')!, { target: { value: 'project' } });
		await fireEvent.click(screen.getByRole('checkbox', { name: en.sendWithAnnouncement }));
		const submit = screen.getByRole('button', { name: system['announcements.actions.send'] }) as HTMLButtonElement;
		await fireEvent.click(submit);
		expect(mocks.create).not.toHaveBeenCalled(); expect(screen.queryByText(en.unknown)).toBeNull();
		expect(submit.disabled).toBe(false); expect((document.getElementById('announcement-title') as HTMLInputElement).disabled).toBe(false);
	});
	it.each([true, false])('keeps history embedded and state labels readable (desktop=%s)', async desktop => {
		viewport.desktop = desktop;
		const announcement: AnnouncementAdmin = {
			id: 1, created_at: '2026-11-16T00:00:00Z', updated_at: '2026-11-16T00:00:00Z',
			created_by_user_id: 'admin', created_by_username: 'Administrator', title: 'Maintenance',
			body: 'Announcement body', severity: 'warning', target_type: 'all', target_id: null,
			starts_at: null, ends_at: null, is_active: true,
		};
		mocks.announcements = [announcement];
		const { container } = render(AnnouncementsPage);
		const history = container.querySelector('[data-tour="admin-announcements-history"]')!;
		expect(history.querySelector('.responsive-table-embedded')).not.toBeNull();
		expect(history.querySelector('.pill-warning')?.textContent?.trim()).toBe(system['announcements.severity.warning']);
		const active = screen.getByRole('button', { name: system['announcements.status.active'] });
		expect(active.getAttribute('style')).toContain('color: var(--color-state-success-text)');
		await fireEvent.click(active);
		expect(mocks.toggleActive).toHaveBeenCalledExactlyOnceWith(announcement);
	});
});
