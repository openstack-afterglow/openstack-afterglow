import { render, screen, within } from '@testing-library/svelte';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { t } from '$lib/i18n/ns/instance';
import InstanceHeader from '../InstanceHeader.svelte';

const { controller } = vi.hoisted(() => {
	const migrationStatus = {
		server_id: 'vm-1',
		error: 'Guest does not have a console available.',
		migration: {
			id: '953', status: 'error', type: 'live-migration', source: 'dms-compute12', dest: 'dms-compute6',
			created_at: '2026-11-12T09:19:25Z', updated_at: '2026-11-12T09:20:05Z',
		},
	};
	return {
		controller: {
			instance: {
				id: 'vm-1', name: 'librechat', status: 'ERROR',
				fault: { message: migrationStatus.error, created: '2026-11-18T13:29:41Z' },
			},
			migrationStatus,
		},
	};
});

vi.mock('$lib/stores/instanceDetailController.svelte', () => ({ useInstanceDetailController: () => controller }));
vi.mock('$lib/utils/mobileViewport', () => ({ mobileViewport: { current: false } }));

function mount(adminProjectId: string | null = 'project') {
	return render(InstanceHeader, {
		adminProjectId, canMutate: true,
		onOpenMigrateModal: vi.fn(), onOpenPasswordModal: vi.fn(), onOpenResizeModal: vi.fn(), onOpenEvacuateModal: vi.fn(),
	});
}

describe('instance recovery header', () => {
	beforeEach(() => { controller.migrationStatus.server_id = 'vm-1'; });

	it('separates the current fault and the failed migration by record and timestamp', () => {
		mount();
		const [fault, migration] = screen.getAllByRole('alert');
		expect(within(fault).getByText(t('header.latestFault'))).toBeTruthy();
		expect(within(migration).getByText(t('header.migrationFailed'))).toBeTruthy();
		expect(within(fault).getByText(controller.instance.fault.message)).toBeTruthy();
		expect(fault.querySelector('time')?.dateTime).toBe('2026-11-18T13:29:41Z');
		expect(within(migration).getByText('live-migration · dms-compute12 → dms-compute6')).toBeTruthy();
		expect(migration.querySelector('time')?.dateTime).toBe('2026-11-12T09:20:05Z');
		expect(within(migration).getByText(t('header.liveMigrationLogs'))).toBeTruthy();
		expect(within(migration).queryByText(controller.instance.fault.message)).toBeNull();
		expect(screen.getByRole('button', { name: t('header.recoveryAnalysis') })).toBeTruthy();
	});

	it('does not interpret a Nova fault or another server’s migration as this server’s failure', () => {
		controller.migrationStatus.server_id = 'vm-other';
		mount();
		expect(screen.getByText(t('header.latestFault'))).toBeTruthy();
		expect(screen.queryByText(t('header.migrationFailed'))).toBeNull();
	});

	it('hides admin evidence and recovery actions outside admin mode', () => {
		mount(null);
		expect(screen.queryByText(t('header.latestFault'))).toBeNull();
		expect(screen.queryByText(t('header.migrationFailed'))).toBeNull();
		expect(screen.queryByRole('button', { name: t('header.recoveryAnalysis') })).toBeNull();
	});
});
