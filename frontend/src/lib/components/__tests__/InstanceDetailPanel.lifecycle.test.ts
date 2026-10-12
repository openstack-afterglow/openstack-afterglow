import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { fromStore, writable } from 'svelte/store';
import type { Writable } from 'svelte/store';
import type { Instance } from '$lib/types/compute';
import type { InstanceDetailController } from '$lib/stores/instanceDetailController.svelte';
import { initLocale } from '$lib/i18n/runtime.svelte';
import { t } from '$lib/i18n/ns/instance';

const mocks = vi.hoisted(() => ({
	controller: undefined as unknown,
	get: vi.fn(),
	fetchInstance: vi.fn(),
	loadResizeFlavors: vi.fn(),
	doResize: vi.fn(),
}));
vi.mock('$lib/stores/auth', () => ({
	auth: writable({ token: 'token-a', projectId: 'project-a', userId: 'user-a', isSystemAdmin: false }),
	canWrite: writable(true),
}));
vi.mock('$app/navigation', () => ({ goto: vi.fn() }));
vi.mock('$lib/api/client', () => ({ api: { get: mocks.get } }));
vi.mock('$lib/stores/instanceDetailController.svelte', () => ({
	createInstanceDetailController: () => mocks.controller,
	provideInstanceDetailController: vi.fn(),
	useInstanceDetailController: () => mocks.controller,
}));
// Keep the actual header, information, resize modal, shared Button/Alert/Modal and i18n.
// Network/storage/metrics behavior has its own suites and is outside this assignment.
vi.mock('$lib/components/instance/MetricsPanel.svelte', () => import('./_UnrelatedInstanceDetailSection.svelte'));
vi.mock('$lib/components/instance/ConsoleSection.svelte', () => import('./_UnrelatedInstanceDetailSection.svelte'));
vi.mock('$lib/components/instance/NetworkSection.svelte', () => import('./_UnrelatedInstanceDetailSection.svelte'));
vi.mock('$lib/components/instance/VolumesSection.svelte', () => import('./_UnrelatedInstanceDetailSection.svelte'));
vi.mock('$lib/components/instance/StorageAttachmentsSection.svelte', () => import('./_UnrelatedInstanceDetailSection.svelte'));
vi.mock('$lib/components/instance/UnionInfoSection.svelte', () => import('./_UnrelatedInstanceDetailSection.svelte'));

import { auth, canWrite } from '$lib/stores/auth';
import InstanceDetailPanel from '../InstanceDetailPanel.svelte';

interface TestIdentity { token: string | null; projectId: string | null; userId: string; isSystemAdmin: boolean }
const identity = auth as unknown as Writable<TestIdentity>;
const permission = canWrite as unknown as Writable<boolean>;
let controllerState: Writable<InstanceDetailController>;
const instance = {
	id: 'instance-a', name: 'linux-vm', status: 'ACTIVE', project_id: 'project-a',
	user_id: 'user-a', created_at: '2026-10-12T00:00:00Z', os_type: 'linux',
	image_id: 'image-a', image_name: 'Ubuntu', flavor_id: 'flavor-current', flavor_name: 'm1.small',
	key_name: 'my-keypair', ip_addresses: [], union_libraries: [], union_strategy: null,
} as Instance;
const suggested = { id: 'flavor-small', name: 'm1.tiny', vcpus: 1, ram: 512, disk: 20, is_public: true };
const summary = {
	prometheus_available: true,
	stats: { cpu: { avg: 1, min: 0, max: 3 }, memory: { avg: 5, min: 1, max: 10 } },
	recommendation: { underutilized: true, reason: null, current_flavor: null, suggested_flavor: suggested },
};

