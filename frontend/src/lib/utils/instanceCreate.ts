export function normalizeRequestedInstanceName(value: string | null | undefined): string | null {
	const normalized = (value ?? '').trim().replace(/[^\S\r\n]+/g, '-');
	return normalized || null;
}

export function normalizeGithubUsername(value: string | null | undefined): string {
	return (value ?? '').trim();
}

const GITHUB_USERNAME_RE = /^(?!-)(?!.*--)[A-Za-z0-9-]{1,39}(?<!-)$/;

export function isValidGithubUsername(value: string | null | undefined): boolean {
	return GITHUB_USERNAME_RE.test(normalizeGithubUsername(value));
}

export function isUbuntuImage(
	image: Pick<{ name: string; os_distro?: string | null; properties?: Record<string, unknown> | null }, 'name' | 'os_distro' | 'properties'> | null | undefined,
	fallbackName?: string | null,
): boolean {
	if (!image) return false;
	const props = image.properties ?? {};
	const distro = String(image.os_distro ?? props.os_distro ?? '').trim().toLowerCase();
	if (distro === 'ubuntu') return true;
	return /ubuntu/i.test(image.name ?? fallbackName ?? '');
}

export function isGithubSshEligible(input: {
	adminMode: boolean;
	bootSource: 'image' | 'volume';
	selectedImageIsUbuntu: boolean;
}): boolean {
	return !input.adminMode && input.bootSource === 'image' && input.selectedImageIsUbuntu;
}

export function isSshAccessReady(input: {
	adminMode: boolean;
	sshAccessMode: 'keypair' | 'github';
	keyName: string | null;
	githubUsername: string;
	githubProfile?: { login: string; has_public_keys: boolean } | null;
}): boolean {
	if (input.adminMode) return true;
	if (input.sshAccessMode !== 'github') return Boolean(input.keyName);
	const profile = input.githubProfile;
	return isValidGithubUsername(input.githubUsername)
		&& profile?.login.toLowerCase() === normalizeGithubUsername(input.githubUsername).toLowerCase()
		&& profile.has_public_keys;
}

/** Windows is determined by provider metadata, never the display name. */
export function isWindowsImageMetadata(metadata: { os_type?: unknown } | null | undefined): boolean {
	return typeof metadata?.os_type === 'string' && metadata.os_type.trim().toLowerCase() === 'windows';
}

/** Only the native Nova adminPass/config-drive method enables password creation. */
export function windowsPasswordAccount(metadata: {
	os_type?: unknown;
	windows_initial_password_method?: unknown;
	os_admin_user?: unknown;
} | null | undefined): string | null {
	if (!isWindowsImageMetadata(metadata)
		|| metadata?.windows_initial_password_method !== 'nova-adminpass-configdrive') return null;
	const account = metadata?.os_admin_user;
	return typeof account === 'string' && account.trim() && !/[\u0000-\u001f\u007f-\u009f]/u.test(account)
		? account : null;
}

export function windowsPasswordError(password: string, confirmation: string): 'invalid' | 'mismatch' | null {
	let length = 0;
	for (let index = 0; index < password.length; index += password.codePointAt(index)! > 0xffff ? 2 : 1) length += 1;
	if (length < 8 || length > 128 || /[\u0000-\u001f\u007f-\u009f]/u.test(password)) return 'invalid';
	return password === confirmation ? null : 'mismatch';
}

export function hasWindowsUserDataConflict(input: { cloudInit: string; dataMounts: unknown[] }): boolean {
	return input.cloudInit.length > 0 || input.dataMounts.length > 0;
}
