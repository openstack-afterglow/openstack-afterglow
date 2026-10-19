import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { get } from 'svelte/store';
import { tick } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '$lib/api/client';
import { auth } from '../auth';
import { siteConfig } from '$lib/config/site';
import { closeWizard, openWizard, resetWizard, wizard, wizardPassword } from '../wizard';
import type { VmCreateStore } from '../vmCreateStore.svelte';
import { t } from '$lib/i18n/ns/vm-wizard';
import type * as MockupTransport from '$lib/mockup/transport';

vi.mock('$app/navigation', () => ({ goto: vi.fn() }));
vi.mock('$app/environment', () => ({ browser: true }));
vi.mock('$lib/mockup/transport', async importOriginal => ({
	...await importOriginal<typeof MockupTransport>(),
	maybeMockInstanceCreateStream: () => null,
}));
import Wrapper from './_VmCreatePasswordWrapper.svelte';

const metadata = { os_type: ' Windows ', windows_initial_password_method: 'nova-adminpass-configdrive', os_admin_user: 'GuestAdmin' };
const unsupportedMetadata = [
	{ name: 'legacy-method', metadata: { ...metadata, windows_initial_password_method: 'cloudbase-user-data' } },
	{ name: 'unknown-method', metadata: { ...metadata, windows_initial_password_method: 'unknown' } },
	{ name: 'missing-method', metadata: { os_type: 'windows', os_admin_user: 'GuestAdmin' } },
	{ name: 'missing-metadata', metadata: { os_type: 'windows' } },
	{ name: 'missing-account', metadata: { os_type: 'windows', windows_initial_password_method: 'nova-adminpass-configdrive' } },
	{ name: 'blank-account', metadata: { ...metadata, os_admin_user: '   ' } },
	{ name: 'invalid-account', metadata: { ...metadata, os_admin_user: 'admin\n' } },
];
const flavor = {
	id: 'flavor-a', name: 'small', vcpus: 1, ram: 1024, disk: 20,
	eligibility: {
		selectable: true, blockers: [], requirements: { instances: 1, cores: 1, ram_mb: 1024, gpus: {} },
		remaining: { instances: 5, cores: 8, ram_mb: 8192, gpus: {} },
		capacity: { status: 'available', checked_at: '2026-10-01T00:00:00+00:00', candidate_hosts: 1, cpu_resource_class: 'VCPU', remaining_vcpus: 8, remaining_ram_mb: 8192 },
	},
};
function json(value: unknown) { return new Response(JSON.stringify(value), { headers: { 'Content-Type': 'application/json' } }); }
function deferred<T>() {
	let resolve!: (value: T) => void;
	const promise = new Promise<T>(res => { resolve = res; });
	return { promise, resolve };
}
let requests: { path: string; body: Record<string, unknown> }[];
let refresh: (() => Promise<Response>) | null;
let flavorCalls: number;

beforeEach(() => {
	vi.restoreAllMocks();
	api.clearPrefetchCache();
	resetWizard();
	openWizard();
	auth.set({ token: 'token-a', refreshToken: null, accessExpiresAt: null, userId: 'user-a', username: 'user-a', projectId: 'project-a', projectName: 'A', availableProjects: [], roles: [], isSystemAdmin: false, federated: false, domainId: 'domain-1', domainName: 'Domain', isDomainManager: false });
	siteConfig.update(value => ({ ...value, runtime: { ...value.runtime, api_base: 'https://afterglow.test' }, services: { ...value.services, manila: false } }));
	requests = [];
	refresh = null;
	flavorCalls = 0;
	vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
		const path = new URL(String(input)).pathname;
		if (path.endsWith('/instances/async')) {
			requests.push({ path, body: JSON.parse(String(init?.body)) });
			return new Response('data: {"step":"failed","message":"synthetic refusal"}\n\n', { headers: { 'Content-Type': 'text/event-stream' } });
		}
		if (path === '/api/v1/images') return json([
			{ id: 'windows-a', name: 'Unrelated name', status: 'active', ...metadata },
			{ id: 'windows-b', name: 'Another image', status: 'active', ...metadata },
			{ id: 'ubuntu', name: 'Ubuntu', status: 'active', os_distro: 'ubuntu' },
			{ id: 'name-only', name: 'Windows 11 Ubuntu', status: 'active' },
			...unsupportedMetadata.map(item => ({ id: item.name, name: 'Windows Ubuntu', status: 'active', ...item.metadata })),
		]);
		if (path.endsWith('/volumes') || path.endsWith('/volumes-for-project')) return json([
			{ id: 'volume-a', name: 'Boot disk', status: 'available', size: 40, bootable: true, attachments: [], volume_image_metadata: metadata },
			...unsupportedMetadata.map(item => ({ id: item.name, name: 'Boot disk', status: 'available', size: 40, bootable: true, attachments: [], volume_image_metadata: item.metadata })),
		]);
		if (path.endsWith('/flavors') || path.endsWith('/flavors-for-project')) {
			flavorCalls += 1;
			return refresh ? refresh() : json([flavor]);
		}
		if (path.endsWith('/cloud-init/library')) return json({ history: [], presets: [] });
		return json([]);
	}));
});
afterEach(() => { cleanup(); closeWizard(); vi.unstubAllGlobals(); });

