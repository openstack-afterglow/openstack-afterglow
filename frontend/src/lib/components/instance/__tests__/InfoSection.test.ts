import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import type { Instance } from '$lib/types/compute';
import type { InstanceDetailController } from '$lib/stores/instanceDetailController.svelte';

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
