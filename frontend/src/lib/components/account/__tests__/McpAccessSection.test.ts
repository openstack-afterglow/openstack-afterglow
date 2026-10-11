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
const clock = '2028-01-31T23:45:12.345Z';
const defaultExpiry = '2028-02-29T23:45:12.345Z';
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
async function selectMethod(method: 'oauth' | 'api') {
	await fireEvent.click(screen.getByRole('button', { name: t(method === 'oauth' ? 'mcp.methodOAuth' : 'mcp.methodApiKey') }));
}

async function renderApi() {
	const view = render(McpAccessSection);
	await selectMethod('api');
	return view;
}

function configBlock(target: 'oauth' | 'setup' | 'config') {
	const block = document.querySelector(`[data-mcp-config="${target}"]`);
	expect(block).not.toBeNull();
	return block as HTMLElement;
}

function configJson(target: 'oauth' | 'setup' | 'config') {
	return JSON.parse(within(configBlock(target)).getByRole('region', { name: t(target === 'oauth' ? 'mcp.oauthConfig' : 'mcp.config') }).textContent!);
}

function clipboard(writeText = vi.fn().mockResolvedValue(undefined)) {
	Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } });
	return writeText;
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
		vi.useFakeTimers({ toFake: ['Date'] });
		vi.setSystemTime(new Date(clock));
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
		vi.useRealTimers();
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
		await renderApi();
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
		await renderApi();
		await createButton();
		const restriction = screen.getByRole('group', { name: t('mcp.savedRestrictions') });
		expect(within(restriction).getByText(t('mcp.savedAccess', { access: t('mcp.read') }))).toBeTruthy();
		expect(within(restriction).getByText(t('mcp.savedCurrentProject'))).toBeTruthy();
		expect(within(restriction).getByText(t('mcp.savedProjects', { projects: 'Saved home project (project)' }))).toBeTruthy();
		expect(within(restriction).queryByRole('combobox')).toBeNull();
		expect(within(restriction).queryByRole('checkbox')).toBeNull();
		await fireEvent.change(screen.getByLabelText(t('mcp.permission')), { target: { value: 'manage' } });
		await fireEvent.change(screen.getByLabelText(t('mcp.projects')), { target: { value: 'all' } });
		expect(within(restriction).getByText(t('mcp.savedAccess', { access: t('mcp.read') }))).toBeTruthy();
		expect(within(restriction).getByText(t('mcp.savedProjects', { projects: 'Saved home project (project)' }))).toBeTruthy();
		await selectMethod('oauth');
		const oauthRestriction = screen.getByRole('group', { name: t('mcp.savedRestrictions') });
		expect(within(oauthRestriction).getByText(t('mcp.savedAccess', { access: t('mcp.manage') }))).toBeTruthy();
		expect(within(oauthRestriction).getByText(t('mcp.savedAllProjects'))).toBeTruthy();
		expect(within(oauthRestriction).getByText(t('mcp.savedProjects', { projects: 'Saved other project (other)' }))).toBeTruthy();
		expect(within(oauthRestriction).queryByRole('combobox')).toBeNull();
		expect(within(oauthRestriction).queryByRole('checkbox')).toBeNull();
		expect(screen.getAllByRole('group', { name: t('mcp.savedRestrictions') })).toHaveLength(1);
	});

	it.each(['personal_token', 'oauth'] as const)('shows the explicit saved %s project set rather than current memberships or the creation draft', async (source) => {
		const record = {
			...activeToken, source, project_scope: 'selected', project_ids: ['saved-one', 'saved-two'],
			projects: [{ id: 'saved-one', name: 'Archived name' }, { id: 'saved-two', name: 'Other saved name' }],
		};
		api.get.mockImplementation((path: string) => Promise.resolve(path.endsWith('/mcp-projects') ? availableProjects
			: path.includes('oauth') ? source === 'oauth' ? [record] : [] : source === 'personal_token' ? [record] : []));
		await renderApi();
		await createButton();
		await fireEvent.click(projectCheckbox('other', 'Other project'));
		if (source === 'oauth') await selectMethod('oauth');
		const restriction = screen.getByRole('group', { name: t('mcp.savedRestrictions') });
		expect(within(restriction).getByText(t('mcp.savedSelectedProjects'))).toBeTruthy();
		expect(within(restriction).getByText(t('mcp.savedProjects', { projects: 'Archived name (saved-one), Other saved name (saved-two)' }))).toBeTruthy();
		expect(restriction.textContent).not.toContain('Other project (other)');
		await fireEvent.click(screen.getByRole('button', { name: t('mcp.refresh') }));
		await screen.findByRole('button', { name: t('mcp.refresh') });
		expect(screen.getByRole('group', { name: t('mcp.savedRestrictions') }).textContent).toContain('Archived name (saved-one), Other saved name (saved-two)');
	});

	it.each(['empty', 'missing'] as const)('does not invent saved project restrictions when metadata is %s', async (metadata) => {
		const record = { ...activeToken, projects: metadata === 'empty' ? [] : undefined };
		api.get.mockImplementation((path: string) => Promise.resolve(path.endsWith('/mcp-projects') ? availableProjects : path.includes('oauth') ? [] : [record]));
		await renderApi();
		await createButton();
		const restriction = screen.getByRole('group', { name: t('mcp.savedRestrictions') });
		expect(within(restriction).getByText(t('mcp.savedProjectsUnavailable'))).toBeTruthy();
		expect(restriction.textContent).not.toContain('Saved home project (project)');
		expect(restriction.textContent).not.toContain('Project (project)');
	});


	it('defaults to read access and the authoritative current project payload', async () => {
		await renderApi();
		await createButton();
		expect(api.get).toHaveBeenCalledWith('/api/v1/auth/mcp-projects', 'token', 'project', scopedGetOptions);
		expect(projectCheckbox('project', 'Project').checked).toBe(true);
		expect(projectCheckbox('other', 'Other project').checked).toBe(false);
		expect((screen.getByLabelText(t('mcp.permission')) as HTMLSelectElement).value).toBe('read');
		expect((screen.getByLabelText(t('mcp.expiry')) as HTMLSelectElement).value).toBe('1m');
		await fireEvent.click(await createButton());
		expect(api.post).toHaveBeenCalledWith('/api/v1/auth/mcp-tokens', {
			name: 'Lumen', access_level: 'read', project_scope: 'selected', project_ids: ['project'], expires_at: defaultExpiry,
		}, 'token', 'project', scopedPostOptions);
	});

	it('issues manage access for explicit projects without adding the home project implicitly', async () => {
		await renderApi();
		await createButton();
		await fireEvent.change(screen.getByLabelText(t('mcp.permission')), { target: { value: 'manage' } });
		await fireEvent.click(projectCheckbox('project', 'Project'));
		await fireEvent.click(projectCheckbox('other', 'Other project'));
		await fireEvent.input(screen.getByRole('textbox', { name: t('mcp.name') }), { target: { value: 'Explicit client' } });
		await fireEvent.click(await createButton());
		expect(api.post).toHaveBeenCalledWith('/api/v1/auth/mcp-tokens', {
			name: 'Explicit client', access_level: 'manage', project_scope: 'selected', project_ids: ['other'], expires_at: defaultExpiry,
		}, 'token', 'project', scopedPostOptions);
	});

	it('preserves an explicit multi-project payload', async () => {
		await renderApi();
		await createButton();
		await fireEvent.click(projectCheckbox('other', 'Other project'));
		await fireEvent.click(await createButton());
		expect(api.post).toHaveBeenCalledWith('/api/v1/auth/mcp-tokens', expect.objectContaining({
			project_scope: 'selected', project_ids: ['project', 'other'],
		}), 'token', 'project', scopedPostOptions);
	});

	it('keeps valid explicit choices after a successful authoritative reload', async () => {
		await renderApi();
		await createButton();
		await fireEvent.click(projectCheckbox('other', 'Other project'));
		await fireEvent.click(screen.getByRole('button', { name: t('mcp.refresh') }));
		await createButton();
		expect(projectCheckbox('project', 'Project').checked).toBe(true);
		expect(projectCheckbox('other', 'Other project').checked).toBe(true);
	});

	it('hides stale saved rows and discards previous project choices when collection reload fails', async () => {
		await renderApi();
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
		await renderApi();
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
		await renderApi();
		await createButton();
		await fireEvent.click(projectCheckbox('other', 'Other project'));
		await fireEvent.change(screen.getByLabelText(t('mcp.projects')), { target: { value: 'all' } });
		expect(screen.queryByRole('checkbox')).toBeNull();
		await fireEvent.click(await createButton());
		expect(api.post).toHaveBeenCalledWith('/api/v1/auth/mcp-tokens', {
			name: 'Lumen', access_level: 'read', project_scope: 'all', project_ids: [], expires_at: defaultExpiry,
		}, 'token', 'project', scopedPostOptions);
	});

	it('blocks empty explicit selection even when the form is submitted directly', async () => {
		await renderApi();
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
		await renderApi();
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
		await renderApi();
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
		await renderApi();
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
			await renderApi();
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
		const view = await renderApi();
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
			await renderApi();
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
		await renderApi();
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
		await renderApi();
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
		await renderApi();
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
		await renderApi();

		await createButton();
		await waitFor(() => expect(screen.getByText('Lumen 기본 토큰')).toBeTruthy());
		expect(screen.queryByText('mcp-afgl-secret-value')).toBeNull();
		expect(screen.getByRole('button', { name: 'Lumen 해제' })).toBeTruthy();
	});

	it('displays a newly issued token once after creation', async () => {
		await renderApi();
		await createButton();
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
		await renderApi();
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
		await renderApi();
		await fireEvent.click(await createButton());
		const dialog = await screen.findByRole('dialog', { name: t('mcp.newToken') });
		await fireEvent.click(within(dialog).getByRole('button', { name: t('mcp.done') }));
		await selectMethod('oauth');
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
		await renderApi();
		await createButton();
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
		await renderApi();
		await createButton();
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
		await renderApi();
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
		await renderApi();
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
		await renderApi();
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
		await renderApi();
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
		await renderApi();
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
		const view = await renderApi();
		await createButton();
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
		const view = await renderApi();
		await fireEvent.click(await createButton());
		const dialog = await screen.findByRole('dialog', { name: t('mcp.newToken') });
		await fireEvent.click(within(dialog).getByRole('button', { name: t('mcp.verify') }));
		const signal = api.post.mock.calls.at(-1)![4].signal as AbortSignal;
		view.unmount();
		expect(signal.aborted).toBe(true);
		await renderApi();
		await act(async () => { verification.resolve(connectionResult); });
		expect(screen.queryByText(t('mcp.verified'))).toBeNull();
		expect(screen.queryByRole('dialog')).toBeNull();
		expect(document.body.textContent).not.toContain('mcp-afgl-secret-value');
	});

	it('initially renders only OAuth setup and grants, then only the explicitly selected API setup and tokens', async () => {
		const grant = { ...activeToken, id: 'oauth-1', name: 'OAuth client', source: 'oauth', is_lumen_default: false };
		api.get.mockImplementation((path: string) => Promise.resolve(path.includes('oauth') ? [grant] : accountResponse(path)));
		render(McpAccessSection);
		await screen.findByText('OAuth client');
		const methods = screen.getByRole('group', { name: t('mcp.method') });
		expect(within(methods).getByRole('button', { name: t('mcp.methodOAuth') }).getAttribute('aria-pressed')).toBe('true');
		expect(within(methods).getByRole('button', { name: t('mcp.methodApiKey') }).getAttribute('aria-pressed')).toBe('false');
		expect(screen.getByRole('heading', { name: t('mcp.oauthSetupTitle') })).toBeTruthy();
		expect(screen.getByRole('heading', { name: t('mcp.oauth') })).toBeTruthy();
		expect(screen.queryByRole('heading', { name: t('mcp.personal') })).toBeNull();
		expect(screen.queryByLabelText(t('mcp.name'))).toBeNull();
		expect(screen.queryByLabelText(t('mcp.tokenLabel'))).toBeNull();
		expect(screen.queryByText('Lumen')).toBeNull();
		expect(screen.queryByRole('region', { name: t('mcp.config') })).toBeNull();
		expect(configJson('oauth')).toEqual({ mcpServers: { 'my-stream-server': { type: 'http', url: 'https://api.example.test/api/v1/mcp' } } });
		expect(api.post).not.toHaveBeenCalled();
		await selectMethod('api');
		await createButton();
		expect(within(methods).getByRole('button', { name: t('mcp.methodApiKey') }).getAttribute('aria-pressed')).toBe('true');
		expect(within(methods).getByRole('button', { name: t('mcp.methodOAuth') }).getAttribute('aria-pressed')).toBe('false');
		expect(screen.getByRole('heading', { name: t('mcp.personal') })).toBeTruthy();
		expect(screen.getByRole('heading', { name: t('mcp.setupTitle') })).toBeTruthy();
		expect(screen.getByLabelText(t('mcp.tokenLabel'))).toBeTruthy();
		expect(screen.getByText('Lumen')).toBeTruthy();
		expect(screen.queryByText('OAuth client')).toBeNull();
		expect(screen.queryByRole('heading', { name: t('mcp.oauth') })).toBeNull();
		expect(screen.queryByRole('region', { name: t('mcp.oauthConfig') })).toBeNull();
		expect(configJson('setup').mcpServers['my-stream-server'].headers.Authorization).toBe(['Bearer', 'YOUR_PERSONAL_MCP_TOKEN'].join(' '));
		await selectMethod('oauth');
		expect(screen.getByText('OAuth client')).toBeTruthy();
		expect(screen.queryByText('Lumen')).toBeNull();
		expect(screen.queryByRole('button', { name: t('mcp.create') })).toBeNull();
		expect(api.post).not.toHaveBeenCalled();
	});

	it.each([
		['1d', { expires_at: '2028-02-01T23:45:12.345Z' }],
		['1w', { expires_at: '2028-02-07T23:45:12.345Z' }],
		['1m', { expires_at: defaultExpiry }],
		['3m', { expires_at: '2028-04-30T23:45:12.345Z' }],
		['6m', { expires_at: '2028-07-31T23:45:12.345Z' }],
		['1y', { expires_at: '2029-01-31T23:45:12.345Z' }],
		['never', { non_expiring: true }],
		['custom', { expires_at: new Date(2028, 2, 15, 10, 20).toISOString() }],
	] as const)('posts the actual %s lifetime with mutually exclusive expiration fields', async (lifetime, expiration) => {
		await renderApi();
		await createButton();
		const select = screen.getByRole('combobox', { name: t('mcp.expiry') });
		expect(within(select).getAllByRole('option').map((option) => (option as HTMLOptionElement).value)).toEqual(['1d', '1w', '1m', '3m', '6m', '1y', 'never', 'custom']);
		await fireEvent.change(select, { target: { value: lifetime } });
		if (lifetime === 'custom') await fireEvent.input(screen.getByLabelText(t('mcp.customExpiry')), { target: { value: '2028-03-15T10:20' } });
		await fireEvent.click(await createButton());
		expect(api.post).toHaveBeenCalledExactlyOnceWith('/api/v1/auth/mcp-tokens', {
			name: 'Lumen', access_level: 'read', project_scope: 'selected', project_ids: ['project'], ...expiration,
		}, 'token', 'project', scopedPostOptions);
		const dialog = await screen.findByRole('dialog', { name: t('mcp.newToken') });
		await fireEvent.click(within(dialog).getByRole('button', { name: t('mcp.done') }));
		expect((screen.getByLabelText(t('mcp.expiry')) as HTMLSelectElement).value).toBe('1m');
		expect(screen.queryByLabelText(t('mcp.customExpiry'))).toBeNull();
	});

	it.each([
		['2027-01-31T00:15:42.123Z', '1m', '2027-02-28T00:15:42.123Z'],
		['2028-03-31T00:15:42.123Z', '3m', '2028-06-30T00:15:42.123Z'],
		['2027-08-31T00:15:42.123Z', '6m', '2028-02-29T00:15:42.123Z'],
		['2028-08-31T00:15:42.123Z', '6m', '2029-02-28T00:15:42.123Z'],
		['2028-02-29T00:15:42.123Z', '1y', '2029-02-28T00:15:42.123Z'],
	] as const)('clamps %s plus %s in the UTC calendar in the posted payload', async (now, lifetime, expires_at) => {
		vi.setSystemTime(new Date(now));
		await renderApi();
		await createButton();
		await fireEvent.change(screen.getByLabelText(t('mcp.expiry')), { target: { value: lifetime } });
		await fireEvent.click(await createButton());
		expect(api.post).toHaveBeenCalledExactlyOnceWith('/api/v1/auth/mcp-tokens', {
			name: 'Lumen', access_level: 'read', project_scope: 'selected', project_ids: ['project'], expires_at,
		}, 'token', 'project', scopedPostOptions);
	});

	it.each([
		['empty', ''],
		['invalid', 'not-a-date'],
		['past', '2027-12-31T12:00'],
	] as const)('rejects a %s custom expiry even on direct form submission', async (_kind, value) => {
		await renderApi();
		const button = await createButton();
		await fireEvent.change(screen.getByLabelText(t('mcp.expiry')), { target: { value: 'custom' } });
		await fireEvent.input(screen.getByLabelText(t('mcp.customExpiry')), { target: { value } });
		await fireEvent.submit(button.closest('form')!);
		await screen.findByText(t('mcp.invalidExpiry'));
		expect(api.post).not.toHaveBeenCalled();
		expect(screen.queryByRole('dialog')).toBeNull();
	});

	it('rejects a custom expiry equal to now', async () => {
		const now = new Date(2028, 0, 31, 12, 0);
		vi.setSystemTime(now);
		await renderApi();
		const button = await createButton();
		await fireEvent.change(screen.getByLabelText(t('mcp.expiry')), { target: { value: 'custom' } });
		await fireEvent.input(screen.getByLabelText(t('mcp.customExpiry')), { target: { value: '2028-01-31T12:00' } });
		await fireEvent.submit(button.closest('form')!);
		await screen.findByText(t('mcp.invalidExpiry'));
		expect(api.post).not.toHaveBeenCalled();
	});

	it('reveals the custom date field only for custom without issuing until submit or leaking it into a preset', async () => {
		await renderApi();
		await createButton();
		expect(screen.queryByLabelText(t('mcp.customExpiry'))).toBeNull();
		await fireEvent.change(screen.getByLabelText(t('mcp.expiry')), { target: { value: 'custom' } });
		await fireEvent.input(screen.getByLabelText(t('mcp.customExpiry')), { target: { value: '2028-05-01T10:20' } });
		expect(api.post).not.toHaveBeenCalled();
		expect(screen.queryByRole('dialog')).toBeNull();
		await fireEvent.change(screen.getByLabelText(t('mcp.expiry')), { target: { value: '1m' } });
		expect(screen.queryByLabelText(t('mcp.customExpiry'))).toBeNull();
		await fireEvent.click(await createButton());
		expect(api.post).toHaveBeenCalledExactlyOnceWith('/api/v1/auth/mcp-tokens', {
			name: 'Lumen', access_level: 'read', project_scope: 'selected', project_ids: ['project'], expires_at: defaultExpiry,
		}, 'token', 'project', scopedPostOptions);
	});

	it('clears issued secrets, saved credentials and successful verification when the method changes', async () => {
		api.post.mockImplementation((path: string) => Promise.resolve(path.endsWith('/verify') ? connectionResult : { ...activeToken, token: 'method-private-secret' }));
		await renderApi();
		await fireEvent.click(await createButton());
		const dialog = await screen.findByRole('dialog', { name: t('mcp.newToken') });
		await fireEvent.click(within(dialog).getByRole('button', { name: t('mcp.verify') }));
		await screen.findByText(t('mcp.verified'));
		await selectMethod('oauth');
		expect(screen.queryByRole('dialog')).toBeNull();
		expect(screen.queryByText(t('mcp.verified'))).toBeNull();
		expect(document.body.textContent).not.toContain('method-private-secret');
		await selectMethod('api');
		expect((screen.getByLabelText(t('mcp.tokenLabel')) as HTMLInputElement).value).toBe('');
		expect(screen.queryByText(t('mcp.verified'))).toBeNull();
		await fireEvent.input(screen.getByLabelText(t('mcp.tokenLabel')), { target: { value: 'saved-method-secret' } });
		await fireEvent.click(screen.getByRole('button', { name: t('mcp.verify') }));
		await screen.findByText(t('mcp.verified'));
		await selectMethod('oauth');
		await selectMethod('api');
		expect(screen.queryByRole('dialog')).toBeNull();
		expect(document.body.textContent).not.toContain('method-private-secret');
		expect(screen.queryByText(t('mcp.verified'))).toBeNull();
		await fireEvent.input(screen.getByLabelText(t('mcp.tokenLabel')), { target: { value: 'unverified-method-secret' } });
		await selectMethod('oauth');
		await selectMethod('api');
		expect((screen.getByLabelText(t('mcp.tokenLabel')) as HTMLInputElement).value).toBe('');
	});

	it.each(['success', 'failure'] as const)('fences a pending issuance %s through API→OAuth→API even after a newer issuance', async (outcome) => {
		const pending = deferred<typeof activeToken & { token: string }>();
		api.post.mockReturnValueOnce(pending.promise);
		await renderApi();
		await fireEvent.click(await createButton());
		const signal = api.post.mock.calls[0][4].signal as AbortSignal;
		await selectMethod('oauth');
		expect(signal.aborted).toBe(true);
		expect(screen.queryByRole('dialog')).toBeNull();
		await selectMethod('api');
		await fireEvent.click(await createButton());
		await screen.findByText('mcp-afgl-secret-value');
		await act(async () => {
			if (outcome === 'success') pending.resolve({ ...activeToken, token: 'stale-method-secret' });
			else pending.reject(new ApiError('Stale method issuance error'));
		});
		expect(screen.getByText('mcp-afgl-secret-value')).toBeTruthy();
		expect(document.body.textContent).not.toContain('stale-method-secret');
		expect(screen.queryByText('Stale method issuance error')).toBeNull();
	});

	describe.each(['saved', 'issued'] as const)('%s verification fences', (source) => {
		it.each(['method', 'method-aba', 'scope-aba', 'secret-aba'] as const)('discards late success and failure across %s', async (boundary) => {
			// A fresh verification must survive either outcome of the old request.
			for (const outcome of ['success', 'failure'] as const) {
				const pending = deferred<typeof connectionResult>();
				let verifies = 0;
				api.post.mockImplementation((path: string) => path.endsWith('/verify')
					? ++verifies === 1 ? pending.promise : Promise.resolve({ ...connectionResult, server_name: 'Current server' })
					: Promise.resolve({ ...activeToken, token: 'same-issued-secret' }));
				await renderApi();
				await createButton();
				if (source === 'issued') {
					await fireEvent.click(await createButton());
					const dialog = await screen.findByRole('dialog', { name: t('mcp.newToken') });
					await fireEvent.click(within(dialog).getByRole('button', { name: t('mcp.verify') }));
				} else {
					await fireEvent.input(screen.getByLabelText(t('mcp.tokenLabel')), { target: { value: 'same-saved-secret' } });
					await fireEvent.click(screen.getByRole('button', { name: t('mcp.verify') }));
				}
				const signal = api.post.mock.calls.at(-1)![4].signal as AbortSignal;
				if (boundary === 'method' || boundary === 'method-aba') {
					await selectMethod('oauth');
					if (boundary === 'method') {
						await act(async () => {
							if (outcome === 'success') pending.resolve({ ...connectionResult, server_name: 'Stale server' });
							else pending.reject(Object.assign(new ApiError('Private error'), { code: 'invalid_token' }));
						});
					}
					await selectMethod('api');
				} else if (boundary === 'scope-aba') {
					setProject('other', 'Other project');
					setProject('project', 'Project');
					await createButton();
				} else if (source === 'issued') {
					await fireEvent.click(screen.getByRole('button', { name: t('mcp.done') }));
				} else {
					// Closing an issued dialog clears the shared saved-verification generation too.
					await fireEvent.click(await createButton());
					await screen.findByRole('dialog', { name: t('mcp.newToken') });
					await fireEvent.click(screen.getByRole('button', { name: t('mcp.done') }));
				}
				expect(signal.aborted).toBe(true);
				expect(screen.queryByText(t('mcp.verified'))).toBeNull();
				expect(screen.queryByText(t('mcp.verifyError.invalidToken'))).toBeNull();
				if (source === 'issued') {
					await fireEvent.click(await createButton());
					const dialog = await screen.findByRole('dialog', { name: t('mcp.newToken') });
					await fireEvent.click(within(dialog).getByRole('button', { name: t('mcp.verify') }));
				} else {
					await fireEvent.input(screen.getByLabelText(t('mcp.tokenLabel')), { target: { value: 'same-saved-secret' } });
					await fireEvent.click(screen.getByRole('button', { name: t('mcp.verify') }));
				}
				await screen.findByText(t('mcp.verificationDetails', { name: 'Current server', version: '1.0', protocol: '2025-11-25', count: 5 }));
				if (boundary !== 'method') await act(async () => {
					if (outcome === 'success') pending.resolve({ ...connectionResult, server_name: 'Stale server' });
					else pending.reject(Object.assign(new ApiError('Private error'), { code: 'invalid_token' }));
				});
				expect(screen.getByText(t('mcp.verified'))).toBeTruthy();
				expect(screen.queryByText(t('mcp.verifyError.invalidToken'))).toBeNull();
				expect(document.body.textContent).not.toContain('Stale server');
				expect(document.body.textContent).not.toContain('Private error');
				cleanup();
				api.post.mockClear();
			}
		});
	});

	it('copies whole parseable JSON from each labeled JSON block, never its badge or controls', async () => {
		const writeText = clipboard();
		siteConfig.update((config) => ({ ...config, mcp_url: 'https://mcp.example.test/custom' }));
		render(McpAccessSection);
		await screen.findByRole('button', { name: t('mcp.copyOAuthConfig') });
		const oauth = configBlock('oauth');
		expect(within(oauth).getByText('mcp.json')).toBeTruthy();
		await fireEvent.click(within(oauth).getByRole('button', { name: t('mcp.copyOAuthConfig') }));
		await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
		expect(JSON.parse(writeText.mock.calls[0][0])).toEqual(configJson('oauth'));
		expect(JSON.parse(writeText.mock.calls[0][0])).toEqual({ mcpServers: { 'my-stream-server': { type: 'http', url: 'https://mcp.example.test/custom' } } });
		await selectMethod('api');
		await createButton();
		const setup = configBlock('setup');
		expect(within(setup).getByText('mcp.json')).toBeTruthy();
		await fireEvent.click(within(setup).getByRole('button', { name: t('mcp.copySetupConfig') }));
		await waitFor(() => expect(writeText).toHaveBeenCalledTimes(2));
		expect(JSON.parse(writeText.mock.calls[1][0])).toEqual(configJson('setup'));
		expect(JSON.parse(writeText.mock.calls[1][0])).toEqual({ mcpServers: { 'my-stream-server': { type: 'http', url: 'https://mcp.example.test/custom', headers: { Authorization: ['Bearer', 'YOUR_PERSONAL_MCP_TOKEN'].join(' ') } } } });
		await fireEvent.click(await createButton());
		const dialog = await screen.findByRole('dialog', { name: t('mcp.newToken') });
		const issued = configBlock('config');
		expect(within(issued).getByText('mcp.json')).toBeTruthy();
		await fireEvent.click(within(issued).getByRole('button', { name: t('mcp.copyConfig') }));
		await waitFor(() => expect(writeText).toHaveBeenCalledTimes(3));
		expect(JSON.parse(writeText.mock.calls[2][0])).toEqual(configJson('config'));
		expect(JSON.parse(writeText.mock.calls[2][0])).toEqual({ mcpServers: { 'my-stream-server': { type: 'http', url: 'https://mcp.example.test/custom', headers: { Authorization: ['Bearer', 'mcp-afgl-secret-value'].join(' ') } } } });
		await fireEvent.click(within(dialog).getByRole('button', { name: t('mcp.copy') }));
		await waitFor(() => expect(writeText).toHaveBeenCalledTimes(4));
		expect(writeText.mock.calls[3][0]).toBe('mcp-afgl-secret-value');
	});

	describe.each(['oauth', 'setup', 'token', 'config'] as const)('%s clipboard feedback', (target) => {
		const copyKey = { oauth: 'mcp.copyOAuthConfig', setup: 'mcp.copySetupConfig', token: 'mcp.copy', config: 'mcp.copyConfig' } as const;

		async function openTarget() {
			if (target === 'oauth') render(McpAccessSection);
			else {
				await renderApi();
				await createButton();
				if (target === 'token' || target === 'config') {
					await fireEvent.click(await createButton());
					await screen.findByRole('dialog', { name: t('mcp.newToken') });
				}
			}
		}

		function targetScope() {
			return target === 'token' ? screen.getByRole('dialog', { name: t('mcp.newToken') }) : configBlock(target);
		}

		it.each(['success', 'failure'] as const)('keeps %s feedback local to the clicked control and allows retry', async (outcome) => {
			const writeText = clipboard();
			if (outcome === 'failure') writeText.mockRejectedValueOnce(new Error('Private clipboard failure'));
			await openTarget();
			const scope = targetScope();
			const button = within(scope).getByRole('button', { name: t(copyKey[target]) });
			await fireEvent.click(button);
			if (outcome === 'success') {
				await waitFor(() => expect(button.textContent).toContain(t('mcp.copied')));
				expect(screen.getAllByRole('button', { name: t('mcp.copied') })).toHaveLength(1);
				expect(screen.queryByText(t('mcp.copyFailed'))).toBeNull();
			} else {
				const failure = await within(scope).findByText(t('mcp.copyFailed'));
				expect(failure.getAttribute('role')).toBe('alert');
				expect(screen.getAllByText(t('mcp.copyFailed'))).toHaveLength(1);
				expect(screen.queryByRole('button', { name: t('mcp.copied') })).toBeNull();
				expect(button.textContent).toContain(t(copyKey[target]));
				expect(document.body.textContent).not.toContain('Private clipboard failure');
			}
			if (target === 'config') expect(within(screen.getByRole('dialog')).getByRole('button', { name: t('mcp.copy') })).toBeTruthy();
			if (target === 'token') expect(within(configBlock('config')).getByRole('button', { name: t('mcp.copyConfig') })).toBeTruthy();
			if (target === 'token' || target === 'config') {
				expect(within(configBlock('setup')).queryByText(t('mcp.copyFailed'))).toBeNull();
				expect(within(configBlock('setup')).getByRole('button', { name: t('mcp.copySetupConfig') })).toBeTruthy();
			}
			await fireEvent.click(button);
			await waitFor(() => expect(writeText).toHaveBeenCalledTimes(2));
			await waitFor(() => expect(button.textContent).toContain(t('mcp.copied')));
			expect(screen.queryByText(t('mcp.copyFailed'))).toBeNull();
		});

		it.each((['method-aba', 'scope-aba', 'endpoint'] as const).filter((boundary) => target !== 'token' || boundary !== 'endpoint'))('ignores delayed success and failure across %s even with identical final content', async (boundary) => {
			for (const outcome of ['success', 'failure'] as const) {
				const pending = deferred<void>();
				const writeText = clipboard(vi.fn().mockReturnValueOnce(pending.promise).mockResolvedValue(undefined));
				await openTarget();
				await fireEvent.click(within(targetScope()).getByRole('button', { name: t(copyKey[target]) }));
				expect(writeText).toHaveBeenCalledOnce();
				if (boundary === 'method-aba') {
					await selectMethod(target === 'oauth' ? 'api' : 'oauth');
					await selectMethod(target === 'oauth' ? 'oauth' : 'api');
				} else if (boundary === 'scope-aba') {
					setProject('other', 'Other project');
					setProject('project', 'Project');
					await screen.findByRole('button', { name: t('mcp.refresh') });
				} else {
					siteConfig.update((config) => ({ ...config, mcp_url: 'https://changed.example.test/mcp' }));
					await act(async () => {});
				}
				if (boundary !== 'endpoint' && (target === 'token' || target === 'config')) {
					await fireEvent.click(await createButton());
					await screen.findByRole('dialog', { name: t('mcp.newToken') });
				}
				const scope = targetScope();
				expect(within(scope).queryByRole('button', { name: t('mcp.copied') })).toBeNull();
				await act(async () => {
					if (outcome === 'success') pending.resolve();
					else pending.reject(new Error('Stale clipboard error'));
				});
				expect(within(scope).queryByRole('button', { name: t('mcp.copied') })).toBeNull();
				expect(screen.queryByText(t('mcp.copyFailed'))).toBeNull();
				expect(document.body.textContent).not.toContain('Stale clipboard error');
				await fireEvent.click(within(scope).getByRole('button', { name: t(copyKey[target]) }));
				await within(scope).findByRole('button', { name: t('mcp.copied') });
				cleanup();
				siteConfig.update((config) => ({ ...config, mcp_url: '' }));
			}
		});
	});

	describe.each(['token', 'config'] as const)('%s secret-bound clipboard', (target) => {
		it.each(['changed', 'aba'] as const)('discards delayed results after a %s one-time secret, preserving a newer copy', async (boundary) => {
			for (const outcome of ['success', 'failure'] as const) {
				const pending = deferred<void>();
				const writeText = clipboard(vi.fn().mockReturnValueOnce(pending.promise).mockResolvedValue(undefined));
				api.post.mockResolvedValueOnce({ ...activeToken, token: 'first-secret' })
					.mockResolvedValue({ ...activeToken, token: boundary === 'aba' ? 'first-secret' : 'replacement-secret' });
				await renderApi();
				await fireEvent.click(await createButton());
				let dialog = await screen.findByRole('dialog', { name: t('mcp.newToken') });
				await fireEvent.click(within(dialog).getByRole('button', { name: t(target === 'token' ? 'mcp.copy' : 'mcp.copyConfig') }));
				await fireEvent.click(within(dialog).getByRole('button', { name: t('mcp.done') }));
				await fireEvent.click(await createButton());
				dialog = await screen.findByRole('dialog', { name: t('mcp.newToken') });
				expect(within(dialog).queryByRole('button', { name: t('mcp.copied') })).toBeNull();
				const button = within(dialog).getByRole('button', { name: t(target === 'token' ? 'mcp.copy' : 'mcp.copyConfig') });
				await fireEvent.click(button);
				await waitFor(() => expect(button.textContent).toContain(t('mcp.copied')));
				const secret = boundary === 'aba' ? 'first-secret' : 'replacement-secret';
				expect(target === 'token' ? writeText.mock.calls[1][0] : JSON.parse(writeText.mock.calls[1][0]).mcpServers['my-stream-server'].headers.Authorization).toBe(target === 'token' ? secret : ['Bearer', secret].join(' '));
				await act(async () => {
					if (outcome === 'success') pending.resolve();
					else pending.reject(new Error('Old secret clipboard error'));
				});
				expect(button.textContent).toContain(t('mcp.copied'));
				expect(screen.queryByText(t('mcp.copyFailed'))).toBeNull();
				expect(document.body.textContent).not.toContain('Old secret clipboard error');
				cleanup();
			}
		});
	});

	it('keeps overlapping raw-token and issued-JSON clipboard outcomes independent', async () => {
		const raw = deferred<void>();
		const json = deferred<void>();
		clipboard(vi.fn().mockReturnValueOnce(raw.promise).mockReturnValueOnce(json.promise));
		await renderApi();
		await fireEvent.click(await createButton());
		const dialog = await screen.findByRole('dialog', { name: t('mcp.newToken') });
		const tokenButton = within(dialog).getByRole('button', { name: t('mcp.copy') });
		const configButton = within(configBlock('config')).getByRole('button', { name: t('mcp.copyConfig') });
		await fireEvent.click(tokenButton);
		await fireEvent.click(configButton);
		await act(async () => { json.resolve(); });
		expect(configButton.textContent).toContain(t('mcp.copied'));
		expect(tokenButton.textContent).toContain(t('mcp.copy'));
		await act(async () => { raw.reject(new Error('Clipboard denied')); });
		expect(within(dialog).getByText(t('mcp.copyFailed')).getAttribute('role')).toBe('alert');
		expect(within(configBlock('config')).queryByText(t('mcp.copyFailed'))).toBeNull();
		expect(configButton.textContent).toContain(t('mcp.copied'));
		expect(tokenButton.textContent).toContain(t('mcp.copy'));
	});

	it.each(['old-success', 'old-failure'] as const)('keeps a newer copy outcome when an overlapping %s arrives', async (outcome) => {
		const old = deferred<void>();
		const writeText = clipboard(vi.fn().mockReturnValueOnce(old.promise));
		if (outcome === 'old-success') writeText.mockRejectedValueOnce(new Error('Current clipboard failure'));
		else writeText.mockResolvedValueOnce(undefined);
		render(McpAccessSection);
		const button = await screen.findByRole('button', { name: t('mcp.copyOAuthConfig') });
		await fireEvent.click(button);
		await fireEvent.click(button);
		if (outcome === 'old-success') await screen.findByText(t('mcp.copyFailed'));
		else await waitFor(() => expect(button.textContent).toContain(t('mcp.copied')));
		await act(async () => {
			if (outcome === 'old-success') old.resolve();
			else old.reject(new Error('Old clipboard failure'));
		});
		if (outcome === 'old-success') {
			expect(screen.getByText(t('mcp.copyFailed'))).toBeTruthy();
			expect(button.textContent).toContain(t('mcp.copyOAuthConfig'));
		} else {
			expect(screen.queryByText(t('mcp.copyFailed'))).toBeNull();
			expect(button.textContent).toContain(t('mcp.copied'));
		}
	});

	describe.each(['set-default', 'clear-default', 'revoke-token', 'revoke-oauth'] as const)('%s action', (action) => {
		const record = { ...activeToken, id: 'token/one', grant_id: 'grant/one', name: 'Action client', is_lumen_default: action === 'clear-default' };
		const label = { 'set-default': 'mcp.setLumen', 'clear-default': 'mcp.clearLumen', 'revoke-token': 'mcp.revoke', 'revoke-oauth': 'mcp.revokeAccess' } as const;
		const errorKey = { 'set-default': 'mcp.selectFailed', 'clear-default': 'mcp.clearFailed', 'revoke-token': 'mcp.revokeFailed', 'revoke-oauth': 'mcp.revokeOAuthFailed' } as const;
		const path = action === 'set-default' ? '/api/v1/auth/mcp-tokens/token%2Fone/lumen-default'
			: action === 'clear-default' ? '/api/v1/auth/mcp-tokens/lumen-default'
				: action === 'revoke-token' ? '/api/v1/auth/mcp-tokens/token%2Fone' : '/api/v1/auth/mcp-oauth/grants/grant%2Fone';

		async function openAction() {
			if (action === 'revoke-oauth') render(McpAccessSection);
			else await renderApi();
			await screen.findByText(record.name);
			return screen.getByRole('button', { name: t(label[action]) });
		}

		it('sends the scoped mutation and renders the authoritative reload', async () => {
			let rows = [record];
			api.get.mockImplementation((path: string) => Promise.resolve(path.endsWith('/mcp-projects') ? availableProjects
				: path.includes('oauth') ? action === 'revoke-oauth' ? rows : [] : action === 'revoke-oauth' ? [] : rows));
			const mutation = deferred<void>();
			const mutate = () => mutation.promise.then(() => {
				rows = action === 'set-default' || action === 'clear-default' ? [{ ...record, is_lumen_default: action === 'set-default' }] : [];
			});
			api.put.mockImplementation(mutate);
			api.delete.mockImplementation(mutate);
			await fireEvent.click(await openAction());
			await waitFor(() => {
				if (action === 'set-default') expect(api.put).toHaveBeenCalledExactlyOnceWith(path, {}, 'token', 'project');
				else expect(api.delete).toHaveBeenCalledExactlyOnceWith(path, 'token', 'project');
			});
			if (action.startsWith('revoke')) expect(confirmDialog).toHaveBeenCalledExactlyOnceWith(t(action === 'revoke-oauth' ? 'mcp.revokeOAuthConfirm' : 'mcp.revokeConfirm', { name: record.name }));
			else expect(confirmDialog).not.toHaveBeenCalled();
			for (const button of screen.getAllByRole('button', { name: t(label[action]) })) expect(button.hasAttribute('disabled')).toBe(true);
			await act(async () => { mutation.resolve(); });
			if (action === 'set-default') await screen.findByRole('button', { name: t('mcp.clearLumen') });
			else if (action === 'clear-default') await screen.findByRole('button', { name: t('mcp.setLumen') });
			else {
				await screen.findByText(t(action === 'revoke-oauth' ? 'mcp.emptyOAuth' : 'mcp.emptyTokens'));
				expect(screen.queryByText(record.name)).toBeNull();
			}
			expect(api.get).toHaveBeenCalledWith(action === 'revoke-oauth' ? '/api/v1/auth/mcp-oauth/grants' : '/api/v1/auth/mcp-tokens', 'token', 'project', scopedGetOptions);
		});

		it('keeps the record and localizes a failed mutation', async () => {
			api.get.mockImplementation((path: string) => Promise.resolve(path.endsWith('/mcp-projects') ? availableProjects
				: path.includes('oauth') ? action === 'revoke-oauth' ? [record] : [] : action === 'revoke-oauth' ? [] : [record]));
			api.put.mockRejectedValue(new Error('Private mutation detail'));
			api.delete.mockRejectedValue(new Error('Private mutation detail'));
			await fireEvent.click(await openAction());
			await screen.findByText(t(errorKey[action]));
			expect(screen.getByText(record.name)).toBeTruthy();
			expect(screen.getByRole('button', { name: t(label[action]) }).hasAttribute('disabled')).toBe(false);
			expect(document.body.textContent).not.toContain('Private mutation detail');
		});
	});

	it.each(['personal_token', 'oauth'] as const)('does not revoke %s access when confirmation is canceled', async (source) => {
		confirmDialog.mockResolvedValue(false);
		const record = { ...activeToken, source, name: 'Canceled client' };
		api.get.mockImplementation((path: string) => Promise.resolve(path.endsWith('/mcp-projects') ? availableProjects
			: path.includes('oauth') ? source === 'oauth' ? [record] : [] : source === 'personal_token' ? [record] : []));
		if (source === 'oauth') render(McpAccessSection);
		else await renderApi();
		await screen.findByText(record.name);
		await fireEvent.click(screen.getByRole('button', { name: t(source === 'oauth' ? 'mcp.revokeAccess' : 'mcp.revoke') }));
		expect(confirmDialog).toHaveBeenCalledOnce();
		expect(api.delete).not.toHaveBeenCalled();
		expect(screen.getByText(record.name)).toBeTruthy();
	});

	it('discards an OAuth revoke confirmation across an A→B→A scope change', async () => {
		const confirmation = deferred<boolean>();
		confirmDialog.mockReturnValue(confirmation.promise);
		let generation = 'Old';
		api.get.mockImplementation((path: string) => Promise.resolve(path.endsWith('/mcp-projects') ? availableProjects
			: path.includes('oauth') ? [{ ...activeToken, source: 'oauth', name: `${generation} OAuth client` }] : []));
		render(McpAccessSection);
		await screen.findByText('Old OAuth client');
		await fireEvent.click(screen.getByRole('button', { name: t('mcp.revokeAccess') }));
		generation = 'Current';
		setProject('other', 'Other project');
		setProject('project', 'Project');
		await screen.findByText('Current OAuth client');
		await act(async () => { confirmation.resolve(true); });
		expect(api.delete).not.toHaveBeenCalled();
		expect(screen.getByText('Current OAuth client')).toBeTruthy();
	});

	it.each(['expired', 'revoked'] as const)('does not offer a %s token as the Lumen default but leaves revoke reachable', async (status) => {
		api.get.mockImplementation((path: string) => Promise.resolve(accountResponse(path, [{ ...activeToken, status, is_lumen_default: false }])));
		await renderApi();
		await createButton();
		expect(screen.getByRole('button', { name: t('mcp.setLumen') }).hasAttribute('disabled')).toBe(true);
		expect(screen.getByRole('button', { name: t('mcp.revoke') }).hasAttribute('disabled')).toBe(false);
		expect(api.put).not.toHaveBeenCalled();
	});

	it.each(['personal_token', 'oauth'] as const)('discards a delayed %s revoke confirmation across method ABA', async (source) => {
		const confirmation = deferred<boolean>();
		confirmDialog.mockReturnValue(confirmation.promise);
		const record = { ...activeToken, source, name: 'Method-fenced client' };
		api.get.mockImplementation((path: string) => Promise.resolve(path.endsWith('/mcp-projects') ? availableProjects
			: path.includes('oauth') ? source === 'oauth' ? [record] : [] : source === 'personal_token' ? [record] : []));
		if (source === 'oauth') render(McpAccessSection);
		else await renderApi();
		await screen.findByText(record.name);
		await fireEvent.click(screen.getByRole('button', { name: t(source === 'oauth' ? 'mcp.revokeAccess' : 'mcp.revoke') }));
		await selectMethod(source === 'oauth' ? 'api' : 'oauth');
		await selectMethod(source === 'oauth' ? 'oauth' : 'api');
		expect(screen.getByText(record.name)).toBeTruthy();
		await act(async () => { confirmation.resolve(true); });
		expect(api.delete).not.toHaveBeenCalled();
		expect(screen.getByText(record.name)).toBeTruthy();
	});

	it.each(['set-default', 'clear-default', 'revoke-token', 'revoke-oauth'] as const)('does not publish a late %s failure after method ABA', async (action) => {
		const mutation = deferred<void>();
		const record = { ...activeToken, name: 'Pending action client', is_lumen_default: action === 'clear-default' };
		api.get.mockImplementation((path: string) => Promise.resolve(path.endsWith('/mcp-projects') ? availableProjects
			: path.includes('oauth') ? action === 'revoke-oauth' ? [record] : [] : action === 'revoke-oauth' ? [] : [record]));
		api.put.mockReturnValue(mutation.promise);
		api.delete.mockReturnValue(mutation.promise);
		if (action === 'revoke-oauth') render(McpAccessSection);
		else await renderApi();
		await screen.findByText(record.name);
		const label = { 'set-default': 'mcp.setLumen', 'clear-default': 'mcp.clearLumen', 'revoke-token': 'mcp.revoke', 'revoke-oauth': 'mcp.revokeAccess' } as const;
		await fireEvent.click(screen.getByRole('button', { name: t(label[action]) }));
		await waitFor(() => expect(action === 'set-default' ? api.put : api.delete).toHaveBeenCalledOnce());
		await selectMethod(action === 'revoke-oauth' ? 'api' : 'oauth');
		await selectMethod(action === 'revoke-oauth' ? 'oauth' : 'api');
		await act(async () => { mutation.reject(new ApiError('Late method mutation error')); });
		expect(screen.queryByText('Late method mutation error')).toBeNull();
		expect(screen.getByText(record.name)).toBeTruthy();
		expect(screen.getByRole('button', { name: t(label[action]) }).hasAttribute('disabled')).toBe(false);
	});

	it('keeps saved lists and the explicit API project draft across a method change while clearing action feedback', async () => {
		await renderApi();
		const button = await createButton();
		await fireEvent.click(projectCheckbox('project', 'Project'));
		await fireEvent.click(projectCheckbox('other', 'Other project'));
		await fireEvent.change(screen.getByLabelText(t('mcp.permission')), { target: { value: 'manage' } });
		await fireEvent.input(screen.getByRole('textbox', { name: t('mcp.name') }), { target: { value: 'Draft client' } });
		await fireEvent.change(screen.getByLabelText(t('mcp.expiry')), { target: { value: 'custom' } });
		await fireEvent.submit(button.closest('form')!);
		await screen.findByText(t('mcp.invalidExpiry'));
		const reads = api.get.mock.calls.length;
		await selectMethod('oauth');
		await selectMethod('api');
		expect(api.get).toHaveBeenCalledTimes(reads);
		expect(screen.getByText('Lumen')).toBeTruthy();
		expect(projectCheckbox('project', 'Project').checked).toBe(false);
		expect(projectCheckbox('other', 'Other project').checked).toBe(true);
		expect((screen.getByRole('textbox', { name: t('mcp.name') }) as HTMLInputElement).value).toBe('Draft client');
		expect((screen.getByLabelText(t('mcp.permission')) as HTMLSelectElement).value).toBe('manage');
		expect(screen.queryByText(t('mcp.invalidExpiry'))).toBeNull();
	});

	it('retains the explicitly selected API method on auth reset but drops creation and verification drafts', async () => {
		await renderApi();
		await createButton();
		await fireEvent.click(projectCheckbox('other', 'Other project'));
		await fireEvent.input(screen.getByRole('textbox', { name: t('mcp.name') }), { target: { value: 'Old owner draft' } });
		await fireEvent.change(screen.getByLabelText(t('mcp.permission')), { target: { value: 'manage' } });
		await fireEvent.change(screen.getByLabelText(t('mcp.expiry')), { target: { value: 'custom' } });
		await fireEvent.input(screen.getByLabelText(t('mcp.customExpiry')), { target: { value: '2028-05-01T10:00' } });
		await fireEvent.input(screen.getByLabelText(t('mcp.tokenLabel')), { target: { value: 'old-owner-private-key' } });
		setAuth({ token: 'new-token' });
		await createButton();
		expect(screen.getByRole('button', { name: t('mcp.methodApiKey') }).getAttribute('aria-pressed')).toBe('true');
		expect((screen.getByRole('textbox', { name: t('mcp.name') }) as HTMLInputElement).value).toBe('Lumen');
		expect((screen.getByLabelText(t('mcp.permission')) as HTMLSelectElement).value).toBe('read');
		expect((screen.getByLabelText(t('mcp.expiry')) as HTMLSelectElement).value).toBe('1m');
		expect(screen.queryByLabelText(t('mcp.customExpiry'))).toBeNull();
		expect((screen.getByLabelText(t('mcp.tokenLabel')) as HTMLInputElement).value).toBe('');
		expect(projectCheckbox('project', 'Project').checked).toBe(true);
		expect(projectCheckbox('other', 'Other project').checked).toBe(false);
	});

	it('labels a saved non-expiring personal token explicitly', async () => {
		const record = { ...activeToken, expires_at: null };
		api.get.mockImplementation((path: string) => Promise.resolve(path.endsWith('/mcp-projects') ? availableProjects
			: path.includes('oauth') ? [] : [record]));
		await renderApi();
		await screen.findByText(t('mcp.recordDetails', { prefix: activeToken.visible_prefix, access: t('mcp.read'), lastUsed: '—', expires: t('mcp.expiryNever') }));
	});
});