async function start(adminMode = false, bootSource: 'image' | 'volume' = 'image') {
	if (adminMode) wizard.update(w => ({ ...w, targetProjectId: 'target-a' }));
	let store!: VmCreateStore;
	const view = render(Wrapper, { adminMode, onStore: value => { store = value; } });
	await vi.waitFor(() => expect(store.images.length).toBe(4 + unsupportedMetadata.length));
	await vi.waitFor(() => expect(store.volumes.length).toBe(1 + unsupportedMetadata.length));
	await vi.waitFor(() => expect(store.flavors.length).toBe(1));
	wizard.update(w => ({ ...w, bootSource, imageId: 'windows-a', bootVolumeId: 'volume-a', flavorId: 'flavor-a', flavorName: 'small', step: 5, keyName: null }));
	await tick();
	await tick();
	expect(screen.getByTestId('windows-password-config')).toBeTruthy();
	return { store, ...view };
}
async function enter(password = " Secret'123 ", confirmation = password) {
	await fireEvent.input(screen.getByLabelText(t('config.windows.password'), { exact: false }), { target: { value: password } });
	await fireEvent.input(screen.getByLabelText(t('config.windows.confirmation'), { exact: false }), { target: { value: confirmation } });
}

 describe('Windows first-boot password wizard', () => {
	it.each(['image', 'volume'] as const)('blocks retained review until %s boot metadata resolves and the password is entered', async source => {
		const pending = deferred<Response>();
		const initialFetch = vi.mocked(fetch).getMockImplementation()!;
		vi.mocked(fetch).mockImplementation((input, init) => {
			const path = new URL(String(input)).pathname;
			if (source === 'image' ? path === '/api/v1/images' : path === '/api/v1/volumes') return pending.promise;
			return initialFetch(input, init);
		});
		wizard.update(w => ({ ...w, bootSource: source, imageId: 'windows-a', bootVolumeId: 'volume-a', flavorId: 'flavor-a', step: 6 }));
		closeWizard();
		openWizard();
		let store!: VmCreateStore;
		render(Wrapper, { onStore: value => { store = value; } });
		await vi.waitFor(() => expect(store.flavors.length).toBe(1));
		await tick();
		expect(store.canNext).toBe(false);
		await store.deploy();
		expect(requests).toHaveLength(0);
		pending.resolve(json(source === 'image'
			? [{ id: 'windows-a', name: 'Windows', status: 'active', ...metadata }]
			: [{ id: 'volume-a', name: 'Boot disk', status: 'available', size: 40, bootable: true, attachments: [], volume_image_metadata: metadata }]));
		await vi.waitFor(() => expect(store.windowsAccount).toBe('GuestAdmin'));
		store.goTo(6);
		await tick();
		expect(store.canNext).toBe(false);
		await store.deploy();
		expect(requests).toHaveLength(0);
		store.goTo(5);
		await tick();
		await enter();
		expect(store.canNext).toBe(true);
	});

	it.each([[false, 'image'], [true, 'image'], [false, 'volume'], [true, 'volume']] as const)('supports marked %s / %s without SSH and discards secrets at submission', async (adminMode, source) => {
		const { container } = await start(adminMode, source);
		wizard.update(w => ({ ...w, keyName: 'retained-linux-key', sshAccessMode: 'github', githubUsername: 'octocat', bootVolumeSizeGb: 64, deleteBootVolumeOnTermination: true }));
		await tick();
		const setItem = vi.spyOn(Storage.prototype, 'setItem');
		const password = " Secret'123 ";
		expect(screen.getByTestId('readiness').textContent).toBe('blocked');
		await enter(password);
		expect(container.querySelectorAll('input[type="password"]')).toHaveLength(2);
		expect(container.querySelector('#create-keypair')).toBeNull();
		expect(container.querySelector('#cloud-init')).toBeNull();
		expect(screen.getByTestId('readiness').textContent).toBe('ready');
		await fireEvent.click(screen.getByTestId('next'));
		expect(screen.getByTestId('windows-password-review').textContent).toContain('GuestAdmin');
		expect(screen.getByTestId('windows-password-review').textContent).toContain(t('review.windows.provided'));
		expect(container.innerHTML).not.toContain(password);
		expect(container.textContent).not.toContain(password);
		expect(JSON.stringify(get(wizard))).not.toContain(password);
		await fireEvent.click(screen.getByTestId('deploy'));
		await vi.waitFor(() => expect(requests).toHaveLength(1));
		expect(requests[0].path).toBe(adminMode ? '/api/v1/admin/instances/async' : '/api/v1/instances/async');
		expect(requests[0].body).toMatchObject({ admin_pass: password, key_name: null, github_username: null, userdata: null, data_mounts: [] });
		if (source === 'image') {
			expect(requests[0].body).toMatchObject({ image_id: 'windows-a', boot_volume_size_gb: 64, delete_boot_volume_on_termination: true });
			expect(requests[0].body).not.toHaveProperty('boot_volume_id');
		} else {
			expect(requests[0].body).toMatchObject({ boot_volume_id: 'volume-a' });
			expect(requests[0].body).not.toHaveProperty('image_id');
		}
		if (adminMode) expect(requests[0].body).toMatchObject({ project_id: 'target-a' });
		expect(requests[0].body).not.toHaveProperty('confirmation');
		expect(get(wizardPassword)).toEqual({ password: '', confirmation: '' });
		expect(setItem.mock.calls.some(call => JSON.stringify(call).includes(password))).toBe(false);
	});

	it.each(['short', 'x'.repeat(129), 'secret\n123', 'secret\u0085123', 'mismatch'])('blocks Next and direct final submission for %s', async invalid => {
		const { store } = await start();
		wizardPassword.set({ password: invalid === 'mismatch' ? 'secret123' : invalid, confirmation: invalid === 'mismatch' ? 'different123' : invalid });
		await tick();
		expect(store.canNext).toBe(false);
		await fireEvent.click(screen.getByTestId('next'));
		expect(get(wizard).step).toBe(5);
		store.goTo(6);
		await tick();
		expect(store.canNext).toBe(false);
		await store.deploy();
		expect(requests).toHaveLength(0);
	});

	it.each([[false, 'image'], [true, 'image'], [false, 'volume'], [true, 'volume']] as const)('submits Windows GPU password without Linux bootstrap (admin=%s, source=%s)', async (adminMode, source) => {
		refresh = async () => json([{
			...flavor, name: 'gpu.a100x1_small',
			eligibility: {
				...flavor.eligibility,
				requirements: { ...flavor.eligibility.requirements, gpus: { a100: 1 } },
				remaining: { ...flavor.eligibility.remaining, gpus: { a100: 2 } },
			},
		}]);
		await start(adminMode, source);
		await enter();
		expect(screen.getByTestId('readiness').textContent).toBe('ready');
		await fireEvent.click(screen.getByTestId('next'));
		expect(screen.getByTestId('windows-password-review').textContent).toContain(t('review.windows.provided'));
		await fireEvent.click(screen.getByTestId('deploy'));
		await vi.waitFor(() => expect(requests).toHaveLength(1));
		expect(requests[0].path).toBe(adminMode ? '/api/v1/admin/instances/async' : '/api/v1/instances/async');
		expect(requests[0].body).toMatchObject({ flavor_id: 'flavor-a', admin_pass: " Secret'123 ", userdata: null, data_mounts: [], key_name: null, github_username: null });
		expect(get(wizardPassword)).toEqual({ password: '', confirmation: '' });
	});

	it('retains incompatible drafts, blocks mutation, and clears them only on explicit action', async () => {
		const { store } = await start();
		await enter();
		const drafts = { cloudInit: '#cloud-config\npackages: [git]', dataMounts: [{ fileStorageId: 'data', mountPoint: '/mnt/data', readOnly: false }] };
		wizard.update(w => ({ ...w, ...drafts }));
		await tick();
		expect(store.canNext).toBe(false);
		await store.deploy();
		expect(requests).toHaveLength(0);
		expect(get(wizard)).toMatchObject(drafts);
		await fireEvent.click(screen.getByRole('button', { name: t('config.windows.clearConflict') }));
		expect(get(wizard)).toMatchObject({ cloudInit: '', dataMounts: [] });
		expect(store.canNext).toBe(true);
	});

	it.each(['boot', 'boot-source', 'actor', 'token', 'project', 'target', 'close', 'reset', 'destroy'] as const)('clears drafts synchronously on %s', async transition => {
		const { store } = await start(true);
		await enter();
		if (transition === 'boot') wizard.update(w => ({ ...w, imageId: 'windows-b' }));
		if (transition === 'boot-source') wizard.update(w => ({ ...w, bootSource: 'volume' }));
		if (transition === 'actor') auth.update(a => ({ ...a, userId: 'user-b' }));
		if (transition === 'token') auth.update(a => ({ ...a, token: 'token-b' }));
		if (transition === 'project') auth.update(a => ({ ...a, projectId: 'project-b' }));
		if (transition === 'target') store.selectAdminProject('target-b', 'B');
		if (transition === 'close') closeWizard();
		if (transition === 'reset') resetWizard();
		if (transition === 'destroy') store.destroy();
		expect(get(wizardPassword)).toEqual({ password: '', confirmation: '' });
	});

	it('clears the password when switching between user and administrator mode', async () => {
		const { rerender } = await start();
		await enter();
		await rerender({ adminMode: true });
		await tick();
		expect(get(wizardPassword)).toEqual({ password: '', confirmation: '' });
	});

	it.each(['actor', 'boot-aba', 'close', 'draft', 'conflict', 'target'] as const)('refuses a stale pending submission after %s', async transition => {
		const { store } = await start(true);
		await enter();
		const pending = deferred<Response>();
		refresh = () => pending.promise;
		const calls = flavorCalls;
		const submission = store.deploy();
		await vi.waitFor(() => expect(flavorCalls).toBeGreaterThan(calls));
		if (transition === 'actor') auth.update(a => ({ ...a, userId: 'user-b' }));
		if (transition === 'boot-aba') {
			wizard.update(w => ({ ...w, imageId: 'windows-b' }));
			wizard.update(w => ({ ...w, imageId: 'windows-a' }));
		}
		if (transition === 'close') closeWizard();
		if (transition === 'draft') wizardPassword.update(d => ({ ...d, confirmation: 'changed' }));
		if (transition === 'conflict') wizard.update(w => ({ ...w, cloudInit: 'retained custom data' }));
		if (transition === 'target') store.selectAdminProject('target-b', 'B');
		pending.resolve(json([flavor]));
		await submission;
		expect(requests).toHaveLength(0);
	});

	it.each(([false, true] as const).flatMap(adminMode => (['image', 'volume'] as const).flatMap(source =>
		unsupportedMetadata.map(item => ({ adminMode, source, ...item }))
	)))('blocks $name Windows after a native selection (admin=$adminMode, source=$source)', async ({ adminMode, source, name }) => {
		const { store, container } = await start(adminMode, source);
		await enter();
		expect(store.canNext).toBe(true);
		wizard.update(w => ({
			...w, imageId: source === 'image' ? name : w.imageId, bootVolumeId: source === 'volume' ? name : w.bootVolumeId,
			keyName: 'retained-key', cloudInit: '#cloud-config', dataMounts: [{ fileStorageId: 'data', mountPoint: '/mnt/data', readOnly: false }],
		}));
		await tick();
		expect(store.isWindowsBoot).toBe(true);
		expect(store.windowsUnsupported).toBe(true);
		expect(store.githubSshEligible).toBe(false);
		expect(get(wizardPassword)).toEqual({ password: '', confirmation: '' });
		expect(screen.getByTestId('windows-unsupported-config')).toBeTruthy();
		expect(container.querySelector('#create-keypair')).toBeNull();
		expect(container.querySelector('#cloud-init')).toBeNull();
		expect(container.querySelector('#windows-password')).toBeNull();
		expect(screen.getByTestId('readiness').textContent).toBe('blocked');
		await fireEvent.click(screen.getByTestId('next'));
		expect(get(wizard).step).toBe(5);
		// Retained review state and a direct deploy cannot bypass the unsupported-image gate.
		store.goTo(6);
		await tick();
		expect(screen.getByTestId('windows-unsupported-review')).toBeTruthy();
		expect(screen.queryByTestId('windows-password-review')).toBeNull();
		expect(screen.getByTestId('readiness').textContent).toBe('blocked');
		await fireEvent.click(screen.getByTestId('deploy'));
		expect(requests).toHaveLength(0);
		expect(get(wizard).step).toBe(5);
		store.goTo(1);
		await tick();
		expect(store.canNext).toBe(false);
		await fireEvent.click(screen.getByTestId('next'));
		expect(get(wizard).step).toBe(1);
		// The first Flavor step must remain usable so the unsupported image can be replaced.
		store.goTo(2);
		await tick();
		expect(store.canNext).toBe(true);
		await fireEvent.click(screen.getByTestId('next'));
		expect(get(wizard).step).toBe(1);
		expect(store.canNext).toBe(false);
	});

	it('does not infer password support from a name and retains ordinary keypair and GitHub payloads', async () => {
		const { store, container } = await start();
		wizard.update(w => ({ ...w, imageId: 'name-only', imageName: 'Windows 11 Ubuntu', keyName: null }));
		await tick();
		expect(store.windowsAccount).toBeNull();
		expect(container.querySelector('#windows-password')).toBeNull();
		expect(store.canNext).toBe(false);
		wizard.update(w => ({ ...w, imageId: 'ubuntu', keyName: 'my-key', cloudInit: '#cloud-config\npackages: [git]' }));
		await tick();
		expect(store.canNext).toBe(true);
		await store.deploy();
		expect(requests[0].body).toMatchObject({ key_name: 'my-key', github_username: null, userdata: '#cloud-config\npackages: [git]' });
		expect(requests[0].body).not.toHaveProperty('admin_pass');
		await vi.waitFor(() => expect(store.deploying).toBe(false));
		wizard.update(w => ({ ...w, sshAccessMode: 'github', githubUsername: 'octocat', githubProfile: { id: 1, login: 'octocat', name: null, public_email: null, html_url: 'https://github.com/octocat', has_public_keys: true, verified_at: '2026-10-01T00:00:00Z' } }));
		await tick();
		expect(store.canNext).toBe(true);
		await store.deploy();
		expect(requests[1].body).toMatchObject({ key_name: null, github_username: 'octocat', userdata: '#cloud-config\npackages: [git]' });
		expect(requests[1].body).not.toHaveProperty('admin_pass');
	});
});

