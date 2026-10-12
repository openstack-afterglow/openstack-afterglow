import type { ImageDetail } from '$lib/types/adminImage';

// These are provider projections, never a merge of a PATCH body into the old image.
export function originalImage(id = 'image-a', owner = 'project-a'): ImageDetail {
	return {
		id, owner, name: 'Imported workstation', status: 'active', visibility: 'private',
		size: 1048576, virtual_size: 21474836480, min_disk: 20, min_ram: 2048,
		disk_format: 'qcow2', container_format: 'bare', checksum: 'before-checksum',
		created_at: '2026-10-01T08:00:00Z', updated_at: '2026-10-01T08:00:00Z',
		protected: false, tags: ['imported'], os_hash_algo: 'sha512', os_hash_value: 'before-hash',
		os_type: 'linux', os_distro: 'ubuntu', os_version: '22.04',
		os_admin_user: 'ExistingOperator', windows_initial_password_method: 'cloudbase-user-data',
		properties: {
			os_type: 'linux', os_distro: 'ubuntu', os_admin_user: 'ExistingOperator',
			windows_initial_password_method: 'cloudbase-user-data', img_config_drive: 'mandatory',
			hw_firmware_type: 'bios', hw_machine_type: 'pc', hw_tpm_version: '1.2',
			hw_tpm_model: 'tpm-tis', os_secure_boot: 'disabled', hw_qemu_guest_agent: 'no',
			license_channel: 'volume', support_ticket: 'KEEP-123', pipeline_revision: 'import-1',
		},
	};
}

export function authoritativeSavedImage(): ImageDetail {
	return {
		id: 'image-a', owner: 'project-a', name: 'Provider-normalized workstation',
		status: 'active', visibility: 'community', size: 2097152, virtual_size: 42949672960,
		min_disk: 40, min_ram: 4096, disk_format: 'raw', container_format: 'bare',
		checksum: 'after-checksum', created_at: '2026-10-01T08:00:00Z',
		updated_at: '2026-10-12T12:34:56Z', protected: true, tags: ['windows', 'provider-reviewed'],
		os_hash_algo: 'sha512', os_hash_value: 'after-hash', os_type: 'windows', os_distro: 'windows',
		os_version: '2022', os_admin_user: 'PlatformAdmin',
		windows_initial_password_method: 'nova-adminpass-configdrive',
		properties: {
			os_type: 'windows', os_distro: 'windows', os_admin_user: 'PlatformAdmin',
			windows_initial_password_method: 'nova-adminpass-configdrive', img_config_drive: 'mandatory',
			hw_firmware_type: 'bios', hw_machine_type: 'pc', hw_tpm_version: '1.2',
			hw_tpm_model: 'tpm-tis', os_secure_boot: 'disabled', hw_qemu_guest_agent: 'no',
			license_channel: 'volume', support_ticket: 'KEEP-123', pipeline_revision: 'server-42',
		},
	};
}

// Independently authored GET after remount. A properties-only local restore cannot
// make either this projection or its top-level account/method appear in the consumer.
export function persistedImage(): ImageDetail {
	return {
		id: 'image-a', owner: 'project-a', name: 'Provider-normalized workstation',
		status: 'active', visibility: 'community', size: 2097152, virtual_size: 42949672960,
		min_disk: 40, min_ram: 4096, disk_format: 'raw', container_format: 'bare',
		checksum: 'after-checksum', created_at: '2026-10-01T08:00:00Z',
		updated_at: '2026-10-12T12:34:56Z', protected: true, tags: ['windows', 'provider-reviewed'],
		os_hash_algo: 'sha512', os_hash_value: 'after-hash', os_type: 'windows', os_distro: 'windows',
		os_version: '2022', os_admin_user: 'PlatformAdmin',
		windows_initial_password_method: 'nova-adminpass-configdrive',
		properties: {
			os_type: 'windows', os_distro: 'windows', os_admin_user: 'PlatformAdmin',
			windows_initial_password_method: 'nova-adminpass-configdrive', img_config_drive: 'mandatory',
			hw_firmware_type: 'bios', hw_machine_type: 'pc', hw_tpm_version: '1.2',
			hw_tpm_model: 'tpm-tis', os_secure_boot: 'disabled', hw_qemu_guest_agent: 'no',
			license_channel: 'volume', support_ticket: 'KEEP-123', pipeline_revision: 'server-42',
		},
	};
}

export const requiredDifferences = {
	os_type: 'windows', os_distro: 'windows', os_admin_user: 'PlatformAdmin',
	windows_initial_password_method: 'nova-adminpass-configdrive',
};

export const win11Differences = {
	hw_firmware_type: 'uefi', hw_machine_type: 'q35', hw_tpm_version: '2.0',
	hw_tpm_model: 'tpm-crb', os_secure_boot: 'required',
};
