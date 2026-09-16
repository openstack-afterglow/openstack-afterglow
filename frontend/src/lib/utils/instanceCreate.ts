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
}): boolean {
	if (input.adminMode) return true;
	return input.sshAccessMode === 'github'
		? isValidGithubUsername(input.githubUsername)
		: Boolean(input.keyName);
}