describe('Image boot volume minimum', () => {
	beforeEach(() => {
		const initialFetch = vi.mocked(fetch).getMockImplementation()!;
		vi.mocked(fetch).mockImplementation(async (input, init) => {
			const response = await initialFetch(input, init);
			if (new URL(String(input)).pathname !== '/api/v1/images') return response;
			const images = await response.json() as { id: string; min_disk?: number }[];
			return json(images.map(image => ({
				...image, min_disk: ['windows-a', 'ubuntu'].includes(image.id) ? 80 : 1,
			})));
		});
	});

	function footerAction(container: HTMLElement) {
		return container.querySelector('[data-tour="wizard-next"] button') as HTMLButtonElement;
	}

	it.each([[20, 80], [500, 500]])('raises %i GB only as needed and preserves it on a smaller selection', async (draft, expected) => {
		wizard.update(w => ({ ...w, bootVolumeSizeGb: draft }));
		const { store, container } = await start();
		expect(store.minBootVolumeSizeGb).toBe(80);
		expect(get(wizard).bootVolumeSizeGb).toBe(expected);
		const size = container.querySelector('#boot-volume-size') as HTMLInputElement;
		expect(size.min).toBe('80');
		expect(size.max).toBe('16384');
		expect(size.value).toBe(String(expected));
		expect(screen.getByText(t('config.rootDisk.minimumHelp', { min: 80 }))).toBeTruthy();
		store.goTo(1);
		await tick();
		store.selectImage('windows-b', 'Another image');
		await tick();
		expect(store.minBootVolumeSizeGb).toBe(1);
		expect(get(wizard).bootVolumeSizeGb).toBe(expected);
	});

	it('raises a retained draft only when delayed authoritative image metadata resolves', async () => {
		const pending = deferred<Response>();
		const initialFetch = vi.mocked(fetch).getMockImplementation()!;
		vi.mocked(fetch).mockImplementation((input, init) =>
			new URL(String(input)).pathname === '/api/v1/images' ? pending.promise : initialFetch(input, init));
		wizard.update(w => ({ ...w, imageId: 'ubuntu', flavorId: 'flavor-a', keyName: 'my-key', step: 6 }));
		let store!: VmCreateStore;
		const { container } = render(Wrapper, { onStore: value => { store = value; } });
		await vi.waitFor(() => expect(store.flavors.length).toBe(1));
		expect(get(wizard).bootVolumeSizeGb).toBe(20);
		expect(footerAction(container).disabled).toBe(true);
		await store.deploy();
		expect(requests).toHaveLength(0);
		expect(get(wizard).step).toBe(1);
		pending.resolve(json([{ id: 'ubuntu', name: 'Generic image', status: 'active', min_disk: 80 }]));
		await vi.waitFor(() => expect(get(wizard).bootVolumeSizeGb).toBe(80));
		expect(store.minBootVolumeSizeGb).toBe(80);
		store.goTo(6);
		await tick();
		expect(footerAction(container).disabled).toBe(false);
		await store.deploy();
		expect(requests).toHaveLength(1);
		expect(requests[0].body).toMatchObject({ image_id: 'ubuntu', boot_volume_size_gb: 80 });
	});

	it.each(['79', '', '80.5'])('leaves the edited %s draft intact, blocks Next/review/direct deploy, and admits 80', async draft => {
		const { store, container } = await start();
		await enter();
		const size = container.querySelector('#boot-volume-size') as HTMLInputElement;
		await fireEvent.input(size, { target: { value: draft } });
		await tick();
		expect(size.value).toBe(draft);
		expect(size.getAttribute('aria-invalid')).toBe('true');
		expect(size.getAttribute('aria-describedby')).toBe('boot-volume-size-help');
		expect(screen.getByText(t('config.rootDisk.sizeInvalid', { min: 80 }))).toBeTruthy();
		expect(store.bootVolumeSizeReady).toBe(false);
		expect(footerAction(container).disabled).toBe(true);
		store.nextStep();
		expect(get(wizard).step).toBe(5);
		store.goTo(6);
		await tick();
		expect(store.canNext).toBe(false);
		expect(footerAction(container).disabled).toBe(true);
		const calls = flavorCalls;
		await store.deploy();
		expect(requests).toHaveLength(0);
		expect(flavorCalls).toBe(calls);
		expect(get(wizard).step).toBe(5);
		expect(get(wizardPassword).password).toBe(" Secret'123 ");
		await tick();
		await fireEvent.input(container.querySelector('#boot-volume-size')!, { target: { value: '80' } });
		expect(store.bootVolumeSizeReady).toBe(true);
		expect(footerAction(container).disabled).toBe(false);
		expect(container.querySelector('#boot-volume-size')?.getAttribute('aria-invalid')).toBe('false');
		await fireEvent.click(footerAction(container));
		expect(get(wizard).step).toBe(6);
		expect(footerAction(container).disabled).toBe(false);
		await fireEvent.click(footerAction(container));
		await vi.waitFor(() => expect(requests).toHaveLength(1));
		expect(requests[0].body).toMatchObject({ boot_volume_size_gb: 80, admin_pass: " Secret'123 " });
	});

	it.each([NaN, Infinity, -Infinity])('rejects a nonfinite %s draft without replacing it', async draft => {
		const { store } = await start();
		await enter();
		wizard.update(w => ({ ...w, bootVolumeSizeGb: draft }));
		await tick();
		expect(get(wizard).bootVolumeSizeGb).toBe(draft);
		expect(store.bootVolumeSizeReady).toBe(false);
		expect(store.canNext).toBe(false);
		store.goTo(6);
		await tick();
		expect(store.canNext).toBe(false);
		await store.deploy();
		expect(requests).toHaveLength(0);
		expect(get(wizard).step).toBe(5);
	});

	it.each([false, true])('rechecks a midflight undersized draft after flavor refresh (admin=%s)', async adminMode => {
		const { store } = await start(adminMode);
		await enter();
		store.goTo(6);
		await tick();
		const pending = deferred<Response>();
		refresh = () => pending.promise;
		const calls = flavorCalls;
		const submission = store.deploy();
		await vi.waitFor(() => expect(flavorCalls).toBeGreaterThan(calls));
		wizard.update(w => ({ ...w, bootVolumeSizeGb: 79 }));
		pending.resolve(json([flavor]));
		await submission;
		expect(requests).toHaveLength(0);
		expect(get(wizard)).toMatchObject({ step: 5, bootVolumeSizeGb: 79 });
		expect(get(wizardPassword).password).toBe(" Secret'123 ");
		refresh = null;
		wizard.update(w => ({ ...w, bootVolumeSizeGb: 80 }));
		await tick();
		await store.deploy();
		expect(requests).toHaveLength(1);
		expect(requests[0].body.boot_volume_size_gb).toBe(80);
	});

	it.each([false, true])('ignores stale image minimum and size/deletion drafts for existing-volume reuse (admin=%s)', async adminMode => {
		wizard.update(w => ({ ...w, bootVolumeSizeGb: 20, deleteBootVolumeOnTermination: true }));
		const { store, container } = await start(adminMode, 'volume');
		await enter();
		expect(store.selectedImage?.min_disk).toBe(80);
		expect(store.minBootVolumeSizeGb).toBe(1);
		expect(get(wizard).bootVolumeSizeGb).toBe(20);
		expect(container.querySelector('#boot-volume-size')).toBeNull();
		wizard.update(w => ({ ...w, bootVolumeSizeGb: NaN }));
		await tick();
		expect(store.bootVolumeSizeReady).toBe(true);
		expect(store.canNext).toBe(true);
		await fireEvent.click(footerAction(container));
		expect(get(wizard).step).toBe(6);
		expect(footerAction(container).disabled).toBe(false);
		await store.deploy();
		expect(requests).toHaveLength(1);
		expect(requests[0].body).toMatchObject({ boot_volume_id: 'volume-a' });
		for (const field of ['image_id', 'boot_volume_size_gb', 'delete_boot_volume_on_termination']) {
			expect(requests[0].body).not.toHaveProperty(field);
		}
		expect(store.volumes.find(volume => volume.id === 'volume-a')?.size).toBe(40);
		expect(get(wizard).deleteBootVolumeOnTermination).toBe(true);
		expect(get(wizard).bootVolumeSizeGb).toBeNaN();
	});
});

