import type { ImageDetail } from '$lib/types/adminImage';
import { windowsPasswordAccount } from '$lib/utils/instanceCreate';

export interface WindowsSetupDraft {
	account: string;
	win11: boolean;
	qga: boolean;
}

export interface WindowsSetupChange {
	key: string;
	current: string | undefined;
	proposed: string;
}

/** Explicit properties win; os_distro's display projection may be name-inferred, not a saved flag. */
export function windowsSetupProperties(image: ImageDetail): Record<string, string> {
	const properties = { ...image.properties };
	for (const key of ['os_type', 'os_admin_user', 'windows_initial_password_method'] as const) {
		const value = image[key];
		if (!(key in properties) && typeof value === 'string') properties[key] = value;
	}
	return properties;
}

export function isWindowsSetupAccountValid(account: string): boolean {
	return windowsPasswordAccount({
		os_type: 'windows',
		windows_initial_password_method: 'nova-adminpass-configdrive',
		os_admin_user: account,
	}) !== null;
}

/** This classifies metadata only, never guest, service, or production readiness. */
export function windowsSetupStatus(properties: Record<string, string>): 'native' | 'legacy' | 'unconfigured' {
	if (properties.windows_initial_password_method === 'cloudbase-user-data') return 'legacy';
	return windowsPasswordAccount(properties) !== null ? 'native' : 'unconfigured';
}

/** Unselected optional features and unrelated properties are deliberately absent from the patch. */
export function windowsSetupChanges(properties: Record<string, string>, draft: WindowsSetupDraft): WindowsSetupChange[] {
	const proposed: Record<string, string> = {
		os_type: 'windows',
		os_distro: 'windows',
		os_admin_user: draft.account,
		windows_initial_password_method: 'nova-adminpass-configdrive',
		img_config_drive: 'mandatory',
	};
	if (draft.win11) Object.assign(proposed, {
		hw_firmware_type: 'uefi',
		hw_machine_type: 'q35',
		hw_tpm_version: '2.0',
		hw_tpm_model: 'tpm-crb',
		os_secure_boot: 'required',
	});
	if (draft.qga) proposed.hw_qemu_guest_agent = 'yes';
	return Object.entries(proposed)
		.filter(([key, value]) => properties[key] !== value)
		.map(([key, value]) => ({ key, current: properties[key], proposed: value }));
}
