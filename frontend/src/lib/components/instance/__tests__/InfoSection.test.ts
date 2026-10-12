import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { cleanup, render, screen } from '@testing-library/svelte';
import { tick } from 'svelte';
import { fromStore, writable } from 'svelte/store';
import type { Writable } from 'svelte/store';
import type { Instance } from '$lib/types/compute';
import type { InstanceDetailController } from '$lib/stores/instanceDetailController.svelte';
import { initLocale } from '$lib/i18n/runtime.svelte';

const { mockControllerRef } = vi.hoisted(() => ({
	mockControllerRef: { current: undefined as unknown },
}));

vi.mock('$lib/stores/instanceDetailController.svelte', () => ({
	useInstanceDetailController: () => mockControllerRef.current,
}));

import InfoSection from '../InfoSection.svelte';

const sampleInstance = {
	id: 'inst-12345',
	name: 'test-vm',
	status: 'ACTIVE',
	created_at: '2026-08-31T00:00:00Z',
	image_name: 'Ubuntu 24.04',
	flavor_name: 'm1.small',
	key_name: 'my-keypair',
	host: 'compute-node-01',
} as Instance;
let controllerState: Writable<InstanceDetailController>;

function renderInfoSection(props?: { showHost?: boolean }, overrides: Partial<InstanceDetailController> = {}) {
	controllerState = writable({
		instance: sampleInstance,
		formatDate: (d: string) => d,
		ownerDisplay: null,
		fixedIpsList: [],
		floatingIpsList: [],
		...overrides,
	} as unknown as InstanceDetailController);
	const state = fromStore(controllerState);
	mockControllerRef.current = new Proxy(state.current, {
		get: (_target, key) => state.current[key as keyof InstanceDetailController],
	});

	return render(InfoSection, props);
}

beforeEach(() => {
	vi.clearAllMocks();
	initLocale('ko');
});

afterEach(() => {
	cleanup();
	initLocale('ko');
});

describe('InfoSection host visibility', () => {
	it('does not render host label or host value by default (showHost=false)', () => {
		renderInfoSection();
		expect(screen.queryByText('호스트')).toBeNull();
		expect(screen.queryByText('compute-node-01')).toBeNull();
	});

	it('renders host label and host value when showHost is true and instance host exists', () => {
		renderInfoSection({ showHost: true });
		expect(screen.getByText('호스트')).not.toBeNull();
		expect(screen.getByText('compute-node-01')).not.toBeNull();
	});

	it('does not render host label or host value when showHost is true but instance host is null', () => {
		renderInfoSection({ showHost: true }, { instance: { ...sampleInstance, host: null } as unknown as Instance });
		expect(screen.queryByText('호스트')).toBeNull();
		expect(screen.queryByText('compute-node-01')).toBeNull();
	});
});

describe('InfoSection SSH access', () => {
	it.each([
		['en', 'Key pair'],
		['ko', '키페어'],
		['ja', 'キーペア'],
		['zh-CN', '密钥对'],
	] as const)('renders GitHub SSH and the case-preserved API login in %s', (locale, keyPairLabel) => {
		initLocale(locale);
		renderInfoSection(undefined, {
			instance: { ...sampleInstance, ssh_access_mode: 'github', github_login: 'OctoCat' },
		});

		expect(screen.getByText('GitHub SSH').nextElementSibling?.textContent).toBe('@OctoCat');
		expect(screen.queryByText('@octocat')).toBeNull();
		expect(screen.queryByText(keyPairLabel)).toBeNull();
		expect(screen.queryByText('my-keypair')).toBeNull();
	});

	it.each([
		{ name: 'older instances without SSH access metadata', fields: {} },
		{ name: 'keypair instances with null GitHub fields', fields: { ssh_access_mode: null, github_login: null } },
		{ name: 'a login without a mode', fields: { github_login: 'OctoCat' } },
		{ name: 'a login with a null mode', fields: { ssh_access_mode: null, github_login: 'OctoCat' } },
		{ name: 'GitHub mode without a login', fields: { ssh_access_mode: 'github' } },
		{ name: 'GitHub mode with a null login', fields: { ssh_access_mode: 'github', github_login: null } },
		{ name: 'GitHub mode with an empty login', fields: { ssh_access_mode: 'github', github_login: '' } },
	] satisfies { name: string; fields: Partial<Instance> }[])('retains the keypair for $name', ({ fields }) => {
		renderInfoSection(undefined, { instance: { ...sampleInstance, ...fields } });

		expect(screen.getByText('키페어').nextElementSibling?.textContent).toBe('my-keypair');
		expect(screen.queryByText('GitHub SSH')).toBeNull();
		expect(screen.queryByText('@OctoCat')).toBeNull();
	});

	it.each([
		{ name: 'absent SSH metadata and absent keypair', fields: { key_name: undefined } },
		{ name: 'null SSH metadata and null keypair', fields: { key_name: null, ssh_access_mode: null, github_login: null } },
		{ name: 'login-only metadata and null keypair', fields: { key_name: null, github_login: 'OctoCat' } },
		{ name: 'GitHub mode without a login or keypair', fields: { key_name: null, ssh_access_mode: 'github' } },
	] satisfies { name: string; fields: Partial<Instance> }[])('retains the placeholder for $name', ({ fields }) => {
		renderInfoSection(undefined, { instance: { ...sampleInstance, ...fields } });

		expect(screen.getByText('키페어').nextElementSibling?.textContent).toBe('-');
		expect(screen.queryByText('GitHub SSH')).toBeNull();
		expect(screen.queryByText('@OctoCat')).toBeNull();
	});
});

