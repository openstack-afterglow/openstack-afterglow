import { describe, expect, it, beforeEach } from 'vitest';
import { ApiError } from '$lib/api/errors';
import type { AnnouncementAdmin } from '$lib/types/announcements';
import { mockAdminAnnouncements } from './adminAnnouncements';
import { resetMockupState } from './state';

const BASE = '/api/v1/admin/announcements';
const valid = { title: 'Network upgrade', body: 'Routers restart tonight.', severity: 'info', target_type: 'all', target_id: null, send_email: false };

function list(): AnnouncementAdmin[] {
	return mockAdminAnnouncements('GET', BASE, null) as AnnouncementAdmin[];
}

describe('mockAdminAnnouncements lifecycle', () => {
	beforeEach(() => resetMockupState());

	it('lists the seeded sample and puts a created announcement first', () => {
		expect(list().map((item) => item.title)).toEqual(['Scheduled storage maintenance']);
		const created = mockAdminAnnouncements('POST', BASE, { ...valid, title: '  Network upgrade  ' }) as AnnouncementAdmin;
		expect(created).toMatchObject({ title: 'Network upgrade', target_type: 'all', target_id: null, is_active: true, created_by_username: 'demo-admin' });
		expect(list().map((item) => item.id)).toEqual([created.id, 1]);
	});

	it('rejects blank text, unknown severity or target, missing target id and email delivery', () => {
		for (const payload of [
			{ ...valid, title: '   ' },
			{ ...valid, body: '' },
			{ ...valid, severity: 'critical' },
			{ ...valid, target_type: 'everyone' },
			{ ...valid, target_type: 'project', target_id: null },
			{ ...valid, target_type: 'user', target_id: 'bad id!' },
			{ ...valid, send_email: true },
		]) expect(() => mockAdminAnnouncements('POST', BASE, payload)).toThrow(ApiError);
		expect(list()).toHaveLength(1);
	});

	it('allows repeated titles like the real API and deletes only the selected id', () => {
		const first = mockAdminAnnouncements('POST', BASE, valid) as AnnouncementAdmin;
		const second = mockAdminAnnouncements('POST', BASE, valid) as AnnouncementAdmin;
		expect(second.id).not.toBe(first.id);
		mockAdminAnnouncements('DELETE', `${BASE}/${second.id}`, null);
		expect(list().map((item) => item.id).sort()).toEqual([1, first.id].sort());
		expect(() => mockAdminAnnouncements('DELETE', `${BASE}/${second.id}`, null)).toThrow(ApiError);
	});

	it('toggles active state and rejects other edits', () => {
		mockAdminAnnouncements('PATCH', `${BASE}/1`, { is_active: false });
		expect(list()[0].is_active).toBe(false);
		expect(() => mockAdminAnnouncements('PATCH', `${BASE}/1`, { title: 'changed' })).toThrow(ApiError);
	});

	it('serves form options and ignores paths it does not own', () => {
		expect(mockAdminAnnouncements('GET', `${BASE}/meta/options`, null)).toEqual({ severities: ['info', 'warning', 'danger'], target_types: ['all', 'project', 'user'] });
		expect(mockAdminAnnouncements('GET', '/api/v1/announcements', null)).toBeUndefined();
		expect(mockAdminAnnouncements('POST', `${BASE}/1/email`, {})).toBeUndefined();
	});
});
