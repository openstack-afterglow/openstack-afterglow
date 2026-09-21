import { describe, expect, it } from 'vitest';

import {
	isGithubSshEligible,
	isSshAccessReady,
	isUbuntuImage,
	isValidGithubUsername,
	normalizeRequestedInstanceName,
} from '../instanceCreate';

describe('VM creation helpers', () => {
	it('normalizes whitespace runs in the submitted instance name', () => {
		expect(normalizeRequestedInstanceName('  Open Crew\tHub  ')).toBe('Open-Crew-Hub');
		expect(normalizeRequestedInstanceName('   ')).toBeNull();
	});

	it('recognizes Ubuntu from distro metadata without a version allowlist', () => {
		expect(isUbuntuImage({ name: 'custom-image', os_distro: 'ubuntu' })).toBe(true);
		expect(isUbuntuImage({ name: 'Ubuntu 26.04 preview' })).toBe(true);
		expect(isUbuntuImage({ name: 'Rocky Linux 9', os_distro: 'rocky' })).toBe(false);
	});

	it('offers GitHub SSH only for direct Ubuntu images', () => {
		expect(isGithubSshEligible({ adminMode: false, bootSource: 'image', selectedImageIsUbuntu: true })).toBe(true);
		expect(isGithubSshEligible({ adminMode: false, bootSource: 'volume', selectedImageIsUbuntu: true })).toBe(false);
		expect(isGithubSshEligible({ adminMode: true, bootSource: 'image', selectedImageIsUbuntu: true })).toBe(false);
	});

	it('validates GitHub usernames and requires a verified profile for GitHub SSH', () => {
		expect(isValidGithubUsername('octo-cat')).toBe(true);
		expect(isValidGithubUsername('octo--cat')).toBe(false);
		expect(isValidGithubUsername('octo cat')).toBe(false);

		const verified = { login: 'OctoCat', has_public_keys: true };
		expect(isSshAccessReady({ adminMode: false, sshAccessMode: 'github', keyName: null, githubUsername: 'octocat', githubProfile: verified })).toBe(true);
		expect(isSshAccessReady({ adminMode: false, sshAccessMode: 'github', keyName: null, githubUsername: 'octocat' })).toBe(false);
		expect(isSshAccessReady({ adminMode: false, sshAccessMode: 'github', keyName: null, githubUsername: 'someone-else', githubProfile: verified })).toBe(false);
		expect(isSshAccessReady({ adminMode: false, sshAccessMode: 'github', keyName: null, githubUsername: 'octocat', githubProfile: { login: 'OctoCat', has_public_keys: false } })).toBe(false);
		expect(isSshAccessReady({ adminMode: false, sshAccessMode: 'keypair', keyName: 'kp-1', githubUsername: '', githubProfile: null })).toBe(true);
	});
});
