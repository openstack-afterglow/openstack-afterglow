import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { get } from 'svelte/store';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { auth, authReady, logoutInProgress, projectSwitching, setAuth } from '$lib/stores/auth';
import { t } from '$lib/i18n/ns/admin-identity';
import { ApiError } from '$lib/api/client';
import { refreshAuthState } from '$lib/utils/authSession';

const mocks = vi.hoisted(() => ({ get: vi.fn(), delete: vi.fn(), goto: vi.fn(), page: {
	params: { id: 'project /?' }, url: new URL('http://localhost/admin/projects/project/resources?domain_id=domain%20%2F%3F&kind=volumes'),
} }));
vi.mock('$lib/api/client', () => ({
	api: { get: mocks.get, delete: mocks.delete },
	ApiError: class ApiError extends Error {
		constructor(public status: number, message: string) { super(message); }
	},
}));
vi.mock('$app/state', () => ({ page: mocks.page }));
vi.mock('$app/navigation', () => ({ goto: mocks.goto }));
import ProjectResourceMonitor from '../ProjectResourceMonitor.svelte';
import Route from '../../../../../routes/admin/projects/[id]/resources/+page.svelte';

const initialAuth = get(auth);
const initialReady = get(authReady);
const resource = { id: 'resource /? #exact', name: 'duplicate display name', status: 'available' };
const defaults = { projectId: 'project /?', domainId: 'domain /?', kind: 'volumes', onKindChange: vi.fn() };
function inventory(kind = 'volumes', project = defaults.projectId, rows: Array<{ id: string; name: string | null; status: string | null }> = [resource]) {
	return { project_id: project, kind, status: 'ok', reason: null, resources: rows, count: rows.length };
}
const listPath = '/api/v1/admin/projects/project%20%2F%3F/resources?domain_id=domain+%2F%3F&kind=volumes';
const removePath = '/api/v1/admin/projects/project%20%2F%3F/resources/volumes/resource%20%2F%3F%20%23exact?domain_id=domain+%2F%3F';
const rowButton = () => screen.getByRole('button', { name: t('resourceMonitor.removeLabel', { id: resource.id }) }) as HTMLButtonElement;
const refresh = () => screen.getByRole('button', { name: t('resourceMonitor.refresh') }) as HTMLButtonElement;
async function confirm() {
	await screen.findByText(resource.name);
	await fireEvent.click(rowButton());
	const dialog = screen.getByRole('dialog');
	await fireEvent.input(within(dialog).getByLabelText(t('resourceMonitor.confirmId')), { target: { value: resource.id } });
	await fireEvent.click(within(dialog).getByRole('button', { name: t('resourceMonitor.remove') }));
}
beforeEach(() => {
	vi.resetAllMocks();
	authReady.set(true); logoutInProgress.set(false); projectSwitching.set(false);
	auth.set({ ...initialAuth, token: 'admin-token', userId: 'admin', sessionId: 'login-session', projectId: 'observation-project', domainId: 'working-domain', isSystemAdmin: true });
	authReady.set(true);
	mocks.get.mockResolvedValue(inventory()); mocks.delete.mockResolvedValue(undefined);
});
afterEach(() => { cleanup(); auth.set(initialAuth); authReady.set(initialReady); logoutInProgress.set(false); projectSwitching.set(false); });