function setup(overrides: Partial<InstanceDetailController> = {}) {
	controllerState = writable({
		instance, instanceId: instance.id, effectiveProjectId: instance.project_id,
		loading: false, refreshing: false, error: '', actioning: null, deleting: false,
		consoleOpening: false, consoleOpenMessage: '', consoleOpenError: '', migrationStatus: null,
		canChangePassword: false, passwordPrecheckLoading: false,
		formatDate: (date: string) => date, ownerDisplay: null, fixedIpsList: [], floatingIpsList: [],
		detailPollAr: { active: false, intervalSeconds: 15, intervalOptions: [15, 30] },
		manualRefresh: vi.fn(), fetchInstance: mocks.fetchInstance,
		performAction: vi.fn(), deleteInstance: vi.fn(), openConsole: vi.fn(),
		resizeError: '', resizeLoading: false, resizeFlavorsLoading: false,
		resizeFlavors: [suggested], loadResizeFlavors: mocks.loadResizeFlavors, doResize: mocks.doResize,
		...overrides,
	} as unknown as InstanceDetailController);
	const state = fromStore(controllerState);
	mocks.controller = new Proxy(state.current, {
		get: (_target, key) => state.current[key as keyof InstanceDetailController],
		set: (_target, key, value) => {
			controllerState.update(s => ({ ...s, [key]: value }));
			return true;
		},
	});
}
function resizeButtons() {
	return screen.queryAllByRole<HTMLButtonElement>('button', { name: t('header.resize') });
}
function resizeDialog() {
	return screen.queryByRole('dialog', { name: t('resize.title') });
}
async function openHeaderResize() {
	await fireEvent.click(resizeButtons()[0]);
	return screen.findByRole('dialog', { name: t('resize.title') });
}

beforeEach(() => {
	vi.clearAllMocks();
	mocks.get.mockResolvedValue(summary);
	mocks.loadResizeFlavors.mockResolvedValue(undefined);
	identity.set({ token: 'token-a', projectId: 'project-a', userId: 'user-a', isSystemAdmin: false });
	permission.set(true);
	initLocale('ko');
	setup();
});
afterEach(() => cleanup());

