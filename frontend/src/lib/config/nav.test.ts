// @vitest-environment node
import { describe, expect, it } from 'vitest';
import { DEFAULT_BETA_FEATURES } from '$lib/stores/betaFeatures';
import { adminNavSections, allNavItems, isNavSectionActive } from './nav';

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

	it('groups administrator service workspaces without moving tenant Waygate', () => {
		const admin = allNavItems(true, DEFAULT_BETA_FEATURES);
		const services = admin.filter((item) => item.section === '서비스' && item.topLevel);
		expect(services.map((item) => item.href)).toEqual([
			'/admin/drover', '/admin/chat', '/admin/libraries', '/admin/waygate'
		]);
		expect(services.find((item) => item.href === '/admin/waygate')?.service).toBe('waygate');
		expect(allNavItems(false, DEFAULT_BETA_FEATURES).find((item) => item.href === '/dashboard/network/waygate')?.section).toBe('네트워크');
		expect(allNavItems(false, DEFAULT_BETA_FEATURES).find((item) => item.href === '/dashboard/network/waygate')?.service).toBe('waygate');
	});

	it('keeps service gates on both primary and secondary service links', () => {
		const byHref = new Map(allNavItems(true, DEFAULT_BETA_FEATURES).map((item) => [item.href, item]));
		for (const href of ['/admin/drover', '/admin/drover/templates']) {
			expect(byHref.get(href)?.service).toBe('k3s');
		}
		for (const href of ['/admin/chat', '/admin/chat/stats', '/admin/chat/quotas', '/admin/chat/models', '/admin/chat/tools']) {
			expect(byHref.get(href)?.service).toBe('chat');
		}
		expect(byHref.get('/admin/libraries')?.service).toBeNull();
		expect(byHref.get('/admin/waygate')?.service).toBe('waygate');
	});

	it('activates sections only for exact routes and slash descendants', () => {
		const services = adminNavSections.find((section) => section.label === '서비스')!;
		const monitoring = adminNavSections.find((section) => section.label === '모니터링')!;
		for (const href of ['/admin/drover', '/admin/drover/templates', '/admin/chat/stats', '/admin/chat/stats/daily', '/admin/libraries/123', '/admin/waygate']) {
			expect(isNavSectionActive(services, href)).toBe(true);
		}
		for (const href of ['/admin/droverish', '/admin/chatty', '/admin/libraries-old', '/admin/waygate-extra', '/admin/containers']) {
			expect(isNavSectionActive(services, href)).toBe(false);
		}
		expect(isNavSectionActive(monitoring, '/admin/monitoring/node')).toBe(true);
		expect(isNavSectionActive(monitoring, '/admin/monitoring-other')).toBe(false);
	});
});
