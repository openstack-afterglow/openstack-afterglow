import { render, screen } from '@testing-library/svelte';
import { describe, expect, it } from 'vitest';

import VolumeSummaryCards from '../VolumeSummaryCards.svelte';
import type { Snapshot, Volume } from '$lib/types/volume';

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
		expect(screen.getAllByText('—')).toHaveLength(2);
		expect(screen.getByText('10 GiB')).toBeTruthy();
	});
});
