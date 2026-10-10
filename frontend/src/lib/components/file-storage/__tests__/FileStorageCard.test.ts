import { render, screen } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import FileStorageCard from '../FileStorageCard.svelte';
import type { FileStorage } from '$lib/types/fileStorage';
import FileStorageInfoCard from '$lib/components/dashboard/file-storage/[id]/FileStorageInfoCard.svelte';

const share: FileStorage = {
	id: 'share-1', name: 'data-share', status: 'available', size: 10, share_proto: 'NFS',
	export_locations: [], metadata: {}, project_id: 'project-a', created_at: null,
	is_public: false, library_name: null, library_version: null, built_at: null,
	progress: null, user_id: null, user_name: null, access_rules_status: null,
	host: null, availability_zone: null, share_type_name: null, share_network_id: null,
	export_location_details: [],
};

function renderCard(fs = share, quotaLimit = 100) {
	return render(FileStorageCard, {
		fs, quotaLimit, copiedExport: null, deleting: null,
		onOpenDetail: vi.fn(), onCopyExport: vi.fn(), onDelete: vi.fn(), onToggleSelect: vi.fn(),
	});
}

describe('file storage card progress', () => {
	it.each([0, -1, Number.NaN, Number.POSITIVE_INFINITY])('does not claim a quota percentage for unknown or unlimited quota %s', (quotaLimit) => {
		renderCard(share, quotaLimit);
		expect(screen.queryByRole('progressbar')).toBeNull();
		expect(screen.getByText('10 GB')).toBeTruthy();
	});

	it.each([null, 'backend initializing'])('shows real creation without inventing a measured percentage for %s', (progress) => {
		renderCard({ ...share, status: 'creating', progress }, 0);
		const track = screen.getByRole('progressbar');
		expect(track.getAttribute('aria-valuenow')).toBeNull();
		expect(track.getAttribute('aria-busy')).toBe('true');
		if (progress !== null) expect(track.getAttribute('aria-valuetext')).toBe(progress);
	});

});


describe('file storage route progress', () => {
	it.each(['creating', 'extending'])('shows indeterminate %s work in the full-page information card', (status) => {
		render(FileStorageInfoCard, { fileStorage: { ...share, status } });
		const track = screen.getByRole('progressbar');
		expect(track.getAttribute('aria-valuenow')).toBeNull();
		expect(track.getAttribute('aria-busy')).toBe('true');
	});
});