describe('Ordinary image minimum admission', () => {
	it('uses authoritative min_disk for a non-Windows image and rejects an undersized direct submission', async () => {
		const initialFetch = vi.mocked(fetch).getMockImplementation()!;
		vi.mocked(fetch).mockImplementation((input, init) =>
			new URL(String(input)).pathname === '/api/v1/images'
				? Promise.resolve(json([{ id: 'image-a', name: 'Generic image', status: 'active', min_disk: 80 }]))
				: initialFetch(input, init));
		wizard.update(w => ({ ...w, imageId: 'image-a', flavorId: 'flavor-a', keyName: 'my-key', step: 5 }));
		let store!: VmCreateStore;
		const { container } = render(Wrapper, { onStore: value => { store = value; } });
		await vi.waitFor(() => expect(get(wizard).bootVolumeSizeGb).toBe(80));
		await vi.waitFor(() => expect(store.flavors.length).toBe(1));
		expect(store.isWindowsBoot).toBe(false);
		await fireEvent.input(container.querySelector('#boot-volume-size')!, { target: { value: '79' } });
		expect(get(wizard).bootVolumeSizeGb).toBe(79);
		expect(store.canNext).toBe(false);
		await store.deploy();
		expect(requests).toHaveLength(0);
		await fireEvent.input(container.querySelector('#boot-volume-size')!, { target: { value: '80' } });
		expect(store.canNext).toBe(true);
		await store.deploy();
		expect(requests).toHaveLength(1);
		expect(requests[0].body).toMatchObject({ image_id: 'image-a', boot_volume_size_gb: 80, key_name: 'my-key' });
		expect(requests[0].body).not.toHaveProperty('admin_pass');
	});
});