describe('ProjectResourceMonitor scoped normal deletion', () => {
	it('starts a fresh direct-entry list when restored authentication becomes ready', async () => {
		authReady.set(false);
		render(ProjectResourceMonitor, defaults);
		await screen.findByText(t('resourceMonitor.invalidScope'));
		expect(mocks.get).not.toHaveBeenCalled();
		authReady.set(true);
		await screen.findByText(resource.name);
		expect(mocks.get).toHaveBeenCalledOnce();
	});
	it('loads the initial URL kind, preserves exact scope on filter navigation and back link, and offers all 29 kinds', async () => {
		render(Route);
		await screen.findByText(resource.name);
		expect(mocks.get).toHaveBeenCalledWith(listPath, 'admin-token', 'observation-project', expect.objectContaining({ refresh: true, cache: 'no-store', signal: expect.any(AbortSignal) }));
		const picker = screen.getByRole('combobox', { name: t('resourceMonitor.kind') }) as HTMLSelectElement;
		expect(picker.value).toBe('volumes'); expect(picker.options).toHaveLength(29);
		expect([...picker.options].every(option => option.text !== option.value)).toBe(true);
		expect(screen.getByRole('link', { name: t('resourceMonitor.back') }).getAttribute('href')).toBe('/admin/projects?domain_id=domain+%2F%3F');
		await fireEvent.change(picker, { target: { value: 'volumes' } });
		expect(screen.getByText(resource.name)).toBeTruthy();
		expect(mocks.goto).not.toHaveBeenCalled();
		await fireEvent.change(picker, { target: { value: 'child_projects' } });
		const [url] = mocks.goto.mock.calls[0];
		expect(url.pathname).toBe(mocks.page.url.pathname); expect(url.searchParams.get('domain_id')).toBe('domain /?');
		expect(url.searchParams.get('kind')).toBe('child_projects'); expect(mocks.delete).not.toHaveBeenCalled();
	});
	it('shows loading rather than empty, with explicit fresh retry after a failed list', async () => {
		const pending = Promise.withResolvers<unknown>(); mocks.get.mockReturnValueOnce(pending.promise);
		render(ProjectResourceMonitor, defaults);
		await screen.findByText(t('resourceMonitor.loading')); expect(screen.queryByText(t('resourceMonitor.empty'))).toBeNull();
		pending.reject(new Error('private upstream payload'));
		await screen.findByText(t('resourceMonitor.loadFailed')); expect(screen.queryByText('private upstream payload')).toBeNull();
		await fireEvent.click(refresh()); await screen.findByText(resource.name); expect(mocks.get).toHaveBeenCalledTimes(2);
	});
	it.each([
		{ ...inventory(), project_id: 'foreign-project' }, { ...inventory(), kind: 'instances' },
		{ ...inventory(), count: 2 }, { ...inventory(), resources: [resource, resource], count: 2 },
		{ ...inventory(), status: 'unavailable', count: null },
	])('rejects contradictory or partial list responses without presenting removal', async response => {
		mocks.get.mockResolvedValue(response); render(ProjectResourceMonitor, defaults);
		await screen.findByText(t('resourceMonitor.loadFailed')); expect(screen.queryByRole('button', { name: t('resourceMonitor.removeLabel', { id: resource.id }) })).toBeNull();
	});
	it('keeps unavailable distinct from empty and hides all secret names and extra payload', async () => {
		mocks.get.mockResolvedValueOnce({ project_id: defaults.projectId, kind: 'volumes', status: 'unavailable', reason: 'resource_ownership_unverified', count: null, resources: [] });
		const view = render(ProjectResourceMonitor, defaults);
		await screen.findByText(t('resourceMonitor.unavailable')); expect(screen.queryByText(t('resourceMonitor.empty'))).toBeNull();
		mocks.get.mockResolvedValue({ ...inventory('secrets'), resources: [{ id: 'secret-id', name: 'private-name', payload: 'private-value' }] });
		await view.rerender({ ...defaults, kind: 'secrets' }); await screen.findByText('secret-id');
		expect(screen.queryByText(/private-name|private-value/)).toBeNull();
	});
	it('opens a real FormModal with full name and ID, requires exact ID, rechecks then sends one deletion and reads back', async () => {
		render(ProjectResourceMonitor, defaults); await screen.findByText(resource.name); await fireEvent.click(rowButton());
		const dialog = screen.getByRole('dialog');
		expect(within(dialog).getByText(resource.name)).toBeTruthy(); expect(within(dialog).getByText(resource.id)).toBeTruthy();
		const remove = within(dialog).getByRole('button', { name: t('resourceMonitor.remove') }) as HTMLButtonElement;
		expect(remove.disabled).toBe(true);
		await fireEvent.input(within(dialog).getByLabelText(t('resourceMonitor.confirmId')), { target: { value: resource.id.slice(0, 8) } }); expect(remove.disabled).toBe(true);
		await fireEvent.input(within(dialog).getByLabelText(t('resourceMonitor.confirmId')), { target: { value: resource.id } });
		await fireEvent.click(remove); await screen.findByText(t('resourceMonitor.pending'));
		expect(mocks.delete).toHaveBeenCalledExactlyOnceWith(removePath, 'admin-token', 'observation-project', { replayOnUnauthorized: false });
		expect(mocks.get).toHaveBeenCalledTimes(3);
		expect(mocks.get.mock.invocationCallOrder[1]).toBeLessThan(mocks.delete.mock.invocationCallOrder[0]);
		expect(mocks.get.mock.invocationCallOrder[2]).toBeGreaterThan(mocks.delete.mock.invocationCallOrder[0]);
		expect(rowButton().disabled).toBe(true); await fireEvent.click(refresh()); await waitFor(() => expect(refresh().disabled).toBe(false));
		expect(rowButton().disabled).toBe(true); expect(mocks.delete).toHaveBeenCalledTimes(1);
	});
	it('does not send deletion when the fresh inventory no longer contains the exact ID', async () => {
		mocks.get.mockResolvedValueOnce(inventory()).mockResolvedValueOnce(inventory('volumes', defaults.projectId, []));
		render(ProjectResourceMonitor, defaults); await confirm(); await screen.findByText(t('resourceMonitor.changed'));
		expect(mocks.delete).not.toHaveBeenCalled();
	});
	it('never replays unknown deletion and requires explicit readback plus a new confirmation', async () => {
		mocks.delete.mockRejectedValueOnce(new Error('connection lost after dispatch'));
		render(ProjectResourceMonitor, defaults); await confirm(); await screen.findByText(t('resourceMonitor.unknown'));
		expect(mocks.get).toHaveBeenCalledTimes(2); expect(mocks.delete).toHaveBeenCalledTimes(1);
		expect(screen.queryByRole('dialog')).toBeNull(); expect(screen.queryByText(resource.name)).toBeNull();
		await fireEvent.click(refresh()); await screen.findByText(resource.name); await screen.findByText(t('resourceMonitor.readback'));
		expect(mocks.delete).toHaveBeenCalledTimes(1); expect(rowButton().disabled).toBe(false);
		await fireEvent.click(rowButton()); expect(mocks.delete).toHaveBeenCalledTimes(1);
	});
	it.each([403, 409])('distinguishes native refusal %s from an unknown mutation outcome', async status => {
		mocks.delete.mockRejectedValueOnce(new ApiError(status, 'private native provider body'));
		render(ProjectResourceMonitor, defaults); await confirm();
		await screen.findByText(t('resourceMonitor.refused'));
		expect(screen.queryByText(t('resourceMonitor.unknown'))).toBeNull();
		expect(screen.queryByText('private native provider body')).toBeNull();
		expect(mocks.delete).toHaveBeenCalledTimes(1);
		await fireEvent.click(refresh()); await screen.findByText(resource.name);
		expect(mocks.delete).toHaveBeenCalledTimes(1);
	});
	it.each(['project', 'domain', 'kind'])('aborts late lists and closes confirmations when %s changes', async dimension => {
		const view = render(ProjectResourceMonitor, defaults); await screen.findByText(resource.name); await fireEvent.click(rowButton());
		const pending = Promise.withResolvers<unknown>(); mocks.get.mockReturnValueOnce(pending.promise);
		const props = { ...defaults, ...(dimension === 'project' ? { projectId: 'next-project' } : dimension === 'domain' ? { domainId: 'next-domain' } : { kind: 'instances' }) };
		await view.rerender(props); expect(screen.queryByRole('dialog')).toBeNull();
		const signal = mocks.get.mock.calls.at(-1)?.[3].signal as AbortSignal;
		await view.rerender(defaults); expect(signal.aborted).toBe(true);
		pending.resolve(inventory(props.kind, props.projectId, [{ ...resource, name: 'late-response' }])); await tick();
		expect(screen.queryByText('late-response')).toBeNull(); expect(mocks.delete).not.toHaveBeenCalled();
	});
	it('fences same-tick auth ABA and late mutation results', async () => {
		const pending = Promise.withResolvers<unknown>(); mocks.delete.mockReturnValueOnce(pending.promise);
		render(ProjectResourceMonitor, defaults); await confirm(); await waitFor(() => expect(mocks.delete).toHaveBeenCalledOnce());
		const old = get(auth); auth.set({ ...old, userId: 'other-admin' }); auth.set(old); await tick();
		pending.resolve(undefined); await tick(); expect(screen.queryByRole('dialog')).toBeNull();
		expect(screen.queryByText(t('resourceMonitor.accepted'))).toBeNull(); expect(screen.queryByText(t('resourceMonitor.pending'))).toBeNull();
	});
	it('masks an unverified raw token replacement until verification and keeps the draft', async () => {
		render(ProjectResourceMonitor, defaults); await screen.findByText(resource.name); await fireEvent.click(rowButton());
		auth.update(value => ({ ...value, token: 'rotated-token' })); await tick();
		// Direct store replacement starts verification; the same logical owner's
		// confirmation is masked, then returns after the continuation is verified.
		expect(screen.queryByRole('dialog')).toBeNull();
		authReady.set(true); await tick();
		const dialog = screen.getByRole('dialog'); await fireEvent.input(within(dialog).getByLabelText(t('resourceMonitor.confirmId')), { target: { value: resource.id } });
		await fireEvent.click(within(dialog).getByRole('button', { name: t('resourceMonitor.remove') }));
		await waitFor(() => expect(mocks.delete).toHaveBeenCalledOnce());
		expect(mocks.delete.mock.calls[0][1]).toBe('rotated-token');
	});
	it('retains the typed confirmation across a verified native refresh continuation', async () => {
		auth.update(value => ({ ...value, identityDomainId: 'accounts', identityDomainName: 'Accounts' }));
		authReady.set(true);
		render(ProjectResourceMonitor, defaults);
		await screen.findByText(resource.name); await fireEvent.click(rowButton());
		const dialog = screen.getByRole('dialog');
		await fireEvent.input(within(dialog).getByLabelText(t('resourceMonitor.confirmId')), { target: { value: resource.id } });
		const current = get(auth);
		setAuth(refreshAuthState({ token: 'rotated-token', user_id: current.userId!, username: 'admin',
			project_id: current.projectId!, project_name: 'Observation', expires_at: null,
			domain_id: current.domainId!, domain_name: 'Working', identity_domain_id: 'accounts', identity_domain_name: 'Accounts',
			is_system_admin: true, can_write: current.canWrite, roles: current.roles,
			is_domain_manager: current.isDomainManager }, current));
		expect(get(authReady)).toBe(true);
		await tick();
		expect(screen.getByRole('dialog')).toBe(dialog);
		expect((within(dialog).getByLabelText(t('resourceMonitor.confirmId')) as HTMLInputElement).value).toBe(resource.id);
		await fireEvent.click(within(dialog).getByRole('button', { name: t('resourceMonitor.remove') }));
		await waitFor(() => expect(mocks.delete).toHaveBeenCalledOnce());
		expect(mocks.delete.mock.calls[0][1]).toBe('rotated-token');
	});
	it('does not truncate long native container names used as resource IDs', async () => {
		const longId = 'container-' + 'x'.repeat(240); const longResource = { id: longId, name: longId, status: null };
		mocks.get.mockResolvedValue(inventory('object_containers', defaults.projectId, [longResource]));
		render(ProjectResourceMonitor, { ...defaults, kind: 'object_containers' });
		await screen.findByRole('button', { name: t('resourceMonitor.removeLabel', { id: longId }) });
		await fireEvent.click(screen.getByRole('button', { name: t('resourceMonitor.removeLabel', { id: longId }) }));
		const dialog = screen.getByRole('dialog'); await fireEvent.input(within(dialog).getByLabelText(t('resourceMonitor.confirmId')), { target: { value: longId } });
		await fireEvent.click(within(dialog).getByRole('button', { name: t('resourceMonitor.remove') }));
		await waitFor(() => expect(mocks.delete).toHaveBeenCalledOnce()); expect(mocks.delete.mock.calls[0][0]).toContain(`/object_containers/${longId}?`);
	});
	it.each(['constructor', 'toString', '__proto__'])('can explicitly delete a native container named %s', async name => {
		mocks.get.mockResolvedValue(inventory('object_containers', defaults.projectId, [{ id: name, name, status: null }]));
		render(ProjectResourceMonitor, { ...defaults, kind: 'object_containers' });
		const button = await screen.findByRole('button', { name: t('resourceMonitor.removeLabel', { id: name }) }) as HTMLButtonElement;
		expect(button.disabled).toBe(false);
		expect(screen.queryByText(t('resourceMonitor.unknownStatus'))).toBeNull();
		await fireEvent.click(button);
		const dialog = screen.getByRole('dialog');
		await fireEvent.input(within(dialog).getByLabelText(t('resourceMonitor.confirmId')), { target: { value: name } });
		await fireEvent.click(within(dialog).getByRole('button', { name: t('resourceMonitor.remove') }));
		await waitFor(() => expect(mocks.delete).toHaveBeenCalledOnce());
		expect(mocks.delete.mock.calls[0][0]).toContain(`/object_containers/${name}?`);
		await screen.findByText(t('resourceMonitor.pending'));
	});
});
