import { auth } from '$lib/stores/auth';
import { siteConfig } from '$lib/config/site';
import { openWizard, resetWizard, wizard } from '$lib/stores/wizard';

export const nativeWindowsMetadata = {
	os_type: ' Windows ',
	windows_initial_password_method: 'nova-adminpass-configdrive',
	os_admin_user: 'GuestAdmin',
};

export function wizardResource(path: string): unknown | undefined {
	if (path === '/api/v1/images') return [
		{ id: 'image-a', name: 'Ubuntu 24.04', status: 'active', os_distro: 'ubuntu' },
		{ id: 'windows-native', name: 'Native guest', status: 'active', ...nativeWindowsMetadata },
		{ id: 'windows-unsupported', name: 'Legacy guest', status: 'active', ...nativeWindowsMetadata, windows_initial_password_method: 'cloudbase-user-data' },
	];
	if (path === '/api/v1/volumes' || path.includes('/volumes-for-project')) return [
		{ id: 'volume-a', name: 'Boot disk', status: 'available', size: 40, bootable: true, attachments: [] },
		{ id: 'windows-native', name: 'Native disk', status: 'available', size: 40, bootable: true, attachments: [], volume_image_metadata: nativeWindowsMetadata },
		{ id: 'windows-unsupported', name: 'Legacy disk', status: 'available', size: 40, bootable: true, attachments: [], volume_image_metadata: { ...nativeWindowsMetadata, windows_initial_password_method: 'cloudbase-user-data' } },
	];
	if (path.startsWith('/api/v1/flavors') || path.includes('/flavors-for-project')) return [{
		id: 'flavor-a', name: 'gpu.4c_8g', vcpus: 4, ram: 8192, disk: 40,
		extra_specs: { 'pci_passthrough:alias': 'gpu-a:1,audio:1' },
		eligibility: {
			selectable: true, blockers: [],
			requirements: { instances: 1, cores: 4, ram_mb: 8192, gpus: {} },
			remaining: { instances: 5, cores: 16, ram_mb: 32768, gpus: {} },
			capacity: { status: 'available', checked_at: '2026-10-12T00:00:00+00:00', candidate_hosts: 1, cpu_resource_class: 'VCPU', remaining_vcpus: 16, remaining_ram_mb: 32768 },
		},
	}];
	if (path === '/api/v1/keypairs') return [{ name: 'test-keypair' }, { name: 'project-key' }];
	if (path === '/api/v1/file-storage') return [{ id: 'storage-a', name: 'project-data', status: 'available', share_proto: 'NFS' }];
	if (path === '/api/v1/networks/default') return { network_id: null };
	if (path === '/api/v1/admin/projects/names') return [{ id: 'target-a', name: 'Target' }];
	if (path === '/api/v1/dashboard/quotas' || path.startsWith('/api/v1/admin/quotas/')) return {};
	if (path === '/api/v1/networks' || path === '/api/v1/security-groups' || path.includes('/networks-for-project') || path.includes('/security-groups-for-project')) return [];
	return undefined;
}

export function prepareWizardConsumer(step: number) {
	resetWizard();
	openWizard();
	auth.set({ token: 'test-token', refreshToken: null, accessExpiresAt: null, userId: 'user-a', username: 'user-a', projectId: 'project-a', projectName: 'Project A', availableProjects: [], roles: [], isSystemAdmin: false, federated: false });
	siteConfig.update(value => ({ ...value, services: { ...value.services, manila: true } }));
	wizard.update(w => ({ ...w, step, imageId: 'image-a', imageName: 'Ubuntu 24.04', flavorId: 'flavor-a', flavorName: 'gpu.4c_8g' }));
}
