// @vitest-environment node
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const root = resolve(__dirname, '../../..');
const readSource = (path: string) => readFileSync(resolve(root, path), 'utf8');

describe('beta-gated feature surfaces', () => {
	it('marks hidden navigation entries with beta metadata', () => {
		const source = [
			'src/lib/components/Sidebar.svelte',
			'src/lib/components/AdminSidebar.svelte',
			'src/lib/config/nav.ts',
		].map(readSource).join('\n');

		for (const literal of [
			"beta: 'keyManager'",
			"beta: 'volumeBackups'",
			"beta: 'volumeSnapshots'",
			"beta: 'fileStorageSnapshots'",
			"beta: 'fileStorageShareNetworks'",
			"beta: 'fileStorageSecurityServices'",
			"beta: 'databaseBackups'",
		]) {
			expect(source).toContain(literal);
		}
	});

	it('keeps command palette navigation filtered by beta preferences', () => {
		const source = readSource('src/lib/components/CmdPalette.svelte');
		expect(source).toContain('allNavItems($isAdmin, paletteBetaFeatures)');
		expect(source).toContain('mockupAdminActive');
	});

	it('keeps direct routes guarded by beta feature state', () => {
		const source = [
			'src/routes/dashboard/secrets/+page.svelte',
			'src/routes/admin/secrets/+page.svelte',
			'src/routes/dashboard/volumes/backups/+page.svelte',
			'src/routes/dashboard/volumes/snapshots/+page.svelte',
			'src/routes/dashboard/file-storage/snapshots/+page.svelte',
			'src/routes/dashboard/file-storage/networks/+page.svelte',
			'src/routes/dashboard/file-storage/security-services/+page.svelte',
			'src/routes/dashboard/database/backups/+page.svelte',
		].map(readSource).join('\n');

		for (const literal of [
			'keyManagerEnabled',
			'volumeBackupsEnabled',
			'volumeSnapshotsEnabled',
			'fileStorageSnapshotsEnabled',
			'shareNetworksEnabled',
			'securityServicesEnabled',
			'databaseBackupsEnabled',
		]) {
			expect(source).toContain(literal);
		}
	});

	it('keeps inline controllers wired with beta option names', () => {
		const source = [
			'src/lib/stores/volumesController.svelte.ts',
			'src/lib/stores/volumeDetailController.svelte.ts',
			'src/routes/dashboard/volumes/+page.svelte',
			'src/lib/components/VolumeDetailPanel.svelte',
			'src/lib/stores/fileStorageWizardStore.svelte.ts',
			'src/lib/components/file-storage/wizard/FileStorageWizard.svelte',
			'src/lib/stores/dbCreateStore.svelte.ts',
			'src/lib/stores/dbInstanceDetailController.svelte.ts',
			'src/lib/stores/adminDatabaseInstanceDetailController.svelte.ts',
			'src/lib/components/database/DbCreatePanel.svelte',
			'src/lib/components/database/DbInstanceDetailPanel.svelte',
			'src/routes/admin/database-instances/[id]/+page.svelte',
		].map(readSource).join('\n');

		for (const literal of [
			'volumeBackupsEnabled',
			'volumeSnapshotsEnabled',
			'fileStorageShareNetworksEnabled',
			'databaseBackupsEnabled',
		]) {
			expect(source).toContain(literal);
		}
	});
});
