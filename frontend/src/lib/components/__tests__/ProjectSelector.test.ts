import { fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { get, readable } from 'svelte/store';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { dialogFocus } from '$lib/utils/dialogFocus';
import ProjectSelector from '../ProjectSelector.svelte';
import { api } from '$lib/api/client';
import { auth, clearAuth, projectSwitching, setAuth } from '$lib/stores/auth';
import { projectList } from '$lib/stores/projectList';
import { cloudShell } from '$lib/stores/cloudShell.svelte';

vi.mock('$app/environment', () => ({ browser: true }));
vi.mock('$app/stores', () => {
	return { page: readable({ data: { mockup: { active: false } } }) };
});
vi.mock('$lib/api/client', () => ({
	ApiError: class ApiError extends Error {},
	api: {
		get: vi.fn(),
		post: vi.fn(),
	},
}));

const { createLocalStorage } = vi.hoisted(() => {
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
	const storage = createLocalStorage();
	vi.stubGlobal('localStorage', storage);
	Object.defineProperty(window, 'localStorage', { configurable: true, value: storage });
	return { createLocalStorage };
});

describe('ProjectSelector', () => {
	beforeEach(() => {
		const storage = createLocalStorage();
		vi.stubGlobal('localStorage', storage);
		Object.defineProperty(window, 'localStorage', { configurable: true, value: storage });
		vi.clearAllMocks();
		projectSwitching.set(false);
	});

	it('캐시된 목록이 있으면 드롭다운을 열자마자 스피너 없이 표시한다', async () => {
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
		vi.mocked(api.get).mockReturnValue(Promise.withResolvers<never>().promise);
		projectList.prefetch('token', 'user-1');

		render(ProjectSelector, { direction: 'down' });
		await fireEvent.click(screen.getByRole('button', { name: /현재 프로젝트/ }));

		expect(screen.getByText('두 번째 프로젝트')).toBeTruthy();
		expect(screen.queryByRole('status', { name: 'Loading' })).toBeNull();
	});

	it('closes Cloud Shell before replacing the project-scoped token', async () => {
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

	it('keeps a remounted selector fenced until the active rescope settles', async () => {
		projectList.reset();
		setAuth({ token: 'token-a', userId: 'user-1', projectId: 'project-1', projectName: '현재 프로젝트' });
		window.localStorage.setItem('afterglow.projects.user-1', JSON.stringify({
			data: [{ id: 'project-1', name: '현재 프로젝트' }, { id: 'project-2', name: '두 번째 프로젝트' }],
			ts: Date.now(),
		}));
		vi.mocked(api.get).mockReturnValue(Promise.withResolvers<never>().promise);
		projectList.prefetch('token-a', 'user-1');
		const close = vi.spyOn(cloudShell, 'close').mockResolvedValue();
		const pending = Promise.withResolvers<{
			token: string; refresh_token: string; project_id: string; project_name: string;
		}>();
		vi.mocked(api.post).mockImplementation((path) => path === '/api/v1/auth/token/project'
			? pending.promise : Promise.resolve({}));
		const first = render(ProjectSelector);
		try {
			await fireEvent.click(screen.getByRole('button', { name: '현재 프로젝트' }));
			await fireEvent.click(screen.getByRole('button', { name: '두 번째 프로젝트' }));
			await waitFor(() => expect(get(projectSwitching)).toBe(true));
			first.unmount();
			render(ProjectSelector);
			const remounted = screen.getByRole('button', { name: /현재 프로젝트/ });
			expect((remounted as HTMLButtonElement).disabled).toBe(true);
			await fireEvent.click(remounted);
			expect(screen.queryByRole('menu')).toBeNull();
			expect(get(auth).projectId).toBe('project-1');
			pending.resolve({ token: 'token-b', refresh_token: 'refresh-b', project_id: 'project-2', project_name: '두 번째 프로젝트' });
			await waitFor(() => expect(get(auth).projectId).toBe('project-2'));
			expect(get(projectSwitching)).toBe(false);
			expect((screen.getByRole('button', { name: '두 번째 프로젝트' }) as HTMLButtonElement).disabled).toBe(false);
		} finally {
			pending.resolve({ token: 'token-b', refresh_token: 'refresh-b', project_id: 'project-2', project_name: '두 번째 프로젝트' });
			await pending.promise;
			close.mockRestore();
		}
	});

	it.each([false, true])('handles token refresh without applying an old rescope to a replacement login (replacement=%s)', async (replacement) => {
		projectList.reset();
		setAuth({ token: 'original-token', userId: 'user-1', projectId: 'project-1', projectName: '현재 프로젝트' });
		window.localStorage.setItem('afterglow.projects.user-1', JSON.stringify({
			data: [{ id: 'project-1', name: '현재 프로젝트' }, { id: 'project-2', name: '두 번째 프로젝트' }], ts: Date.now(),
		}));
		vi.mocked(api.get).mockReturnValue(Promise.withResolvers<never>().promise);
		projectList.prefetch('original-token', 'user-1');
		const close = vi.spyOn(cloudShell, 'close').mockResolvedValue();
		const pending = Promise.withResolvers<{ token: string; refresh_token: string; project_id: string; project_name: string }>();
		vi.mocked(api.post).mockImplementation((path) => path === '/api/v1/auth/token/project' ? pending.promise : Promise.resolve({}));
		render(ProjectSelector);
		try {
			await fireEvent.click(screen.getByRole('button', { name: '현재 프로젝트' }));
			await fireEvent.click(screen.getByRole('button', { name: '두 번째 프로젝트' }));
			await waitFor(() => expect(get(projectSwitching)).toBe(true));
			if (replacement) clearAuth();
			setAuth({ token: 'new-session-token', userId: 'user-1', projectId: 'project-1', projectName: '현재 프로젝트' });
			pending.resolve({ token: 'rescope-token', refresh_token: 'rescope-refresh', project_id: 'project-2', project_name: '두 번째 프로젝트' });
			await waitFor(() => expect(get(projectSwitching)).toBe(false));
			expect(get(auth).projectId).toBe(replacement ? 'project-1' : 'project-2');
			expect(get(auth).token).toBe(replacement ? 'new-session-token' : 'rescope-token');
		} finally {
			pending.resolve({ token: 'rescope-token', refresh_token: 'rescope-refresh', project_id: 'project-2', project_name: '두 번째 프로젝트' });
			await pending.promise;
			close.mockRestore();
		}
	});


	it('keeps project options reachable by keyboard inside a modal navigation menu', async () => {
		projectList.reset();
		setAuth({ token: 'navigation-token', userId: 'navigation-user', projectId: 'project-1', projectName: '현재 프로젝트' });
		window.localStorage.setItem('afterglow.projects.navigation-user', JSON.stringify({
			data: [{ id: 'project-1', name: '현재 프로젝트' }, { id: 'project-2', name: '두 번째 프로젝트' }], ts: Date.now(),
		}));
		vi.mocked(api.get).mockReturnValue(Promise.withResolvers<never>().promise);
		projectList.prefetch('navigation-token', 'navigation-user');
		const dialog = document.createElement('div');
		dialog.setAttribute('role', 'dialog');
		document.body.appendChild(dialog);
		render(ProjectSelector, { target: dialog });
		const trigger = within(dialog).getByRole('button', { name: '현재 프로젝트' });
		const boundary = dialogFocus(dialog, { enabled: true, onEscape: () => {} });
		try {
			trigger.focus();
			await fireEvent.click(trigger);
			const options = screen.getByRole('menu');
			const currentProject = within(options).getByRole('button', { name: '현재 프로젝트' });
			trigger.focus();
			await fireEvent.keyDown(trigger, { key: 'Tab' });
			expect(document.activeElement).toBe(currentProject);
			await fireEvent.keyDown(currentProject, { key: 'Tab' });
			expect(document.activeElement).toBe(within(options).getByRole('button', { name: '두 번째 프로젝트' }));
		} finally {
			boundary.destroy();
			dialog.remove();
		}
	});
});
