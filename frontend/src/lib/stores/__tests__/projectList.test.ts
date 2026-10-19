import { get } from 'svelte/store';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('$app/environment', () => ({ browser: true }));
vi.mock('$lib/api/client', () => ({
	api: {
		get: vi.fn(),
	},
}));

describe('projectList store', () => {
	beforeEach(() => {
		window.localStorage.clear();
		window.sessionStorage.clear();
		vi.clearAllMocks();
		vi.resetModules();
	});

	it('fresh localStorage 캐시는 prefetch 즉시 store에 반영한다', async () => {
		const cachedProjects = [{ id: 'project-1', name: '캐시 프로젝트' }];
		window.localStorage.setItem(
			'afterglow.projects.user-1',
			JSON.stringify({ data: cachedProjects, ts: Date.now() }),
		);
		const { api } = await import('$lib/api/client');
		vi.mocked(api.get).mockReturnValue(new Promise(() => {}));
		const { projectList } = await import('../projectList');

		projectList.prefetch('token', 'user-1');

		expect(get(projectList)).toMatchObject({ projects: cachedProjects, loaded: true });
		expect(api.get).toHaveBeenCalledWith('/api/v1/auth/projects?cache=true', 'token');
	});

	it('stale localStorage 캐시는 즉시 반영하지 않고 revalidate 결과로 채운다', async () => {
		const staleProjects = [{ id: 'stale', name: '오래된 프로젝트' }];
		const freshProjects = [{ id: 'fresh', name: '새 프로젝트' }];
		const { BROWSER_TTL_MS, projectList } = await import('../projectList');
		window.localStorage.setItem(
			'afterglow.projects.user-1',
			JSON.stringify({ data: staleProjects, ts: Date.now() - BROWSER_TTL_MS - 1 }),
		);
		const { api } = await import('$lib/api/client');
		vi.mocked(api.get).mockResolvedValueOnce(freshProjects);

		projectList.prefetch('token', 'user-1');
		expect(get(projectList).projects).toEqual([]);

		await vi.waitFor(() => {
			expect(get(projectList)).toEqual({ projects: freshProjects, loading: false, loaded: true });
		});
	});

	it('revalidate 성공 시 data와 ts를 localStorage에 갱신한다', async () => {
		const projects = [{ id: 'project-1', name: '프로젝트 1' }];
		const { api } = await import('$lib/api/client');
		vi.mocked(api.get).mockResolvedValueOnce(projects);
		const { projectList } = await import('../projectList');
		const before = Date.now();

		await projectList.revalidate('token', 'user-1');

		const cached = JSON.parse(window.localStorage.getItem('afterglow.projects.user-1') ?? '{}');
		expect(cached.data).toEqual(projects);
		expect(cached.ts).toBeGreaterThanOrEqual(before);
		expect(cached.ts).toBeLessThanOrEqual(Date.now());
	});

	it('reset(userId)는 store와 해당 사용자의 localStorage 캐시를 비운다', async () => {
		const projects = [{ id: 'project-1', name: '프로젝트 1' }];
		window.localStorage.setItem(
			'afterglow.projects.user-1',
			JSON.stringify({ data: projects, ts: Date.now() }),
		);
		const { api } = await import('$lib/api/client');
		vi.mocked(api.get).mockReturnValue(new Promise(() => {}));
		const { projectList } = await import('../projectList');
		projectList.prefetch('token', 'user-1');

		projectList.reset('user-1');

		expect(get(projectList)).toEqual({ projects: [], loading: false, loaded: false });
		expect(window.localStorage.getItem('afterglow.projects.user-1')).toBeNull();
	});

	it('auth token이 null이 되면 이전 사용자의 store와 캐시를 자동 초기화한다', async () => {
		const projects = [{ id: 'project-1', name: '프로젝트 1' }];
		const { api } = await import('$lib/api/client');
		vi.mocked(api.get).mockReturnValue(new Promise(() => {}));
		const { projectList } = await import('../projectList');
		const { auth, clearAuth, setAuth } = await import('../auth');
		setAuth({ token: 'token', userId: 'user-1' });
		window.localStorage.setItem(
			'afterglow.projects.user-1',
			JSON.stringify({ data: projects, ts: Date.now() }),
		);
		projectList.prefetch('token', 'user-1');
		expect(get(projectList).projects).toEqual(projects);

		clearAuth();

		expect(get(auth).token).toBeNull();
		expect(get(projectList)).toEqual({ projects: [], loading: false, loaded: false });
		expect(window.localStorage.getItem('afterglow.projects.user-1')).toBeNull();
	});

	it('reset 뒤 늦게 완료된 요청은 초기화된 store를 다시 채우지 않는다', async () => {
		let resolveRequest: ((projects: { id: string; name: string }[]) => void) | undefined;
		const { api } = await import('$lib/api/client');
		vi.mocked(api.get).mockReturnValueOnce(new Promise((resolve) => { resolveRequest = resolve; }));
		const { projectList } = await import('../projectList');
		const request = projectList.revalidate('token', 'user-1');

		projectList.reset('user-1');
		resolveRequest?.([{ id: 'late-project', name: '늦은 프로젝트' }]);
		await request;

		expect(get(projectList)).toEqual({ projects: [], loading: false, loaded: false });
		expect(window.localStorage.getItem('afterglow.projects.user-1')).toBeNull();
	});

	it('clears cached projects and fences pending publication when one account changes working domain', async () => {
		// Each test reloads the singleton to exercise its auth-subscription boundary.
		const { api } = await import('$lib/api/client');
		const { auth, clearAuth, setLoginAuth, setAuth } = await import('../auth');
		setLoginAuth({ token: 'home-token', userId: 'user-1', identityDomainId: 'home', domainId: 'home' });
		const { projectList } = await import('../projectList');
		const pending = Promise.withResolvers<{ id: string; name: string }[]>();
		vi.mocked(api.get).mockReturnValueOnce(pending.promise);
		window.localStorage.setItem('afterglow.projects.user-1', JSON.stringify({ data: [{ id: 'home-project', name: 'Home' }], ts: Date.now(), domainId: 'home' }));
		projectList.prefetch('home-token', 'user-1');
		expect(get(projectList).projects).toHaveLength(1);
		setAuth({ token: 'team-token', domainId: 'team' });
		expect(get(auth).identityDomainId).toBe('home');
		expect(get(projectList)).toEqual({ projects: [], loading: false, loaded: false });
		expect(window.localStorage.getItem('afterglow.projects.user-1')).toBeNull();
		pending.resolve([{ id: 'late-home-project', name: 'Late home' }]);
		await pending.promise;
		await Promise.resolve();
		expect(get(projectList).projects).toEqual([]);
		clearAuth();
	});
});