describe('Instance detail stopped lifecycle presentation', () => {
	it.each([null, 'project-a'])('gates header and recommendation resize across ACTIVE → SHUTOFF in %s mode', async adminProjectId => {
		render(InstanceDetailPanel, { instanceId: instance.id, adminProjectId });
		await waitFor(() => expect(mocks.get).toHaveBeenCalled());
		await tick();
		expect(resizeButtons()).toHaveLength(0);
		expect(screen.queryByText(t('panel.stoppedQuotaWarning'))).toBeNull();
		controllerState.update(s => ({ ...s, instance: { ...instance, status: 'SHUTOFF' } }));
		await waitFor(() => expect(resizeButtons()).toHaveLength(2));
		expect(screen.getByText(t('panel.stoppedQuotaWarning')).closest('[role="status"]')).toBeTruthy();
		await fireEvent.click(resizeButtons()[1]);
		const dialog = await screen.findByRole('dialog', { name: t('resize.title') });
		expect(within(dialog).getByRole<HTMLSelectElement>('combobox', { name: t('resize.newFlavor') }).value).toBe(suggested.id);
		expect(mocks.loadResizeFlavors).toHaveBeenCalledTimes(1);
		await fireEvent.click(within(dialog).getByRole('button', { name: t('resize.cancel') }));
		expect(resizeDialog()).toBeNull();
		await openHeaderResize();
		expect(mocks.loadResizeFlavors).toHaveBeenCalledTimes(2);
		controllerState.update(s => ({ ...s, instance: { ...instance, status: 'ACTIVE' } }));
		await tick();
		expect(resizeDialog()).toBeNull();
		expect(resizeButtons()).toHaveLength(0);
		expect(screen.queryByText(t('panel.stoppedQuotaWarning'))).toBeNull();
		expect(mocks.doResize).not.toHaveBeenCalled();
	});

	it.each([null, 'project-a'])('retains stopped quota information and hides mutations for a Windows reader in %s mode', async adminProjectId => {
		permission.set(false);
		setup({ instance: { ...instance, status: 'SHUTOFF', os_type: ' WINDOWS ', image_id: null, image_name: null, ssh_access_mode: 'github', github_login: 'OctoCat' } });
		render(InstanceDetailPanel, { instanceId: instance.id, adminProjectId });
		await tick();
		expect(screen.getByText(t('panel.stoppedQuotaWarning'))).toBeTruthy();
		expect(resizeButtons()).toHaveLength(0);
		expect(screen.queryByRole('button', { name: t('header.start') })).toBeNull();
		expect(screen.queryByRole('button', { name: t('header.shelve') })).toBeNull();
		expect(screen.queryByRole('button', { name: t('header.delete') })).toBeNull();
		expect(screen.queryByText(t('info.keyPair'))).toBeNull();
		expect(screen.queryByText(t('info.githubSsh'))).toBeNull();
		expect(screen.queryByText('@OctoCat')).toBeNull();
		expect(screen.getByText(t('info.bootFromVolume'))).toBeTruthy();
		expect(mocks.loadResizeFlavors).not.toHaveBeenCalled();
	});

	it.each([
		{ name: 'another action', overrides: { actioning: 'attach-vol' } },
		{ name: 'deletion', overrides: { deleting: true } },
		{ name: 'resize submission', overrides: { resizeLoading: true } },
		{ name: 'loading instance', overrides: { loading: true } },
		{ name: 'wrong instance', overrides: { instance: { ...instance, id: 'instance-other', status: 'SHUTOFF' } } },
		{ name: 'wrong project', overrides: { instance: { ...instance, project_id: 'project-other', status: 'SHUTOFF' } } },
	] satisfies { name: string; overrides: Partial<InstanceDetailController> }[])('guards opening and the recommendation shortcut during $name', async ({ overrides }) => {
		setup({ instance: { ...instance, status: 'SHUTOFF' }, ...overrides });
		render(InstanceDetailPanel, { instanceId: instance.id });
		await waitFor(() => expect(resizeButtons()).toHaveLength(2));
		expect(resizeButtons()[1].disabled).toBe(true);
		// Even when the header still displays a stopped snapshot, the panel owns the scope/open guard.
		await fireEvent.click(resizeButtons()[0]);
		await fireEvent.click(resizeButtons()[1]);
		expect(resizeDialog()).toBeNull();
		expect(mocks.loadResizeFlavors).not.toHaveBeenCalled();
	});

	it.each(['action', 'deletion', 'loading', 'permission', 'project', 'token', 'logout', 'instance'] as const)('closes an open modal on %s loss without submitting or resurrecting it', async loss => {
		setup({ instance: { ...instance, status: 'SHUTOFF' } });
		const view = render(InstanceDetailPanel, { instanceId: instance.id });
		await openHeaderResize();
		if (loss === 'action') controllerState.update(s => ({ ...s, actioning: 'start' }));
		if (loss === 'deletion') controllerState.update(s => ({ ...s, deleting: true }));
		if (loss === 'loading') controllerState.update(s => ({ ...s, loading: true }));
		if (loss === 'permission') permission.set(false);
		if (loss === 'project') identity.update(s => ({ ...s, projectId: 'project-b' }));
		if (loss === 'token') identity.update(s => ({ ...s, token: 'token-b' }));
		if (loss === 'logout') identity.update(s => ({ ...s, token: null }));
		if (loss === 'instance') await view.rerender({ instanceId: 'instance-b' });
		await tick();
		expect(resizeDialog()).toBeNull();
		expect(mocks.doResize).not.toHaveBeenCalled();
		controllerState.update(s => ({ ...s, actioning: null, deleting: false, resizeLoading: false, loading: false }));
		permission.set(true);
		identity.set({ token: 'token-a', projectId: 'project-a', userId: 'user-a', isSystemAdmin: false });
		await view.rerender({ instanceId: instance.id });
		await tick();
		expect(resizeDialog()).toBeNull();
	});

	it('keeps the selected resize and failure feedback visible through its own busy state', async () => {
		setup({ instance: { ...instance, status: 'SHUTOFF' } });
		render(InstanceDetailPanel, { instanceId: instance.id });
		await openHeaderResize();
		await fireEvent.change(within(resizeDialog()!).getByRole('combobox', { name: t('resize.newFlavor') }), { target: { value: suggested.id } });
		controllerState.update(s => ({ ...s, resizeLoading: true }));
		await tick();
		const busyDialog = resizeDialog()!;
		expect(busyDialog).not.toBeNull();
		expect(within(busyDialog).getByRole<HTMLSelectElement>('combobox', { name: t('resize.newFlavor') }).value).toBe(suggested.id);
		expect(within(busyDialog).getByRole<HTMLButtonElement>('button', { name: t('resize.resizing') }).disabled).toBe(true);
		controllerState.update(s => ({ ...s, resizeLoading: false, resizeError: 'Nova unavailable' }));
		await tick();
		expect(resizeDialog()).not.toBeNull();
		expect(within(resizeDialog()!).getByText('Nova unavailable')).toBeTruthy();
		expect(within(resizeDialog()!).getByRole<HTMLButtonElement>('button', { name: t('resize.submit') }).disabled).toBe(false);
	});

	it('uses the administrator target scope rather than the caller project for stopped resize', async () => {
		identity.update(s => ({ ...s, isSystemAdmin: true }));
		setup({ instance: { ...instance, status: 'SHUTOFF', project_id: 'project-other' } });
		render(InstanceDetailPanel, { instanceId: instance.id, adminProjectId: 'project-other' });
		await waitFor(() => expect(resizeButtons()).toHaveLength(2));
		expect(mocks.get).toHaveBeenCalledWith(`/api/v1/instances/${instance.id}/metrics-summary?range=7d`, 'token-a', 'project-other');
		await openHeaderResize();
		expect(mocks.loadResizeFlavors).toHaveBeenCalledTimes(1);
		expect(resizeDialog()).not.toBeNull();
	});

	it('closes an admin-target modal when the target project changes despite unchanged caller auth', async () => {
		setup({ instance: { ...instance, status: 'SHUTOFF' } });
		const view = render(InstanceDetailPanel, { instanceId: instance.id, adminProjectId: 'project-a' });
		await openHeaderResize();
		await view.rerender({ instanceId: instance.id, adminProjectId: 'project-b' });
		expect(resizeDialog()).toBeNull();
		expect(mocks.doResize).not.toHaveBeenCalled();
	});

	it('does not reopen a modal when a flavor request completes after the instance starts', async () => {
		let resolve!: () => void;
		mocks.loadResizeFlavors.mockReturnValueOnce(new Promise<void>(done => { resolve = done; }));
		setup({ instance: { ...instance, status: 'SHUTOFF' } });
		render(InstanceDetailPanel, { instanceId: instance.id });
		await openHeaderResize();
		controllerState.update(s => ({ ...s, instance: { ...instance, status: 'ACTIVE' } }));
		await tick();
		resolve();
		await tick();
		expect(resizeDialog()).toBeNull();
		expect(mocks.doResize).not.toHaveBeenCalled();
	});

	it('discards a previous-scope recommendation instead of preselecting its flavor', async () => {
		let resolveOld!: (value: typeof summary) => void;
		mocks.get.mockReturnValueOnce(new Promise<typeof summary>(done => { resolveOld = done; }));
		mocks.get.mockResolvedValueOnce({ ...summary, recommendation: { ...summary.recommendation, suggested_flavor: { ...suggested, id: 'flavor-new', name: 'm1.new' } } });
		setup({ instance: { ...instance, status: 'SHUTOFF' } });
		const view = render(InstanceDetailPanel, { instanceId: instance.id });
		await waitFor(() => expect(mocks.get).toHaveBeenCalledTimes(1));
		controllerState.update(s => ({ ...s, instance: { ...instance, id: 'instance-b', status: 'SHUTOFF' }, resizeFlavors: [{ ...suggested, id: 'flavor-new', name: 'm1.new' }] }));
		await view.rerender({ instanceId: 'instance-b' });
		await waitFor(() => expect(resizeButtons()).toHaveLength(2));
		resolveOld(summary);
		await tick();
		await fireEvent.click(resizeButtons()[1]);
		const dialog = await screen.findByRole('dialog', { name: t('resize.title') });
		expect(within(dialog).getByRole<HTMLSelectElement>('combobox', { name: t('resize.newFlavor') }).value).toBe('flavor-new');
	});
});
