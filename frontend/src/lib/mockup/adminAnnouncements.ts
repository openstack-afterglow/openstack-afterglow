import { ApiError } from '$lib/api/errors';
import type { AnnouncementAdmin, AnnouncementCreatePayload, AnnouncementSeverity, AnnouncementTargetType } from '$lib/types/announcements';
import { getMockupState } from './state';

const SEVERITIES: AnnouncementSeverity[] = ['info', 'warning', 'danger'];
const TARGET_TYPES: AnnouncementTargetType[] = ['all', 'project', 'user'];
const TARGET_ID = /^[A-Za-z0-9_-]{1,64}$/;
const CREATED_AT = '2026-11-08T00:00:00Z';

// Explicit synthetic admin announcement state: list, create (no email), active toggle and delete.
// Validation mirrors backend/app/services/announcements.py; titles are not unique there either.
// Returns undefined for paths this module does not own so transport can keep its own dispatch.
export function mockAdminAnnouncements(method: string, path: string, body: unknown): unknown | undefined {
	const state = getMockupState();
	if (path === '/api/v1/admin/announcements/meta/options' && method === 'GET') return { severities: SEVERITIES, target_types: TARGET_TYPES };
	if (path === '/api/v1/admin/announcements' && method === 'GET') return [...state.adminAnnouncements].sort((a, b) => b.created_at.localeCompare(a.created_at) || b.id - a.id);
	if (path === '/api/v1/admin/announcements' && method === 'POST') {
		const payload = (body ?? {}) as Partial<AnnouncementCreatePayload>;
		const title = String(payload.title ?? '').trim();
		const text = String(payload.body ?? '').trim();
		const severity = payload.severity ?? 'info';
		const targetType = payload.target_type;
		if (payload.send_email) throw new ApiError(409, 'Announcement email delivery is not available in the tutorial.');
		if (!title || title.length > 200) throw new ApiError(400, 'Announcement title must be 1-200 characters.');
		if (!text || text.length > 10_000) throw new ApiError(400, 'Announcement body must be 1-10000 characters.');
		if (!SEVERITIES.includes(severity)) throw new ApiError(400, `Unsupported severity: ${severity}.`);
		if (!targetType || !TARGET_TYPES.includes(targetType)) throw new ApiError(400, `Unsupported target_type: ${targetType}.`);
		const targetId = targetType === 'all' ? null : payload.target_id ?? null;
		if (targetType !== 'all' && (!targetId || !TARGET_ID.test(targetId))) throw new ApiError(400, `target_type='${targetType}' requires a valid target_id.`);
		const created: AnnouncementAdmin = {
			id: Math.max(0, ...state.adminAnnouncements.map((item) => item.id)) + 1,
			created_at: CREATED_AT, updated_at: CREATED_AT,
			created_by_user_id: 'mock-admin-1', created_by_username: 'demo-admin',
			title, body: text, severity, target_type: targetType, target_id: targetId,
			starts_at: payload.starts_at ?? null, ends_at: payload.ends_at ?? null, is_active: true,
		};
		state.adminAnnouncements.push(created);
		return created;
	}
	const item = path.match(/^\/api\/v1\/admin\/announcements\/(\d+)$/);
	if (item && (method === 'PATCH' || method === 'DELETE')) {
		const id = Number(item[1]);
		const existing = state.adminAnnouncements.find((entry) => entry.id === id);
		if (!existing) throw new ApiError(404, `Announcement not found: ${id}`);
		if (method === 'DELETE') {
			state.adminAnnouncements = state.adminAnnouncements.filter((entry) => entry.id !== id);
			return {};
		}
		const patch = (body ?? {}) as { is_active?: unknown };
		if (typeof patch.is_active !== 'boolean') throw new ApiError(409, 'Only the active toggle is available in the tutorial.');
		existing.is_active = patch.is_active;
		existing.updated_at = CREATED_AT;
		return existing;
	}
	return undefined;
}
