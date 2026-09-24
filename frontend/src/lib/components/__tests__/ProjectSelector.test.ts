import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { get } from 'svelte/store';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('$app/environment', () => ({ browser: true }));
vi.mock('$app/stores', async () => {
	const { readable } = await import('svelte/store');
	return { page: readable({ data: { mockup: { active: false } } }) };
});
vi.mock('$lib/api/client', () => ({
	ApiError: class ApiError extends Error {},
	api: {
		get: vi.fn(),
		post: vi.fn(),
	},
}));

function createLocalStorage(): Storage {
	const values = new Map<string, string>();
	return {
		get length() { return values.size; },
		clear: () => values.clear(),
		getItem: (key) => values.get(key) ?? null,
		key: (index) => [...values.keys()][index] ?? null,
		removeItem: (key) => { values.delete(key); },
		setItem: (key, value) => { values.set(key, value); },
	};
}

describe('ProjectSelector', () => {
	beforeEach(() => {
		const storage = createLocalStorage();
		vi.stubGlobal('localStorage', storage);
		Object.defineProperty(window, 'localStorage', { configurable: true, value: storage });
		vi.clearAllMocks();
	});

	it('캐시된 목록이 있으면 드롭다운을 열자마자 스피너 없이 표시한다', async () => {
		const { default: ProjectSelector } = await import('../ProjectSelector.svelte');
		const { api } = await import('$lib/api/client');
		const { auth, setAuth } = await import('$lib/stores/auth');
		const { projectList } = await import('$lib/stores/projectList');
		projectList.reset();
		auth.set({
			token: null,
			refreshToken: null,
			accessExpiresAt: null,
			userId: null,
			username: null,
			projectId: null,
			projectName: null,
			availableProjects: [],
			roles: [],
			isSystemAdmin: false,
			federated: false,
		});
		const projects = [
			{ id: 'project-1', name: '현재 프로젝트' },
			{ id: 'project-2', name: '두 번째 프로젝트' },
		];
		setAuth({
			token: 'token',
			userId: 'user-1',
			projectId: 'project-1',
			projectName: '현재 프로젝트',
		});
		window.localStorage.setItem(
			'afterglow.projects.user-1',
			JSON.stringify({ data: projects, ts: Date.now() }),
		);
		vi.mocked(api.get).mockReturnValue(new Promise(() => {}));
		projectList.prefetch('token', 'user-1');
		expect(get(projectList).projects).toEqual(projects);

		render(ProjectSelector, { direction: 'down' });
		await fireEvent.click(screen.getByRole('button', { name: /현재 프로젝트/ }));

		expect(screen.getByText('두 번째 프로젝트')).toBeTruthy();
		expect(screen.queryByRole('status', { name: 'Loading' })).toBeNull();
		const menu = screen.getByRole('menu');
		expect(menu.parentElement).toBe(document.body);
		expect(menu.className).toContain('z-[var(--z-popover)]');
	});

	it('closes Cloud Shell before replacing the project-scoped token', async () => {
		const { default: ProjectSelector } = await import('../ProjectSelector.svelte');
		const { api } = await import('$lib/api/client');
		const { auth, setAuth } = await import('$lib/stores/auth');
		const { projectList } = await import('$lib/stores/projectList');
		const { cloudShell } = await import('$lib/stores/cloudShell.svelte');
		projectList.reset();
		setAuth({
			token: 'token-a',
			userId: 'user-1',
			projectId: 'project-1',
			projectName: '현재 프로젝트',
		});
		const projects = [
			{ id: 'project-1', name: '현재 프로젝트' },
			{ id: 'project-2', name: '두 번째 프로젝트' },
		];
		window.localStorage.setItem(
			'afterglow.projects.user-1',
			JSON.stringify({ data: projects, ts: Date.now() }),
		);
		projectList.prefetch('token-a', 'user-1');
		const close = vi.spyOn(cloudShell, 'close').mockResolvedValue();
		vi.mocked(api.post).mockResolvedValue({
			token: 'token-b',
			refresh_token: 'refresh-b',
			expires_at: '2030-01-01T00:00:00Z',
			project_id: 'project-2',
			project_name: '두 번째 프로젝트',
			roles: [],
			is_system_admin: false,
		});

		render(ProjectSelector, { direction: 'down' });
		await fireEvent.click(screen.getByRole('button', { name: /현재 프로젝트/ }));
		await fireEvent.click(screen.getByRole('button', { name: /두 번째 프로젝트/ }));
		await waitFor(() => expect(get(auth).projectId).toBe('project-2'));

		expect(close).toHaveBeenCalledWith('project-switch', { keepDock: false });
		expect(close.mock.invocationCallOrder[0]).toBeLessThan(vi.mocked(api.post).mock.invocationCallOrder[0]);
		close.mockRestore();
	});
});
