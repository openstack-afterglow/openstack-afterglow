import { render, screen, waitFor } from '@testing-library/svelte';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { flushSync, tick } from 'svelte';
import { ApiError } from '$lib/api/client';
import type * as ClientModule from '$lib/api/client';
import { t } from '$lib/i18n/ns/database';
import DbInstanceDetailPanel from '../DbInstanceDetailPanel.svelte';

const transport = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('$lib/api/client', async (importOriginal) => {
	const actual = await importOriginal<typeof ClientModule>();
	return { ...actual, api: { get: transport.get, withExperience() { return this; } } };
});
vi.mock('$lib/utils/autoRefresh.svelte', () => ({
	createAutoRefresh: () => ({ active: false, intervalSeconds: 15, intervalOptions: [10, 15, 30, 60] }),
}));
vi.mock('$lib/stores/confirm.svelte', () => ({ confirmDialog: vi.fn() }));
vi.mock('$lib/stores/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

beforeEach(() => { vi.clearAllMocks(); });

function serveEmptyCatalog(status: number) {
	const reads = new Map<string, number>();
	transport.get.mockImplementation((path: string, token?: string, project?: string) => {
		const key = JSON.stringify([path, token, project]);
		const count = (reads.get(key) ?? 0) + 1;
		reads.set(key, count);
		// Bound the failing-before effect: an unintended repeat cannot create an endless test loop.
		if (count > 1) return new Promise(() => {});
		if (/\/database-instances\/db-[ab]$/.test(path)) {
			return Promise.reject(new ApiError(status, 'PRIVATE-UPSTREAM-DETAIL'));
		}
		return Promise.resolve([]);
	});
	return reads;
}

async function settleAssignments() {
	await tick();
	flushSync();
	await tick();
}

describe('database detail read lifecycle', () => {
	it.each([404, 503])('does not reload after an empty flavor response and keeps HTTP%s outcome honest', async (status) => {
		const reads = serveEmptyCatalog(status);
		render(DbInstanceDetailPanel, { instanceId: 'db-a', token: 'token-a', projectId: 'project-a' });
		await screen.findByText(t(status === 404 ? 'instance.notFound' : 'instances.loadFailed'));
		await settleAssignments();
		expect(reads.get(JSON.stringify(['/api/v1/database-instances/flavors', 'token-a', 'project-a']))).toBe(1);
		expect(reads.get(JSON.stringify(['/api/v1/database-instances/db-a', 'token-a', 'project-a']))).toBe(1);
		expect(screen.queryByText('PRIVATE-UPSTREAM-DETAIL')).toBeNull();
		if (status === 503) {
			expect(screen.queryByText(t('instance.notFound'))).toBeNull();
			expect(screen.getByRole('alert').textContent).toContain(t('instances.loadFailed'));
		}
	});

	it.each(['instanceId', 'token', 'projectId'] as const)('still reloads once when the %s input changes', async (field) => {
		serveEmptyCatalog(404);
		const original = { instanceId: 'db-a', token: 'token-a', projectId: 'project-a' };
		const panel = render(DbInstanceDetailPanel, original);
		await screen.findByText(t('instance.notFound'));
		await settleAssignments();
		const before = transport.get.mock.calls.filter(([path]) => path === '/api/v1/database-instances/db-a').length;
		expect(before).toBe(1);
		const next = { ...original, [field]: field === 'instanceId' ? 'db-b' : field === 'token' ? 'token-b' : 'project-b' };
		await panel.rerender(next);
		await waitFor(() => expect(transport.get.mock.calls.filter(([path, token, project]) =>
			path === `/api/v1/database-instances/${next.instanceId}` && token === next.token && project === next.projectId
		)).toHaveLength(1));
		await settleAssignments();
		expect(transport.get.mock.calls.filter(([path, token, project]) =>
			path === `/api/v1/database-instances/${next.instanceId}` && token === next.token && project === next.projectId
		)).toHaveLength(1);
	});
});
