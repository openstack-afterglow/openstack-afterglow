import type { UsageScheduleDraft, UsageScheduleInfo, UsageScheduleRequest } from '$lib/types/instanceUsage';
import { USAGE_STATES } from '$lib/types/instanceUsage';

const NON_GPU_ALIAS_TOKENS: Record<string, true> = {
	audio: true, crypto: true, fpga: true, infiniband: true, network: true,
	nic: true, nvme: true, qat: true, rdma: true, sriov: true,
};

export function validUsageSchedule(row: UsageScheduleInfo): boolean {
	if (!row || typeof row.instance_id !== 'string' || !row.instance_id) return false;
	const awareDate = (value: unknown) => typeof value === 'string'
		&& /(?:Z|[+-]\d{2}:\d{2})$/i.test(value) && Number.isFinite(Date.parse(value));
	return awareDate(row.starts_at) && awareDate(row.expires_at)
		&& USAGE_STATES.includes(row.state)
		&& ['created', 'adopted'].includes(row.source) && ['shelve', 'delete'].includes(row.expiry_action)
		&& typeof row.delete_volumes === 'boolean' && (row.expiry_action === 'delete' || !row.delete_volumes)
		&& typeof row.revision === 'string' && row.revision.length > 0 && typeof row.reason === 'string'
		&& (row.last_error === null || typeof row.last_error === 'string');
}

export function requiresUsageSchedule(flavor: {
	name?: string; vcpus?: number; ram?: number; is_gpu?: boolean | null; gpu_count?: number | null;
	usage_schedule_required?: boolean; extra_specs?: Record<string, string>;
} | null | undefined): boolean {
	if (!flavor) return false;
	if (typeof flavor.usage_schedule_required === 'boolean') return flavor.usage_schedule_required;
	const specs = flavor.extra_specs ?? {};
	if ((flavor.vcpus ?? 0) >= 12 || (flavor.ram ?? 0) >= 65536
		|| ['true', '1', 'yes', 'on'].includes((specs['afterglow:usage_schedule_required'] ?? '').trim().toLowerCase())) return true;
	if (Object.entries(specs).some(([key, value]) => /^resources\d*:[VP]GPU$/.test(key) && Number(value) > 0)) return true;
	if ((specs['pci_passthrough:alias'] ?? '').split(',').some(entry => {
		const trimmed = entry.trim();
		const alias = (trimmed.includes(':') ? trimmed.slice(0, trimmed.lastIndexOf(':')) : trimmed).trim().toLowerCase();
		return alias && !alias.includes('audio') && alias.split(/[^a-z0-9]+/).every(token => !Object.hasOwn(NON_GPU_ALIAS_TOKENS, token));
	})) return true;
	if ((specs[':category'] ?? '').toLowerCase().includes('gpu')) return true;
	if (typeof flavor.is_gpu === 'boolean') return flavor.is_gpu;
	return /^(gpu[._]|g1\.)/i.test(flavor.name ?? '');
}

/** UTC calendar arithmetic, matching native metadata policy (including month-end clamping). */
export function calendarMonthAfter(now: Date): Date {
	const next = new Date(now);
	const day = next.getUTCDate();
	next.setUTCDate(1);
	next.setUTCMonth(next.getUTCMonth() + 1);
	const lastDay = new Date(Date.UTC(next.getUTCFullYear(), next.getUTCMonth() + 1, 0)).getUTCDate();
	next.setUTCDate(Math.min(day, lastDay));
	return next;
}

export function toLocalDateTime(iso: string): string {
	const date = new Date(iso);
	if (!Number.isFinite(date.getTime())) return '';
	const pad = (value: number) => String(value).padStart(2, '0');
	return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export function fromLocalDateTime(value: string): string | null {
	if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value)) return null;
	const date = new Date(value);
	// Reject impossible dates and local DST gaps instead of silently normalizing them.
	return Number.isFinite(date.getTime()) && toLocalDateTime(date.toISOString()) === value ? date.toISOString() : null;
}

export function defaultUsageDraft(now = new Date()): UsageScheduleDraft {
	const expiry = calendarMonthAfter(now).toISOString();
	return { expiresLocal: toLocalDateTime(expiry), defaultExpiresAt: expiry, expiryAction: 'shelve', deleteVolumes: false, reason: '' };
}

export function scheduleDraft(schedule: UsageScheduleInfo): UsageScheduleDraft {
	return { expiresLocal: toLocalDateTime(schedule.expires_at), defaultExpiresAt: schedule.expires_at,
		expiryAction: schedule.expiry_action, deleteVolumes: schedule.delete_volumes, reason: '' };
}

export type UsageDraftError = 'invalidDate' | 'pastDate' | 'shorterDate' | 'reasonRequired' | 'reasonInvalid' | 'invalidConsent';
export function usageDraftError(draft: UsageScheduleDraft, currentExpiry?: string, now = Date.now()): UsageDraftError | null {
	const expires = fromLocalDateTime(draft.expiresLocal);
	if (!expires) return 'invalidDate';
	const changed = !currentExpiry || draft.expiresLocal !== toLocalDateTime(currentExpiry);
	if (changed && Date.parse(expires) <= now) return 'pastDate';
	if (currentExpiry && changed && Date.parse(expires) < Date.parse(currentExpiry)) return 'shorterDate';
	if (draft.expiryAction !== 'delete' && draft.deleteVolumes) return 'invalidConsent';
	const reason = draft.reason.trim();
	if (new TextEncoder().encode(reason).length > 255 || /[\u0000-\u001f\u007f-\u009f]/u.test(reason)) return 'reasonInvalid';
	const baseline = currentExpiry ?? draft.defaultExpiresAt;
	if (changed && Date.parse(expires) > Date.parse(baseline) && !reason) return 'reasonRequired';
	return null;
}

export function usagePayload(draft: UsageScheduleDraft, currentExpiry?: string): UsageScheduleRequest {
	const expires = fromLocalDateTime(draft.expiresLocal);
	if (!expires) throw new Error('Invalid usage schedule date');
	// null preserves native expiry on edits and uses the server clock for untouched initial defaults.
	const unchanged = draft.expiresLocal === toLocalDateTime(currentExpiry ?? draft.defaultExpiresAt);
	return { expires_at: unchanged ? null : expires, expiry_action: draft.expiryAction, delete_volumes: draft.expiryAction === 'delete' && draft.deleteVolumes, reason: draft.reason.trim() };
}

export type UsageUrgency = 'week' | 'threeDays' | 'oneDay' | 'expired' | 'attention';
export function scheduleUrgency(schedule: UsageScheduleInfo, now = Date.now()): UsageUrgency | null {
	if (schedule.last_error || !['active', 'complete'].includes(schedule.state)) return 'attention';
	if (schedule.state === 'complete') return null;
	const remaining = Date.parse(schedule.expires_at) - now;
	if (!Number.isFinite(remaining)) return 'attention';
	if (remaining <= 0) return 'expired';
	if (remaining <= 86400000) return 'oneDay';
	if (remaining <= 3 * 86400000) return 'threeDays';
	return remaining <= 7 * 86400000 ? 'week' : null;
}
