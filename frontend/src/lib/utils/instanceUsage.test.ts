import { describe, expect, it } from 'vitest';
import { calendarMonthAfter, defaultUsageDraft, fromLocalDateTime, requiresUsageSchedule, scheduleDraft, scheduleUrgency, toLocalDateTime, usageDraftError, usagePayload } from './instanceUsage';
import type { UsageScheduleInfo } from '$lib/types/instanceUsage';

const now = Date.parse('2026-01-31T12:34:56Z');
const schedule: UsageScheduleInfo = {
	instance_id: 'vm-a', starts_at: new Date(now).toISOString(), expires_at: '2026-02-28T12:34:56Z',
	expiry_action: 'shelve', delete_volumes: false, reason: '', revision: 'native-revision', state: 'active', source: 'created', last_error: null,
};

describe('native usage policy presentation', () => {
	it.each([
		[{ vcpus: 11, ram: 65535 }, false], [{ vcpus: 12, ram: 1024 }, true], [{ vcpus: 1, ram: 65536 }, true],
		[{ is_gpu: true }, true], [{ gpu_count: 1 }, false], [{ name: 'gpu.small' }, true], [{ name: 'g1.small' }, true],
		[{ extra_specs: { 'resources:VGPU': '1' } }, true], [{ extra_specs: { 'pci_passthrough:alias': 'accelerator:1' } }, true],
		[{ usage_schedule_required: true }, true], [{ extra_specs: { 'afterglow:usage_schedule_required': ' true ' } }, true],
		[{ vcpus: 12, extra_specs: { 'afterglow:usage_schedule_required': 'false' } }, true],
		[{ name: 'cpu.expensive', extra_specs: { 'hw:cpu_policy': 'dedicated', 'afterglow:usage_schedule_required': 'false' } }, false],
		[{ usage_schedule_required: false, extra_specs: { 'afterglow:gpu_model': 'display only' } }, false],
		[{ extra_specs: { 'afterglow:gpu_model': 'display only', 'resources:VGPU': '0', 'pci_passthrough:alias': 'audio:1,nic:1' } }, false],
		[{ extra_specs: { ':category': 'GPU compute' } }, true],
	] as const)('classifies additive requirement %#', (flavor, expected) => {
		expect(requiresUsageSchedule(flavor)).toBe(expected);
	});

	it('clamps a calendar month rather than adding thirty days, retaining UTC time', () => {
		expect(calendarMonthAfter(new Date(now)).toISOString()).toBe('2026-02-28T12:34:56.000Z');
		expect(calendarMonthAfter(new Date('2028-01-31T23:59:00Z')).toISOString()).toBe('2028-02-29T23:59:00.000Z');
		expect(calendarMonthAfter(new Date('2026-12-31T08:00:00Z')).toISOString()).toBe('2027-01-31T08:00:00.000Z');
		const draft = defaultUsageDraft(new Date(now));
		expect(draft.expiryAction).toBe('shelve');
		expect(draft.deleteVolumes).toBe(false);
		expect(usageDraftError(draft, undefined, now)).toBeNull();
	});

	it('roundtrips local dates explicitly and rejects impossible calendar values', () => {
		const iso = '2026-12-12T10:15:00.000Z';
		expect(fromLocalDateTime(toLocalDateTime(iso))).toBe(iso);
		expect(fromLocalDateTime('2026-02-30T10:15')).toBeNull();
		expect(fromLocalDateTime('2026-12-12')).toBeNull();
	});

	it('preserves native second precision for policy-only updates', () => {
		const draft = scheduleDraft(schedule);
		draft.expiryAction = 'delete';
		expect(usagePayload(draft, schedule.expires_at)).toEqual({ expires_at: null, expiry_action: 'delete', delete_volumes: false, reason: '' });
	});

	it('requires a reason for later dates while allowing future shortening', () => {
		const draft = defaultUsageDraft(new Date(now));
		draft.expiresLocal = toLocalDateTime('2026-03-01T12:34:00Z');
		expect(usageDraftError(draft, undefined, now)).toBe('reasonRequired');
		draft.reason = '  research continues  ';
		expect(usageDraftError(draft, undefined, now)).toBeNull();
		expect(usagePayload(draft).reason).toBe('research continues');
		draft.expiresLocal = toLocalDateTime('2026-02-27T12:34:00Z');
		expect(usageDraftError(draft, schedule.expires_at, now, schedule.starts_at)).toBeNull();
	});

	it('caps each extension at one UTC calendar month from the effective expiry', () => {
		const draft = scheduleDraft(schedule);
		draft.reason = 'Research continues';
		draft.expiresLocal = toLocalDateTime('2026-03-28T12:34:00Z');
		expect(usageDraftError(draft, schedule.expires_at, now)).toBeNull();
		draft.expiresLocal = toLocalDateTime('2026-03-28T12:35:00Z');
		expect(usageDraftError(draft, schedule.expires_at, now)).toBe('extensionLimit');
		draft.expiresLocal = toLocalDateTime('2026-01-31T12:34:00Z');
		expect(usageDraftError(draft, schedule.expires_at, now - 60000, schedule.starts_at)).toBe('beforeStart');
		draft.expiresLocal = toLocalDateTime('2026-01-31T12:33:00Z');
		expect(usageDraftError(draft, schedule.expires_at, now)).toBe('pastDate');
	});

	it('limits UTF-8 bytes, not characters, and rejects controls and stale volume consent', () => {
		const draft = scheduleDraft(schedule);
		draft.reason = '가'.repeat(85);
		expect(usageDraftError(draft, schedule.expires_at, now)).toBeNull();
		draft.reason += '가';
		expect(usageDraftError(draft, schedule.expires_at, now)).toBe('reasonInvalid');
		draft.reason = 'line\nbreak';
		expect(usageDraftError(draft, schedule.expires_at, now)).toBe('reasonInvalid');
		draft.reason = ''; draft.deleteVolumes = true;
		expect(usageDraftError(draft, schedule.expires_at, now)).toBe('invalidConsent');
		expect(usagePayload(draft, schedule.expires_at).delete_volumes).toBe(false);
	});

	it.each([
		[8, null], [7, 'week'], [3, 'threeDays'], [1, 'oneDay'], [0, 'expired'], [-1, 'expired'],
	] as const)('distinguishes reminder boundary %s days', (days, urgency) => {
		expect(scheduleUrgency({ ...schedule, expires_at: new Date(now + days * 86400000).toISOString() }, now)).toBe(urgency);
	});

	it('never labels uncertain outcomes as normal or complete compute release', () => {
		expect(scheduleUrgency({ ...schedule, state: 'unknown' }, now)).toBe('attention');
		expect(scheduleUrgency({ ...schedule, state: 'offload_requested' }, now)).toBe('attention');
		expect(scheduleUrgency({ ...schedule, state: 'complete', last_error: 'native read failed' }, now)).toBe('attention');
		expect(scheduleUrgency({ ...schedule, state: 'complete' }, now)).toBeNull();
	});
});