describe('InfoSection Windows OS contract', () => {
	it.each([
		{ status: 'ACTIVE', os_type: 'windows', canChangePassword: false, image_name: 'Ubuntu 24.04', ssh_access_mode: null },
		{ status: 'ACTIVE', os_type: ' WINDOWS ', canChangePassword: true, image_name: 'Windows Server', ssh_access_mode: 'github' },
		{ status: 'SHUTOFF', os_type: '\tWiNdOwS\n', canChangePassword: false, image_name: null, ssh_access_mode: 'github' },
		{ status: 'SHUTOFF', os_type: 'windows', canChangePassword: true, image_name: null, ssh_access_mode: null },
	] as const)('hides both SSH identities for authoritative Windows metadata %#', fields => {
		renderInfoSection(undefined, {
			instance: { ...sampleInstance, name: 'linux-vm', status: fields.status, os_type: fields.os_type, image_name: fields.image_name, image_id: null, ssh_access_mode: fields.ssh_access_mode, github_login: 'OctoCat' },
			canChangePassword: fields.canChangePassword,
			passwordPrecheckLoading: true,
		});
		expect(screen.queryByText('키페어')).toBeNull();
		expect(screen.queryByText('my-keypair')).toBeNull();
		expect(screen.queryByText('GitHub SSH')).toBeNull();
		expect(screen.queryByText('@OctoCat')).toBeNull();
		if (fields.image_name === null) expect(screen.getByText('볼륨에서 부팅')).toBeTruthy();
	});

	it.each(['linux', ' LINUX ', null, undefined, ''])('does not infer Windows from instance/image names when os_type is %s', os_type => {
		renderInfoSection(undefined, {
			instance: { ...sampleInstance, name: 'Windows Server', image_name: 'Windows Server 2025', os_type, status: 'SHUTOFF' },
			canChangePassword: false,
			passwordPrecheckLoading: true,
		});
		expect(screen.getByText('키페어').nextElementSibling?.textContent).toBe('my-keypair');
	});

	it('updates SSH presentation from ACTIVE Linux to volume-backed SHUTOFF Windows and back for a reader', async () => {
		renderInfoSection(undefined, {
			instance: { ...sampleInstance, os_type: 'linux', ssh_access_mode: 'github', github_login: 'OctoCat' },
			canChangePassword: false,
		});
		expect(screen.getByText('GitHub SSH').nextElementSibling?.textContent).toBe('@OctoCat');
		controllerState.update(s => ({ ...s, instance: { ...s.instance!, os_type: ' Windows ', status: 'SHUTOFF', image_id: null, image_name: null } }));
		await tick();
		expect(screen.queryByText('GitHub SSH')).toBeNull();
		expect(screen.queryByText('키페어')).toBeNull();
		expect(screen.getByText('볼륨에서 부팅')).toBeTruthy();
		controllerState.update(s => ({ ...s, instance: { ...s.instance!, os_type: 'linux' } }));
		await tick();
		expect(screen.getByText('GitHub SSH').nextElementSibling?.textContent).toBe('@OctoCat');
		controllerState.update(s => ({ ...s, instance: { ...s.instance!, ssh_access_mode: null, github_login: null } }));
		await tick();
		expect(screen.getByText('키페어').nextElementSibling?.textContent).toBe('my-keypair');
	});
});
