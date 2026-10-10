import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { authReady, clearAuth, projectSwitching, setAuth, setProject } from '$lib/stores/auth';
import { siteConfig } from '$lib/config/site';
import { t } from '$lib/i18n/ns/account';
import { initLocale } from '$lib/i18n/runtime.svelte';

const { api, ApiError, confirmDialog, getBaseUrl } = vi.hoisted(() => ({
	api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
	ApiError: class ApiError extends Error {},
	confirmDialog: vi.fn(),
	getBaseUrl: vi.fn(() => 'https://api.example.test'),
}));

vi.mock('$lib/api/client', () => ({ api, ApiError, getBaseUrl }));
vi.mock('$lib/stores/confirm.svelte', () => ({ confirmDialog }));
vi.mock('$app/stores', async () => {
	const { readable } = await import('svelte/store');
	return { page: readable({ data: {}, url: new URL('https://afterglow.example.test/dashboard/account') }) };
});

import McpAccessSection from '../McpAccessSection.svelte';

const clipboardDescriptor = Object.getOwnPropertyDescriptor(navigator, 'clipboard');
const scopedPostOptions = { signal: expect.any(AbortSignal), suppressAuthRedirect: true, cache: 'no-store' };
const scopedGetOptions = { refresh: true, signal: expect.any(AbortSignal), suppressAuthRedirect: true };
const connectionResult = {
	endpoint: 'https://cloud.dmslab.re.kr/mcp',
	protocol_version: '2025-11-25',
	server_name: 'Afterglow',
	server_version: '1.0',
	tool_count: 5,
};

const activeToken = {
	id: 'token-1',
	grant_id: 'grant-1',
	name: 'Lumen',
	source: 'personal_token',
	access_level: 'read',
	project_scope: 'current',
	project_ids: ['project'],
	projects: [{ id: 'project', name: 'Saved home project' }],
	status: 'active',
	visible_prefix: 'mcp-afgl-example',
	issued_at: '2026-07-27T00:00:00Z',
	expires_at: '2026-08-27T00:00:00Z',
	last_used_at: null,
	revoked_at: null,
	is_lumen_default: true,
};

const availableProjects = [
	{ id: 'project', name: 'Project' },
	{ id: 'other', name: 'Other project' },
];

function accountResponse(path: string, personalTokens = [activeToken]) {
	return path.endsWith('/mcp-projects') ? availableProjects : path.includes('oauth') ? [] : personalTokens;
}

async function createButton() {
	const button = await screen.findByRole('button', { name: t('mcp.create') });
	await waitFor(() => expect(button.hasAttribute('disabled')).toBe(false));
	return button;
}

function projectCheckbox(id: string, name: string) {
	return screen.getByRole('checkbox', { name: t('mcp.selectProject', { name, id }) }) as HTMLInputElement;
}

function deferred<T>() {
	return Promise.withResolvers<T>();
}

