import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import { writable, type Writable } from 'svelte/store';
import { tick } from 'svelte';
import type { VolumeBackup } from '$lib/types/volume';

const { mockGet, mockPost } = vi.hoisted(() => ({ mockGet: vi.fn(), mockPost: vi.fn() }));

vi.mock('$lib/api/client', () => ({
  api: { get: mockGet, prefetch: vi.fn(), post: mockPost, delete: vi.fn() },
  ApiError: class ApiError extends Error { status = 500; },
}));
vi.mock('$lib/stores/auth', () => ({
  auth: writable({ token: 'token', projectId: 'old' }),
  canWrite: writable(true), projectSwitching: writable(false),
}));
vi.mock('$lib/utils/autoRefresh.svelte', () => ({
  createAutoRefresh: () => ({ active: false, intervalSeconds: 15, intervalOptions: [10, 15, 30, 60] }),
}));
vi.mock('$app/state', () => ({ page: { url: new URL('http://localhost/dashboard/volumes/backups') } }));

import { auth } from '$lib/stores/auth';
import Page from '../+page.svelte';

const projectAuth = auth as unknown as Writable<{ token: string; projectId: string | null }>;
const backup = (id: string): VolumeBackup => ({
  id, name: id, description: null, volume_id: 'volume-1', status: 'available', size: 1,
  created_at: '2026-01-01T00:00:00Z', is_incremental: false, has_dependent_backups: false,
});

describe('volume backup project isolation', () => {
  beforeEach(() => {
    projectAuth.set({ token: 'token', projectId: 'old' });
    mockGet.mockReset();
    mockPost.mockReset();
    mockPost.mockResolvedValue([]);
  });

  it('ignores a late response from the previous project and clears rows when no project is selected', async () => {
    let resolveOld!: (rows: VolumeBackup[]) => void;
    const oldResponse = new Promise<VolumeBackup[]>((resolve) => { resolveOld = resolve; });
		const oldStarted = Promise.withResolvers<void>();
    mockGet.mockImplementation((path: string, _token: string, projectId: string) => {
      if (path === '/api/v1/volumes') return Promise.resolve([]);
      expect(path).toBe('/api/v1/volumes/backups');
			if (projectId === 'old') { oldStarted.resolve(); return oldResponse; }
			return Promise.resolve([backup('current-backup')]);
    });

    render(Page);
		await oldStarted.promise;
    projectAuth.set({ token: 'token', projectId: 'current' });
    expect(await screen.findByText('current-backup')).toBeTruthy();

    resolveOld([backup('previous-project-backup')]);
    await tick();
    expect(screen.queryByText('previous-project-backup')).toBeNull();
    expect(screen.getByText('current-backup')).toBeTruthy();

    projectAuth.set({ token: 'token', projectId: null });
    await vi.waitFor(() => expect(screen.queryByText('current-backup')).toBeNull());
    expect(screen.getByText('볼륨 백업이 없습니다')).toBeTruthy();
  });
});
