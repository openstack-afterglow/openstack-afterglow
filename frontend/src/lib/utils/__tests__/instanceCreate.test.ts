// @vitest-environment node
import { describe, expect, it } from 'vitest';

import {
	isGithubSshEligible,
	isSshAccessReady,
	isUbuntuImage,
	isWindowsImageMetadata,
	isValidGithubUsername,
	normalizeRequestedInstanceName,
	windowsPasswordAccount,
	windowsPasswordError,
	hasWindowsUserDataConflict,
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

	it('requires authoritative Windows method and account, never an image name', () => {
		const marked = { os_type: ' Windows ', windows_initial_password_method: 'nova-adminpass-configdrive', os_admin_user: 'GuestAdmin' };
		expect(windowsPasswordAccount(marked)).toBe('GuestAdmin');
		expect(windowsPasswordAccount({})).toBeNull();
		for (const metadata of [
			{ ...marked, os_type: 'linux' },
			{ ...marked, windows_initial_password_method: 'other' },
			{ ...marked, windows_initial_password_method: 'nova-adminpass-configdrive ' },
			{ ...marked, windows_initial_password_method: 'cloudbase-user-data' },
			{ ...marked, windows_initial_password_method: undefined },
			{ ...marked, os_admin_user: undefined },
			{ ...marked, os_admin_user: 123 },
			{ ...marked, os_admin_user: '' },
			{ ...marked, os_admin_user: '   ' },
			{ ...marked, os_admin_user: 'admin\n' },
		]) expect(windowsPasswordAccount(metadata)).toBeNull();
	});

	it('recognizes Windows independently of password method and account', () => {
		for (const metadata of [{ os_type: 'windows' }, { os_type: ' Windows ' }]) {
			expect(isWindowsImageMetadata(metadata)).toBe(true);
			expect(windowsPasswordAccount(metadata)).toBeNull();
		}
		for (const metadata of [undefined, null, {}, { os_type: 'linux' }, { os_type: 123 }]) {
			expect(isWindowsImageMetadata(metadata)).toBe(false);
		}
	});

	it.each(['short', 'x'.repeat(129), 'password\n', 'password\u0000', 'password\u007f', 'password\u0085'])('rejects an invalid password independently of confirmation', password => {
		expect(windowsPasswordError(password, password)).toBe('invalid');
	});

	it('preserves spaces and quotes, counts Unicode characters, and requires exact confirmation', () => {
		for (const password of [" 'secret' ", 'x'.repeat(8), 'x'.repeat(128), '😀'.repeat(128)]) {
			expect(windowsPasswordError(password, password)).toBeNull();
			expect(windowsPasswordError(password, password + 'x')).toBe('mismatch');
		}
		expect(windowsPasswordError(' password ', 'password')).toBe('mismatch');
	});

	it('blocks retained custom user-data and mount drafts including whitespace and incomplete mounts', () => {
		expect(hasWindowsUserDataConflict({ cloudInit: '', dataMounts: [] })).toBe(false);
		expect(hasWindowsUserDataConflict({ cloudInit: ' ', dataMounts: [] })).toBe(true);
		expect(hasWindowsUserDataConflict({ cloudInit: '', dataMounts: [{}] })).toBe(true);
	});
});