describe('McpAccessSection', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		initLocale('ko');
		confirmDialog.mockResolvedValue(true);
		clearAuth();
		setAuth({
			token: 'token',
			refreshToken: 'refresh-token',
			userId: 'user',
			username: 'user',
			projectId: 'project',
			projectName: 'Project',
			accessExpiresAt: null,
			roles: [],
		});
		authReady.set(true);
		projectSwitching.set(false);
		siteConfig.update((config) => ({ ...config, mcp_url: '', services: { ...config.services, mcp: true } }));
		api.get.mockImplementation((path: string) => Promise.resolve(accountResponse(path)));
		api.post.mockResolvedValue({ ...activeToken, id: 'token-2', grant_id: 'grant-2', token: 'mcp-afgl-secret-value' });
	});

	afterEach(() => {
		cleanup();
		initLocale('ko');
		if (clipboardDescriptor) Object.defineProperty(navigator, 'clipboard', clipboardDescriptor);
		else Reflect.deleteProperty(navigator, 'clipboard');
		projectSwitching.set(false);
		clearAuth();
		siteConfig.update((config) => ({ ...config, services: { ...config.services, mcp: false } }));
	});

	it.each(['ko', 'en', 'ja', 'zh-CN'] as const)('opens the MCP guide in the account language %s', async (locale) => {
		initLocale(locale);
		render(McpAccessSection);
		const link = await screen.findByRole('link', { name: t('mcp.docs') });
		const url = new URL(link.getAttribute('href')!, 'https://afterglow.example.test');
		expect(url.pathname).toBe('/docs/mcp');
		expect(url.searchParams.get('lang')).toBe(locale === 'ko' ? null : locale);
	});

	it.each(['ko', 'en', 'ja', 'zh-CN'] as const)('localizes explicit project access controls in %s', async (locale) => {
		initLocale(locale);
		render(McpAccessSection);
		await createButton();
		expect(screen.getByText(t('mcp.projectsHelp'))).toBeTruthy();
		expect(screen.getByRole('option', { name: t('mcp.selectedProjects') })).toBeTruthy();
		expect(screen.getByRole('option', { name: t('mcp.allProjects') })).toBeTruthy();
		await fireEvent.click(projectCheckbox('project', 'Project'));
		expect(screen.getByText(t('mcp.projectsRequired'))).toBeTruthy();
	});

	it.each(['ko', 'en', 'ja', 'zh-CN'] as const)('shows immutable saved access and projects on token and OAuth grant lists in %s', async (locale) => {
		initLocale(locale);
		const grant = {
			...activeToken, id: 'oauth-grant', name: 'External client', source: 'oauth', access_level: 'manage', is_lumen_default: false,
			project_scope: 'all', project_ids: ['other'], projects: [{ id: 'other', name: 'Saved other project' }],
		};
		api.get.mockImplementation((path: string) => Promise.resolve(path.includes('oauth') ? [grant] : accountResponse(path)));
		render(McpAccessSection);
		await createButton();
		const restrictions = screen.getAllByRole('group', { name: t('mcp.savedRestrictions') });
		expect(restrictions).toHaveLength(2);
		expect(within(restrictions[0]).getByText(t('mcp.savedAccess', { access: t('mcp.read') }))).toBeTruthy();
		expect(within(restrictions[1]).getByText(t('mcp.savedAccess', { access: t('mcp.manage') }))).toBeTruthy();
		expect(within(restrictions[0]).getByText(t('mcp.savedCurrentProject'))).toBeTruthy();
		expect(within(restrictions[0]).getByText(t('mcp.savedProjects', { projects: 'Saved home project (project)' }))).toBeTruthy();
		expect(within(restrictions[1]).getByText(t('mcp.savedAllProjects'))).toBeTruthy();
		expect(within(restrictions[1]).getByText(t('mcp.savedProjects', { projects: 'Saved other project (other)' }))).toBeTruthy();
		for (const restriction of restrictions) {
			expect(within(restriction).queryByRole('combobox')).toBeNull();
			expect(within(restriction).queryByRole('checkbox')).toBeNull();
		}
		await fireEvent.change(screen.getByLabelText(t('mcp.permission')), { target: { value: 'manage' } });
		expect(within(restrictions[0]).getByText(t('mcp.savedAccess', { access: t('mcp.read') }))).toBeTruthy();
		await fireEvent.change(screen.getByLabelText(t('mcp.projects')), { target: { value: 'all' } });
		expect(within(restrictions[0]).getByText(t('mcp.savedProjects', { projects: 'Saved home project (project)' }))).toBeTruthy();
		expect(within(restrictions[1]).getByText(t('mcp.savedProjects', { projects: 'Saved other project (other)' }))).toBeTruthy();
	});

	it.each(['personal_token', 'oauth'] as const)('shows the explicit saved %s project set rather than current memberships or the creation draft', async (source) => {
		const record = {
			...activeToken, source, project_scope: 'selected', project_ids: ['saved-one', 'saved-two'],
			projects: [{ id: 'saved-one', name: 'Archived name' }, { id: 'saved-two', name: 'Other saved name' }],
		};
		api.get.mockImplementation((path: string) => Promise.resolve(path.endsWith('/mcp-projects') ? availableProjects
			: path.includes('oauth') ? source === 'oauth' ? [record] : [] : source === 'personal_token' ? [record] : []));
		render(McpAccessSection);
		await createButton();
		const restriction = screen.getByRole('group', { name: t('mcp.savedRestrictions') });
		expect(within(restriction).getByText(t('mcp.savedSelectedProjects'))).toBeTruthy();
		expect(within(restriction).getByText(t('mcp.savedProjects', { projects: 'Archived name (saved-one), Other saved name (saved-two)' }))).toBeTruthy();
		await fireEvent.click(projectCheckbox('other', 'Other project'));
		expect(restriction.textContent).not.toContain('Other project (other)');
		await fireEvent.click(screen.getByRole('button', { name: t('mcp.refresh') }));
		await createButton();
		expect(screen.getByRole('group', { name: t('mcp.savedRestrictions') }).textContent).toContain('Archived name (saved-one), Other saved name (saved-two)');
	});

	it.each(['empty', 'missing'] as const)('does not invent saved project restrictions when metadata is %s', async (metadata) => {
		const record = { ...activeToken, projects: metadata === 'empty' ? [] : undefined };
		api.get.mockImplementation((path: string) => Promise.resolve(path.endsWith('/mcp-projects') ? availableProjects : path.includes('oauth') ? [] : [record]));
		render(McpAccessSection);
		await createButton();
		const restriction = screen.getByRole('group', { name: t('mcp.savedRestrictions') });
		expect(within(restriction).getByText(t('mcp.savedProjectsUnavailable'))).toBeTruthy();
		expect(restriction.textContent).not.toContain('Saved home project (project)');
		expect(restriction.textContent).not.toContain('Project (project)');
	});


	it('defaults to read access and the authoritative current project payload', async () => {
		render(McpAccessSection);
		await createButton();
		expect(api.get).toHaveBeenCalledWith('/api/v1/auth/mcp-projects', 'token', 'project', scopedGetOptions);
		expect(projectCheckbox('project', 'Project').checked).toBe(true);
		expect(projectCheckbox('other', 'Other project').checked).toBe(false);
		expect((screen.getByLabelText(t('mcp.permission')) as HTMLSelectElement).value).toBe('read');
		await fireEvent.click(await createButton());
		expect(api.post).toHaveBeenCalledWith('/api/v1/auth/mcp-tokens', {
			name: 'Lumen', access_level: 'read', project_scope: 'selected', project_ids: ['project'], expires_at: null,
		}, 'token', 'project', scopedPostOptions);
	});

	it('issues manage access for explicit projects without adding the home project implicitly', async () => {
		render(McpAccessSection);
		await createButton();
		await fireEvent.change(screen.getByLabelText(t('mcp.permission')), { target: { value: 'manage' } });
		await fireEvent.click(projectCheckbox('project', 'Project'));
		await fireEvent.click(projectCheckbox('other', 'Other project'));
		await fireEvent.input(screen.getByRole('textbox', { name: t('mcp.name') }), { target: { value: 'Explicit client' } });
		await fireEvent.click(await createButton());
		expect(api.post).toHaveBeenCalledWith('/api/v1/auth/mcp-tokens', {
			name: 'Explicit client', access_level: 'manage', project_scope: 'selected', project_ids: ['other'], expires_at: null,
		}, 'token', 'project', scopedPostOptions);
	});

	it('preserves an explicit multi-project payload', async () => {
		render(McpAccessSection);
		await createButton();
		await fireEvent.click(projectCheckbox('other', 'Other project'));
		await fireEvent.click(await createButton());
		expect(api.post).toHaveBeenCalledWith('/api/v1/auth/mcp-tokens', expect.objectContaining({
			project_scope: 'selected', project_ids: ['project', 'other'],
		}), 'token', 'project', scopedPostOptions);
	});

	it('keeps valid explicit choices after a successful authoritative reload', async () => {
		render(McpAccessSection);
		await createButton();
		await fireEvent.click(projectCheckbox('other', 'Other project'));
		await fireEvent.click(screen.getByRole('button', { name: t('mcp.refresh') }));
		await createButton();
		expect(projectCheckbox('project', 'Project').checked).toBe(true);
		expect(projectCheckbox('other', 'Other project').checked).toBe(true);
	});

	it('hides stale saved rows and discards previous project choices when collection reload fails', async () => {
		render(McpAccessSection);
		const button = await createButton();
		expect(screen.getByRole('group', { name: t('mcp.savedRestrictions') })).toBeTruthy();
		await fireEvent.change(screen.getByLabelText(t('mcp.projects')), { target: { value: 'all' } });
		const reload = deferred<typeof activeToken[]>();
		api.get.mockImplementation((path: string) => path.endsWith('/mcp-tokens') ? reload.promise : Promise.resolve(accountResponse(path)));
		await fireEvent.click(screen.getByRole('button', { name: t('mcp.refresh') }));
		expect(screen.queryByRole('group', { name: t('mcp.savedRestrictions') })).toBeNull();
		expect(button.hasAttribute('disabled')).toBe(true);
		await act(async () => { reload.reject(new ApiError('Collection unavailable')); });
		await screen.findByText('Collection unavailable');
		expect(screen.queryByRole('group', { name: t('mcp.savedRestrictions') })).toBeNull();
		expect((screen.getByLabelText(t('mcp.projects')) as HTMLSelectElement).value).toBe('selected');
		expect(projectCheckbox('project', 'Project').checked).toBe(false);
		expect(projectCheckbox('other', 'Other project').checked).toBe(false);
		await fireEvent.submit(button.closest('form')!);
		expect(api.post).not.toHaveBeenCalled();
		api.get.mockImplementation((path: string) => Promise.resolve(accountResponse(path)));
		await fireEvent.click(screen.getByRole('button', { name: t('mcp.refresh') }));
		await screen.findByText(t('mcp.projectsRequired'));
		expect(button.hasAttribute('disabled')).toBe(true);
		await fireEvent.click(projectCheckbox('other', 'Other project'));
		await fireEvent.click(await createButton());
		expect(api.post).toHaveBeenCalledWith('/api/v1/auth/mcp-tokens', expect.objectContaining({ project_ids: ['other'] }), 'token', 'project', scopedPostOptions);
	});

	it.each(['failure', 'empty'] as const)('blocks all-project issuance after a same-owner inventory reload %s', async (result) => {
		render(McpAccessSection);
		await createButton();
		await fireEvent.change(screen.getByLabelText(t('mcp.projects')), { target: { value: 'all' } });
		api.get.mockImplementation((path: string) => path.endsWith('/mcp-projects')
			? result === 'failure' ? Promise.reject(new Error('Failed reload')) : Promise.resolve([])
			: Promise.resolve(accountResponse(path)));
		await fireEvent.click(screen.getByRole('button', { name: t('mcp.refresh') }));
		await screen.findByText(result === 'failure' ? t('mcp.projectsLoadFailed') : t('mcp.noProjects'));
		const button = screen.getByRole('button', { name: t('mcp.create') });
		expect(button.hasAttribute('disabled')).toBe(true);
		await fireEvent.submit(button.closest('form')!);
		expect(api.post).not.toHaveBeenCalled();
	});

	it('submits all projects for server-side resolution without stale selected ids', async () => {
		render(McpAccessSection);
		await createButton();
		await fireEvent.click(projectCheckbox('other', 'Other project'));
		await fireEvent.change(screen.getByLabelText(t('mcp.projects')), { target: { value: 'all' } });
		expect(screen.queryByRole('checkbox')).toBeNull();
		await fireEvent.click(await createButton());
		expect(api.post).toHaveBeenCalledWith('/api/v1/auth/mcp-tokens', {
			name: 'Lumen', access_level: 'read', project_scope: 'all', project_ids: [], expires_at: null,
		}, 'token', 'project', scopedPostOptions);
	});

	it('blocks empty explicit selection even when the form is submitted directly', async () => {
		render(McpAccessSection);
		const button = await createButton();
		await fireEvent.click(projectCheckbox('project', 'Project'));
		expect(button.hasAttribute('disabled')).toBe(true);
		expect(screen.getByText(t('mcp.projectsRequired'))).toBeTruthy();
		await fireEvent.submit(button.closest('form')!);
		expect(api.post).not.toHaveBeenCalled();
	});

	it.each(['failure', 'empty', 'missing-current'] as const)('fails closed on initial project %s', async (result) => {
		api.get.mockImplementation((path: string) => path.endsWith('/mcp-projects')
			? result === 'failure' ? Promise.reject(new Error('Private upstream failure'))
				: Promise.resolve(result === 'empty' ? [] : [availableProjects[1]])
			: Promise.resolve(accountResponse(path)));
		render(McpAccessSection);
		await screen.findByText(result === 'failure' ? t('mcp.projectsLoadFailed') : result === 'empty' ? t('mcp.noProjects') : t('mcp.projectsRequired'));
		const button = screen.getByRole('button', { name: t('mcp.create') });
		expect(button.hasAttribute('disabled')).toBe(true);
		await fireEvent.submit(button.closest('form')!);
		expect(api.post).not.toHaveBeenCalled();
		expect(document.body.textContent).not.toContain('Private upstream failure');
		if (result === 'missing-current') {
			await fireEvent.click(projectCheckbox('other', 'Other project'));
			expect(button.hasAttribute('disabled')).toBe(false);
		}
	});

	it('removes invalid selections and blocks submission throughout a same-owner reload', async () => {
		render(McpAccessSection);
		const button = await createButton();
		await fireEvent.click(projectCheckbox('project', 'Project'));
		await fireEvent.click(projectCheckbox('other', 'Other project'));
		const reload = deferred<typeof availableProjects>();
		api.get.mockImplementation((path: string) => path.endsWith('/mcp-projects') ? reload.promise : Promise.resolve(accountResponse(path)));
		await fireEvent.click(screen.getByRole('button', { name: t('mcp.refresh') }));
		expect(button.hasAttribute('disabled')).toBe(true);
		expect(screen.queryByRole('checkbox')).toBeNull();
		await fireEvent.submit(button.closest('form')!);
		expect(api.post).not.toHaveBeenCalled();
		await act(async () => { reload.resolve([availableProjects[0]]); });
		await screen.findByText(t('mcp.projectsRequired'));
		expect(projectCheckbox('project', 'Project').checked).toBe(false);
		expect(screen.queryByRole('checkbox', { name: t('mcp.selectProject', { name: 'Other project', id: 'other' }) })).toBeNull();
		expect(button.hasAttribute('disabled')).toBe(true);
		await fireEvent.submit(button.closest('form')!);
		expect(api.post).not.toHaveBeenCalled();
	});

	it('discards old selection after reload failure and requires a new explicit choice on recovery', async () => {
		render(McpAccessSection);
		const button = await createButton();
		api.get.mockImplementation((path: string) => path.endsWith('/mcp-projects') ? Promise.reject(new Error('Failed reload')) : Promise.resolve(accountResponse(path)));
		await fireEvent.click(screen.getByRole('button', { name: t('mcp.refresh') }));
		await screen.findByText(t('mcp.projectsLoadFailed'));
		expect(screen.queryByRole('checkbox')).toBeNull();
		expect(button.hasAttribute('disabled')).toBe(true);
		await fireEvent.submit(button.closest('form')!);
		expect(api.post).not.toHaveBeenCalled();
		api.get.mockImplementation((path: string) => Promise.resolve(accountResponse(path)));
		await fireEvent.click(screen.getByRole('button', { name: t('mcp.refresh') }));
		await screen.findByText(t('mcp.projectsRequired'));
		expect(projectCheckbox('project', 'Project').checked).toBe(false);
		expect(button.hasAttribute('disabled')).toBe(true);
		await fireEvent.click(projectCheckbox('project', 'Project'));
		await fireEvent.click(await createButton());
		expect(api.post).toHaveBeenCalledWith('/api/v1/auth/mcp-tokens', expect.objectContaining({ project_ids: ['project'] }), 'token', 'project', scopedPostOptions);
	});

	it.each(['issuance', 'verification'] as const)('preserves the 30-second deadline for scoped %s POST', async (operation) => {
		const deadline = new AbortController();
		const timeout = vi.spyOn(AbortSignal, 'timeout').mockReturnValue(deadline.signal);
		api.post.mockImplementation((_path: string, _payload: unknown, _token: string, _project: string, options: { signal: AbortSignal }) => {
			const { promise, reject } = Promise.withResolvers();
			options.signal.addEventListener('abort', () => reject(options.signal.reason), { once: true });
			return promise;
		});
		try {
			render(McpAccessSection);
			await createButton();
			if (operation === 'issuance') await fireEvent.click(await createButton());
			else {
				await fireEvent.input(screen.getByLabelText(t('mcp.tokenLabel')), { target: { value: 'private-saved-key' } });
				await fireEvent.click(screen.getByRole('button', { name: t('mcp.verify') }));
			}
			expect(timeout).toHaveBeenCalledWith(30_000);
			const signal = api.post.mock.calls[0][4].signal as AbortSignal;
			expect(signal.aborted).toBe(false);
			await act(async () => { deadline.abort(new DOMException('Deadline exceeded', 'TimeoutError')); });
			expect(signal.aborted).toBe(true);
			await screen.findByText(operation === 'issuance' ? t('mcp.createFailed') : t('mcp.verifyError.unavailable'));
			expect(screen.queryByRole('dialog')).toBeNull();
			expect(document.body.textContent).not.toContain('Deadline exceeded');
		} finally {
			timeout.mockRestore();
		}
	});

	it.each(['token', 'user', 'project-aba', 'unmount'] as const)('discards a late project inventory after %s boundary', async (boundary) => {
		const oldProjects = deferred<typeof availableProjects>();
		api.get.mockImplementation((path: string) => path.endsWith('/mcp-projects') ? oldProjects.promise : Promise.resolve(accountResponse(path)));
		const view = render(McpAccessSection);
		await waitFor(() => expect(api.get).toHaveBeenCalledWith('/api/v1/auth/mcp-projects', 'token', 'project', scopedGetOptions));
		const oldSignal = api.get.mock.calls.find(([path]) => path.endsWith('/mcp-projects'))![3].signal as AbortSignal;
		api.get.mockImplementation((path: string) => path.endsWith('/mcp-projects')
			? Promise.resolve([{ id: 'project', name: 'Fresh membership' }]) : Promise.resolve(accountResponse(path)));
		if (boundary === 'token') setAuth({ token: 'new-token' });
		else if (boundary === 'user') setAuth({ token: 'token', userId: 'new-user' });
		else if (boundary === 'project-aba') {
			setProject('other', 'Other project');
			setProject('project', 'Project');
		} else {
			view.unmount();
			render(McpAccessSection);
		}
		await createButton();
		expect(oldSignal.aborted).toBe(true);
		await act(async () => { oldProjects.resolve([{ id: 'old-id', name: 'Stale membership' }]); });
		expect(screen.queryByText('Stale membership')).toBeNull();
		expect(projectCheckbox('project', 'Fresh membership').checked).toBe(true);
		await fireEvent.click(await createButton());
		expect(api.post).toHaveBeenCalledWith('/api/v1/auth/mcp-tokens', expect.objectContaining({ project_ids: ['project'] }), boundary === 'token' ? 'new-token' : 'token', 'project', scopedPostOptions);
	});

	it('does not publish stale issuance when authoritative projects reload for the same owner', async () => {
		const issuance = deferred<typeof activeToken & { token: string }>();
		api.post.mockReturnValue(issuance.promise);
		render(McpAccessSection);
		await fireEvent.click(await createButton());
		const signal = api.post.mock.calls[0][4].signal as AbortSignal;
		expect(signal.aborted).toBe(false);
		await fireEvent.click(screen.getByRole('button', { name: t('mcp.refresh') }));
		expect(signal.aborted).toBe(true);
		await createButton();
		await act(async () => { issuance.resolve({ ...activeToken, token: 'stale-reload-secret' }); });
		expect(screen.queryByRole('dialog')).toBeNull();
		expect(document.body.textContent).not.toContain('stale-reload-secret');
	});

	it('ignores an old project load failure after a new token has fresh metadata', async () => {
		const oldProjects = deferred<typeof availableProjects>();
		api.get.mockImplementation((path: string) => path.endsWith('/mcp-projects') ? oldProjects.promise : Promise.resolve(accountResponse(path)));
		render(McpAccessSection);
		await screen.findByText('Lumen');
		api.get.mockImplementation((path: string) => Promise.resolve(accountResponse(path)));
		setAuth({ token: 'fresh-token' });
		await createButton();
		await act(async () => { oldProjects.reject(new Error('Old load failed')); });
		expect(screen.queryByText(t('mcp.projectsLoadFailed'))).toBeNull();
		expect(projectCheckbox('project', 'Project').checked).toBe(true);
		await fireEvent.click(await createButton());
		expect(api.post).toHaveBeenCalledWith('/api/v1/auth/mcp-tokens', expect.objectContaining({ project_ids: ['project'] }), 'fresh-token', 'project', scopedPostOptions);
	});

	it.each(['success', 'failure'] as const)('ignores a stale issuance %s after a newer same-owner issuance succeeds', async (result) => {
		const oldIssuance = deferred<typeof activeToken & { token: string }>();
		api.post.mockReturnValueOnce(oldIssuance.promise);
		render(McpAccessSection);
		await fireEvent.click(await createButton());
		await fireEvent.click(screen.getByRole('button', { name: t('mcp.refresh') }));
		await fireEvent.click(await createButton());
		await screen.findByRole('dialog', { name: t('mcp.newToken') });
		await act(async () => {
			if (result === 'success') oldIssuance.resolve({ ...activeToken, token: 'older-issued-secret' });
			else oldIssuance.reject(new ApiError('Old issuance error'));
		});
		expect(screen.queryByText('Old issuance error')).toBeNull();
		expect(document.body.textContent).not.toContain('older-issued-secret');
		expect(screen.getByText('mcp-afgl-secret-value')).toBeTruthy();
	});
	it('shows the current Lumen default without exposing a token secret', async () => {
		render(McpAccessSection);

		await waitFor(() => expect(screen.getByText('Lumen 기본 토큰')).toBeTruthy());
		expect(screen.queryByText('mcp-afgl-secret-value')).toBeNull();
		expect(screen.getByRole('button', { name: 'Lumen 해제' })).toBeTruthy();
	});

	it('displays a newly issued token once after creation', async () => {
		render(McpAccessSection);
		await waitFor(() => expect(screen.getByLabelText(/이름/)).toBeTruthy());

		await fireEvent.input(screen.getByLabelText(/이름/), { target: { value: 'Desktop client' } });
		await fireEvent.click(await createButton());

		expect(await screen.findByText('mcp-afgl-secret-value')).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: '완료' }));
		expect(screen.queryByText('mcp-afgl-secret-value')).toBeNull();
	});

	it.each([
		['https://cloud.dmslab.re.kr/mcp', 'https://cloud.dmslab.re.kr/mcp'],
		['https://mcp.example.test', 'https://mcp.example.test'],
		['', 'https://api.example.test/api/v1/mcp'],
	])('copies authenticated HTTP JSON using the configured resource %s', async (configured, endpoint) => {
		const writeText = vi.fn().mockResolvedValue(undefined);
		Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } });
		siteConfig.update((config) => ({ ...config, mcp_url: configured }));
		render(McpAccessSection);
		await fireEvent.click(await createButton());
		const dialog = await screen.findByRole('dialog', { name: t('mcp.newToken') });
		await fireEvent.click(within(dialog).getByRole('button', { name: t('mcp.copyConfig') }));
		await waitFor(() => expect(writeText).toHaveBeenCalledOnce());
		expect(JSON.parse(writeText.mock.calls[0][0])).toEqual({
			mcpServers: { 'my-stream-server': { type: 'http', url: endpoint, headers: { Authorization: ['Bearer', 'mcp-afgl-secret-value'].join(' ') } } },
		});
		await fireEvent.click(within(dialog).getByRole('button', { name: t('mcp.done') }));
		expect(screen.queryByRole('dialog')).toBeNull();
		expect(document.body.textContent).not.toContain('mcp-afgl-secret-value');
		expect(JSON.parse(screen.getByRole('region', { name: t('mcp.config') }).textContent!).mcpServers['my-stream-server'].headers.Authorization).toBe(['Bearer', 'YOUR_PERSONAL_MCP_TOKEN'].join(' '));
	});

	it('copies credential-free OAuth configuration even after issuing a personal token', async () => {
		const writeText = vi.fn().mockResolvedValue(undefined);
		Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } });
		siteConfig.update((config) => ({ ...config, mcp_url: 'https://cloud.dmslab.re.kr/mcp' }));
		render(McpAccessSection);
		await fireEvent.click(await createButton());
		const dialog = await screen.findByRole('dialog', { name: t('mcp.newToken') });
		await fireEvent.click(within(dialog).getByRole('button', { name: t('mcp.done') }));
		await fireEvent.click(screen.getByRole('button', { name: t('mcp.copyOAuthConfig') }));
		await waitFor(() => expect(writeText).toHaveBeenCalledOnce());
		expect(JSON.parse(writeText.mock.calls[0][0])).toEqual({
			mcpServers: { 'my-stream-server': { type: 'http', url: 'https://cloud.dmslab.re.kr/mcp' } },
		});
		expect(screen.getByText('https://cloud.dmslab.re.kr/mcp/oauth/authorize')).toBeTruthy();
	});
	it('hides project-owned tokens and issued secrets while the new scope loads', async () => {
		const tokens = deferred<typeof activeToken[]>();
		const grants = deferred<typeof activeToken[]>();
		api.get.mockImplementation((path: string, _token: string, project: string) => path.endsWith('/mcp-projects')
			? Promise.resolve(availableProjects)
			: project === 'other' ? (path.includes('oauth') ? grants.promise : tokens.promise)
				: Promise.resolve(accountResponse(path)));
		render(McpAccessSection);
		await screen.findByText('Lumen');
		await fireEvent.click(await createButton());
		await screen.findByText('mcp-afgl-secret-value');
		setProject('other', 'Other project');
		await waitFor(() => {
			expect(screen.queryByText('Lumen')).toBeNull();
			expect(screen.queryByText('mcp-afgl-secret-value')).toBeNull();
			expect(screen.queryByRole('button', { name: 'Lumen 해제' })).toBeNull();
		});
		tokens.resolve([{ ...activeToken, id: 'token-b', name: 'Beta token' }]);
		grants.resolve([]);
		await screen.findByText('Beta token');
		expect(screen.queryByText('mcp-afgl-secret-value')).toBeNull();
	});

	it('rejects an old revoke confirmation and late B response after an A→B→A switch', async () => {
		const confirm = deferred<boolean>();
		const bTokens = deferred<typeof activeToken[]>();
		let aReads = 0;
		confirmDialog.mockReturnValue(confirm.promise);
		api.get.mockImplementation((path: string, _token: string, project: string) => {
			if (path.endsWith('/mcp-projects')) return Promise.resolve(availableProjects);
			if (path.includes('oauth')) return Promise.resolve([]);
			if (project === 'other') return bTokens.promise;
			aReads += 1;
			return Promise.resolve([{ ...activeToken, name: aReads === 1 ? 'Original A token' : 'Fresh A token' }]);
		});
		render(McpAccessSection);
		await screen.findByText('Original A token');
		await fireEvent.click(screen.getByRole('button', { name: t('mcp.revoke') }));
		setProject('other', 'Other project');
		await waitFor(() => expect(screen.queryByText('Original A token')).toBeNull());
		setProject('project', 'Project');
		await screen.findByText('Fresh A token');
		confirm.resolve(true);
		bTokens.resolve([{ ...activeToken, name: 'Late B token' }]);
		await waitFor(() => expect(screen.queryByText('Late B token')).toBeNull());
		expect(api.delete).not.toHaveBeenCalled();
		expect(screen.getByText('Fresh A token')).toBeTruthy();
	});

	it('clears a saved credential after a failed verification without retaining plaintext or leaking raw server detail', async () => {
		api.post.mockRejectedValue(new ApiError('MCP authentication failed'));
		render(McpAccessSection);
		const input = await screen.findByLabelText(t('mcp.tokenLabel')) as HTMLInputElement;
		await fireEvent.input(input, { target: { value: 'mcp-afgl-saved-private-key' } });
		await fireEvent.click(screen.getByRole('button', { name: t('mcp.verify') }));
		await screen.findByText(t('mcp.verifyError.unavailable'));
		expect(screen.queryByText('MCP authentication failed')).toBeNull();
		expect(input.value).toBe('');
		expect(document.body.textContent).not.toContain('mcp-afgl-saved-private-key');
	});

	it('checks a saved key with browser credentials for the current project and clears it on success', async () => {
		api.post.mockResolvedValue(connectionResult);
		render(McpAccessSection);
		const input = await screen.findByLabelText(t('mcp.tokenLabel')) as HTMLInputElement;
		await fireEvent.input(input, { target: { value: '  mcp-afgl-saved-private-key  ' } });
		await fireEvent.click(screen.getByRole('button', { name: t('mcp.verify') }));
		await screen.findByText(t('mcp.verified'));
		expect(api.post).toHaveBeenCalledWith('/api/v1/auth/mcp-tokens/verify', { token: 'mcp-afgl-saved-private-key' }, 'token', 'project', scopedPostOptions);
		expect(input.value).toBe('');
		expect(document.body.textContent).not.toContain('mcp-afgl-saved-private-key');
		expect(screen.getByText(t('mcp.verificationDetails', { name: 'Afterglow', version: '1.0', protocol: '2025-11-25', count: 5 }))).toBeTruthy();
		expect(screen.getByText(t('mcp.verificationLimit'))).toBeTruthy();
	});

	it.each([
		[400, 'invalid_request', 'invalidRequest'],
		[400, 'invalid_token', 'invalidToken'],
		[503, 'not_configured', 'notConfigured'],
		[502, 'rejected', 'rejected'],
		[502, 'redirect', 'redirect'],
		[502, 'protocol', 'protocol'],
		[504, 'unavailable', 'unavailable'],
		[429, undefined, 'rateLimited'],
	])('localizes verification failure %s/%s rather than displaying the server detail', async (status, code, key) => {
		api.post.mockRejectedValue(Object.assign(new ApiError('Raw server detail'), { status, code }));
		render(McpAccessSection);
		const input = await screen.findByLabelText(t('mcp.tokenLabel')) as HTMLInputElement;
		await fireEvent.input(input, { target: { value: 'mcp-afgl-foreign-key' } });
		await fireEvent.click(screen.getByRole('button', { name: t('mcp.verify') }));
		await screen.findByText(t(`mcp.verifyError.${key}` as Parameters<typeof t>[0]));
		expect(screen.queryByText('Raw server detail')).toBeNull();
		expect(input.value).toBe('');
	});

	it('drops an in-flight issued-key result when the one-time dialog closes', async () => {
		const verification = deferred<{ endpoint: string; protocol_version: string; server_name: string; server_version: string; tool_count: number }>();
		api.post.mockImplementation((path: string) => path.endsWith('/verify')
			? verification.promise
			: Promise.resolve({ ...activeToken, token: 'mcp-afgl-secret-value' }));
		render(McpAccessSection);
		await fireEvent.click(await createButton());
		await screen.findByText('mcp-afgl-secret-value');
		await fireEvent.click(screen.getAllByRole('button', { name: t('mcp.verify') }).find((button) => !button.hasAttribute('disabled'))!);
		const signal = api.post.mock.calls.at(-1)![4].signal as AbortSignal;
		expect(api.post.mock.calls.at(-1)![4]).toEqual(scopedPostOptions);
		await fireEvent.click(screen.getByRole('button', { name: t('mcp.done') }));
		expect(signal.aborted).toBe(true);
		await act(async () => {
			verification.resolve({ endpoint: 'https://mcp.example.test', protocol_version: '2025-11-25', server_name: 'Private client', server_version: '1.0', tool_count: 5 });
		});
		expect(screen.queryByText(t('mcp.verified'))).toBeNull();
		expect(document.body.textContent).not.toContain('mcp-afgl-secret-value');
	});

	it('discards verification state and credentials when the owning project changes', async () => {
		const verification = deferred<{ endpoint: string; protocol_version: string; server_name: string; server_version: string; tool_count: number }>();
		api.post.mockReturnValue(verification.promise);
		render(McpAccessSection);
		const input = await screen.findByLabelText(t('mcp.tokenLabel')) as HTMLInputElement;
		await fireEvent.input(input, { target: { value: 'mcp-afgl-old-project-key' } });
		await fireEvent.click(screen.getByRole('button', { name: t('mcp.verify') }));
		const signal = api.post.mock.calls[0][4].signal as AbortSignal;
		setProject('other', 'Other project');
		expect(signal.aborted).toBe(true);
		await waitFor(() => expect(input.value).toBe(''));
		await act(async () => {
			verification.resolve({ endpoint: 'https://mcp.example.test', protocol_version: '2025-11-25', server_name: 'Old project server', server_version: '1.0', tool_count: 5 });
		});
		expect(screen.queryByText(t('mcp.verified'))).toBeNull();
		expect(screen.queryByText(t('mcp.verifying'))).toBeNull();
	});

	it.each(['user', 'token', 'project-aba', 'logout', 'unverified', 'switching', 'disabled', 'unmount'] as const)('drops one-time issuance and saved credentials on %s transition', async (transition) => {
		const issuance = deferred<typeof activeToken & { token: string }>();
		api.post.mockReturnValue(issuance.promise);
		const view = render(McpAccessSection);
		await screen.findByText('Lumen');
		await fireEvent.input(screen.getByLabelText(t('mcp.tokenLabel')), { target: { value: 'private-saved-key' } });
		await fireEvent.click(await createButton());
		if (transition === 'user' || transition === 'token' || transition === 'project-aba') {
			api.get.mockImplementation((path: string) => Promise.resolve(accountResponse(path, [{ ...activeToken, name: 'New owner token' }])));
			if (transition === 'user') setAuth({ token: 'token', userId: 'other-user' });
			else if (transition === 'token') setAuth({ token: 'other-token' });
			else {
				setProject('other', 'Other project');
				setProject('project', 'Project');
			}
			await screen.findByText('New owner token');
		} else if (transition === 'logout') clearAuth();
		else if (transition === 'unmount') view.unmount();
		else if (transition === 'unverified') authReady.set(false);
		else if (transition === 'switching') projectSwitching.set(true);
		else siteConfig.update((config) => ({ ...config, services: { ...config.services, mcp: false } }));
		await waitFor(() => expect(screen.queryByText('Lumen')).toBeNull());
		expect((api.post.mock.calls[0][4].signal as AbortSignal).aborted).toBe(true);
		await act(async () => { issuance.resolve({ ...activeToken, token: 'late-issued-secret' }); });
		expect(screen.queryByRole('dialog')).toBeNull();
		expect(document.body.textContent).not.toContain('late-issued-secret');
		expect(document.body.textContent).not.toContain('private-saved-key');
		const input = screen.queryByLabelText(t('mcp.tokenLabel')) as HTMLInputElement | null;
		if (input) expect(input.value).toBe('');
	});

	it('clears issued secrets when unmounted and ignores a late verification result after remount', async () => {
		const verification = deferred<typeof connectionResult>();
		api.post.mockImplementation((path: string) => path.endsWith('/verify')
			? verification.promise
			: Promise.resolve({ ...activeToken, token: 'mcp-afgl-secret-value' }));
		const view = render(McpAccessSection);
		await fireEvent.click(await createButton());
		const dialog = await screen.findByRole('dialog', { name: t('mcp.newToken') });
		await fireEvent.click(within(dialog).getByRole('button', { name: t('mcp.verify') }));
		const signal = api.post.mock.calls.at(-1)![4].signal as AbortSignal;
		view.unmount();
		expect(signal.aborted).toBe(true);
		render(McpAccessSection);
		await act(async () => { verification.resolve(connectionResult); });
		expect(screen.queryByText(t('mcp.verified'))).toBeNull();
		expect(screen.queryByRole('dialog')).toBeNull();
		expect(document.body.textContent).not.toContain('mcp-afgl-secret-value');
	});
});
