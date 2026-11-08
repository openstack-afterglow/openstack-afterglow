import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { writable } from 'svelte/store';
import { initLocale } from '$lib/i18n/runtime.svelte';
import { t } from '$lib/i18n/ns/usage-schedule';
import { t as instanceT } from '$lib/i18n/ns/instance';
import type { UsageScheduleInfo } from '$lib/types/instanceUsage';

const transport = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), post: vi.fn(), withExperience() { return this; } }));
vi.mock('$lib/api/client', () => ({
	api: transport,
	ApiError: class ApiError extends Error {},
}));
vi.mock('$lib/stores/auth', () => ({
	auth: writable({ token: 'token-a', projectId: 'project-a', userId: 'actor-a' }),
}));

import UsageScheduleSection from '../instance/UsageScheduleSection.svelte';

const schedule: UsageScheduleInfo = {
	instance_id: 'vm-a', starts_at: '2099-01-01T10:20:30Z', expires_at: '2099-01-31T10:20:30Z',
	expiry_action: 'shelve', delete_volumes: false, reason: 'Gateway allocation', revision: 'revision-a',
	state: 'active', source: 'created', last_error: null,
};

beforeEach(() => {
	transport.get.mockReset().mockResolvedValue(schedule);
	transport.put.mockReset();
	transport.post.mockReset();
	initLocale('ko');
});
afterEach(() => cleanup());

describe('usage schedule edit on a Waygate gateway', () => {
	it('keeps only the extension request, sent to the open extend route with the Waygate note', async () => {
		const extended = { ...schedule, expires_at: '2099-02-28T10:20:30Z', revision: 'revision-b' };
		transport.post.mockResolvedValue(extended);
		render(UsageScheduleSection, { instanceId: 'vm-a', projectId: 'project-a', canWrite: true, waygateLocked: true });
		await screen.findByText(t('sourceCreated'));
		expect(screen.getByTestId('waygate-managed-note').textContent).toBe(instanceT('waygate.managedNote'));
		expect(screen.getByRole('link', { name: instanceT('waygate.openLink') }).getAttribute('href')).toBe('/dashboard/network/waygate');
		// The expiry action cannot change on a gateway; only a later expiry and its reason.
		expect(screen.queryByLabelText(t('action'))).toBeNull();
		const extend = screen.getByRole<HTMLButtonElement>('button', { name: t('extend') });
		await waitFor(() => expect(extend.disabled).toBe(false));
		await fireEvent.click(extend);
		await fireEvent.input(screen.getByLabelText(new RegExp(t('reason'))), { target: { value: 'VPN still in use' } });
		const save = screen.getByRole<HTMLButtonElement>('button', { name: t('save') });
		await waitFor(() => expect(save.disabled).toBe(false));
		await fireEvent.click(save);
		await waitFor(() => expect(transport.post).toHaveBeenCalledOnce());
		const [path, payload] = transport.post.mock.calls[0];
		expect(path).toBe('/api/v1/instances/vm-a/usage-schedule/extend');
		expect(payload).toEqual({ expires_at: expect.any(String), reason: 'VPN still in use', revision: 'revision-a' });
		expect(Date.parse(payload.expires_at)).toBeGreaterThan(Date.parse(schedule.expires_at));
		expect(transport.put).not.toHaveBeenCalled();
	});

	it('keeps the edit form for an ordinary instance', async () => {
		render(UsageScheduleSection, { instanceId: 'vm-a', projectId: 'project-a', canWrite: true });
		await waitFor(() => expect(screen.getByRole<HTMLButtonElement>('button', { name: t('save') })).toBeTruthy());
		expect(screen.queryByTestId('waygate-managed-note')).toBeNull();
	});
});
