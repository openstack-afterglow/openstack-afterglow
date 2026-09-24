// @vitest-environment node
import { describe, expect, it } from 'vitest';
import { DEFAULT_BETA_FEATURES } from '$lib/stores/betaFeatures';
import { allNavItems } from './nav';

describe('allNavItems service inheritance', () => {
	it('preserves section service gates for flattened user routes', () => {
		const items = allNavItems(false, DEFAULT_BETA_FEATURES);
		const byHref = new Map(items.map(item => [item.href, item]));

		expect(byHref.get('/dashboard/file-storage')?.service).toBe('manila');
		expect(byHref.get('/dashboard/database/instances')?.service).toBe('trove');
		expect(byHref.get('/dashboard/object-storage/buckets')?.service).toBe('swift');
		expect(byHref.get('/dashboard/compute/instances')?.service).toBeNull();
	});

	it('includes volume backups but not other disabled beta routes by default', () => {
		const hrefs = allNavItems(false, DEFAULT_BETA_FEATURES).map(item => item.href);

		expect(hrefs).toContain('/dashboard/volumes/backups');
		expect(hrefs).not.toContain('/dashboard/volumes/snapshots');
		expect(hrefs).not.toContain('/dashboard/database/backups');
	});

	it('keeps explicit item service gates for admin routes', () => {
		const items = allNavItems(true, DEFAULT_BETA_FEATURES);
		const fileStorage = items.find(item => item.href === '/admin/file-storage');

		expect(fileStorage?.service).toBe('manila');
	});
});
