import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/svelte';
import { clearAuth, projectSwitching, setAuth } from '$lib/stores/auth';
import { api } from '$lib/api/client';
import Page from '../+page.svelte';

vi.mock('$app/environment', () => ({ browser: true }));
vi.mock('$app/state', () => ({ page: { url: new URL('http://localhost/dashboard/volumes/backups') } }));
vi.mock('$lib/utils/autoRefresh.svelte', () => ({
	createAutoRefresh: () => ({ active: false, intervalSeconds: 15, intervalOptions: [10, 15, 30, 60] }),
}));

const configs = '/api/v1/volumes/backups/auto-backup/configs';
const backups = '/api/v1/volumes/backups';
const volume = { id: 'source', name: 'Source volume', status: 'available', size: 10, attachments: [] };
const backup = { id: 'backup', name: 'Saved backup', volume_id: 'source', status: 'available', size: 10,
	created_at: '2026-01-01T00:00:00Z', is_incremental: false, has_dependent_backups: false };
const pending = new Map<string, PromiseWithResolvers<Response>>();
const requests: { path: string; method: string }[] = [];

beforeEach(() => {
	pending.clear(); requests.length = 0;
	projectSwitching.set(false);
	setAuth({ token: 'synthetic-backup-token', refreshToken: null, accessExpiresAt: 4102444800,
		userId: 'reader', projectId: 'project', projectName: 'SYSTEM', domainId: 'domain', identityDomainId: 'domain',
		roles: ['reader'], canWrite: false, isSystemAdmin: false, sessionId: crypto.randomUUID() });
	api.clearPrefetchCache();
	vi.stubGlobal('fetch', vi.fn((input: string, init: RequestInit) => {
		const path = new URL(input).pathname;
		requests.push({ path, method: init.method ?? 'GET' });
		const response = Promise.withResolvers<Response>();
		pending.set(path, response);
		return response.promise;
	}));
});
afterEach(() => { cleanup(); clearAuth({ broadcast: false }); vi.unstubAllGlobals(); });

function complete(path: string, body: unknown, status = 200) {
	pending.get(path)!.resolve(new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }));
}

describe('backup page with the real scoped API transport', () => {
	it.each(['policies-first', 'policies-last'])('publishes concurrent successful reads with %s completion', async (order) => {
		render(Page);
		await waitFor(() => expect(pending.size).toBe(3));
		expect(requests).toEqual(expect.arrayContaining([{ path: configs, method: 'GET' }, { path: backups, method: 'GET' }, { path: '/api/v1/volumes', method: 'GET' }]));
		if (order === 'policies-first') complete(configs, []);
		complete('/api/v1/volumes', [volume]); complete(backups, [backup]);
		if (order === 'policies-last') complete(configs, []);
		await screen.findByText('Saved backup');
		await waitFor(() => expect(screen.queryByRole('status')).toBeNull());
		expect(screen.queryByText('서버 오류')).toBeNull();
		expect(screen.queryByText('원본 볼륨을 불러올 수 없습니다. 정책을 편집하기 전에 다시 시도하세요.')).toBeNull();
		expect(screen.queryByText('볼륨 백업이 없습니다')).toBeNull();
	});

	it('shows a failed list as an alert rather than successful empty artwork or loading', async () => {
		render(Page); await waitFor(() => expect(pending.size).toBe(3));
		complete(configs, []); complete('/api/v1/volumes', [volume]); complete(backups, { detail: 'unavailable' }, 503);
		await screen.findByText('조회 실패 (503)');
		expect(screen.queryByText('볼륨 백업이 없습니다')).toBeNull();
		expect(document.querySelector('.empty-state')).toBeNull();
		expect(screen.queryByRole('status')).toBeNull();
	});

	it('still retires pending GETs when a real policy mutation occurs', async () => {
		const read = api.get('/api/v1/volumes', 'synthetic-backup-token', 'project');
		const result = expect(read).rejects.toMatchObject({ name: 'AbortError' });
		await waitFor(() => expect(pending.has('/api/v1/volumes')).toBe(true));
		const write = api.post('/api/v1/volumes/backups/auto-backup/source', {}, 'synthetic-backup-token', 'project');
		await waitFor(() => expect(pending.size).toBe(2));
		complete('/api/v1/volumes', [volume]); complete('/api/v1/volumes/backups/auto-backup/source', {});
		await write; await result;
	});
});
