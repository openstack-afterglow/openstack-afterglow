import { beforeEach, vi } from 'vitest';
import type { Writable } from 'svelte/store';
import type { PermissionState } from '$lib/stores/servicePermissions';
import { authReady, projectSwitching } from '$lib/stores/auth';

vi.mock('$lib/stores/servicePermissions', async () => {
	// The hoisted mock factory runs before static imports are initialized.
	const { writable } = await import('svelte/store');
	return {
		serviceCapabilities: writable<(leaf: string) => boolean>(() => false),
		serviceDenials: writable<(leaf: string) => boolean>(() => false),
		projectPermissions: writable({ permissions: null, loading: false, error: '' })
	};
});
import { serviceCapabilities, serviceDenials, projectPermissions } from '$lib/stores/servicePermissions';

const leaves = ['inventory_reader', 'history_reader', 'chat_user', 'images_user', 'audio_user', 'tools_user', 'assets_editor', 'agents_editor', 'mcp_editor', 'keys_editor', 'history_editor', 'resources_admin'].map((leaf) => `lumen-${leaf}`);
export function grantLumen(...grants: string[]) {
	const allowed = new Set(grants);
	(serviceCapabilities as Writable<(leaf: string) => boolean>).set((leaf) => allowed.has(leaf));
	(serviceDenials as Writable<(leaf: string) => boolean>).set((leaf) => !allowed.has(leaf));
	(projectPermissions as Writable<PermissionState>).set({ permissions: null, loading: false, error: '' });
}
export function pendingLumen(error = '') {
	(serviceCapabilities as Writable<(leaf: string) => boolean>).set(() => false);
	(serviceDenials as Writable<(leaf: string) => boolean>).set(() => false);
	(projectPermissions as Writable<PermissionState>).set({ permissions: null, loading: !error, error });
}
beforeEach(() => {
	authReady.set(true);
	projectSwitching.set(false);
	grantLumen(...leaves);
});
