import { render, screen } from '@testing-library/svelte';
import { describe, expect, it } from 'vitest';

import VolumeSummaryCards from '../VolumeSummaryCards.svelte';
import type { Snapshot, Volume, VolumeBackup } from '$lib/types/volume';

const volumes: Volume[] = [
	{
		id: 'vol-1',
		name: 'volume-1',
		status: 'available',
		size: 10,
		volume_type: null,
		attachments: [],
	},
];

const snapshots: Snapshot[] = [
	{
		id: 'snap-1',
		name: 'snapshot-1',
		status: 'available',
		volume_id: 'vol-1',
		size: 10,
		description: '',
		created_at: new Date().toISOString(),
	},
];

const quotas = {
	storage: {
		volumes: { limit: 5, in_use: 1 },
		gigabytes: { limit: 100, in_use: 10 },
	},
};

describe('VolumeSummaryCards', () => {
	it('renders snapshot summary by default', () => {
		render(VolumeSummaryCards, { volumes, snapshots, quotas });

		expect(screen.getByText('스냅샷')).toBeTruthy();
	});

	it('hides snapshot summary when snapshot beta is off', () => {
		render(VolumeSummaryCards, {
			volumes,
			snapshots,
			quotas,
			showSnapshots: false,
		});

		expect(screen.queryByText('스냅샷')).toBeNull();
	});

	it('keeps unavailable snapshot counts and quotas distinct from measured zero', () => {
		render(VolumeSummaryCards, { volumes, snapshots: [], quotas: null, snapshotsKnown: false });
		expect(screen.getAllByText('—')).toHaveLength(3);
		expect(screen.getByText('10 GiB')).toBeTruthy();
	});

	it('sums snapshot and backup capacity and marks an unreadable backup inventory unknown', () => {
		const backups = [
			{ id: 'b1', name: 'b1', description: '', volume_id: 'vol-1', status: 'available', size: 10, created_at: null, is_incremental: false, has_dependent_backups: false },
			{ id: 'b2', name: 'b2', description: '', volume_id: 'vol-1', status: 'available', size: 25, created_at: null, is_incremental: true, has_dependent_backups: false },
		] as unknown as VolumeBackup[];
		const view = render(VolumeSummaryCards, { volumes, snapshots, quotas, backups });
		// volume 10 + snapshot 10 + quota 100 are distinct from the 35 GiB backup total.
		expect(screen.getByText('35 GiB')).toBeTruthy();
		expect(screen.getAllByText('10 GiB')).toHaveLength(2);
		view.unmount();
		render(VolumeSummaryCards, { volumes, snapshots, quotas, backups: [], backupsKnown: false });
		expect(screen.getAllByText('—')).toHaveLength(2);
	});

	it('hides backup figures when the page has no backup inventory', () => {
		render(VolumeSummaryCards, { volumes, snapshots, quotas });
		expect(screen.queryByText('백업')).toBeNull();
	});
});
