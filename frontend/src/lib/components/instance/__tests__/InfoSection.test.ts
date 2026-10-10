import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { cleanup, render, screen } from '@testing-library/svelte';
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

function renderInfoSection(props?: { showHost?: boolean }, overrides: Partial<InstanceDetailController> = {}) {
	mockControllerRef.current = {
		instance: sampleInstance,
		formatDate: (d: string) => d,
		ownerDisplay: null,
		fixedIpsList: [],
		floatingIpsList: [],
		...overrides,
	} as unknown as InstanceDetailController;

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
