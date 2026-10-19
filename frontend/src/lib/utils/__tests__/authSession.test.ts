import { describe, expect, it } from 'vitest';
import { get } from 'svelte/store';
import { auth, clearAuth, setAuth, setLoginAuth } from '$lib/stores/auth';
import { domainAuthState, loginAuthState, meAuthState, refreshAuthState, rescopeAuthState, sessionScopeKey, SessionDomainError, type SessionStateUpdate } from '../authSession';
import type { LoginResponse } from '$lib/types/auth';

const domains = [{ id: 'tenant-a', name: 'Tenant A' }, { id: 'tenant-b', name: 'Tenant B' }];
const login: LoginResponse = {
	token: 'access', refresh_token: 'refresh', user_id: 'user-1', username: 'alice',
	project_id: '', project_name: '', expires_at: null,
	domain_id: 'tenant-a', domain_name: 'Tenant A', identity_domain_id: 'tenant-a', identity_domain_name: 'Tenant A',
	is_domain_manager: true, available_domains: [domains[0]], can_create_domain: false,
};
const bound = { domainId: 'tenant-a', identityDomainId: 'tenant-a', userId: 'user-1', roles: [], refreshToken: 'refresh', isSystemAdmin: false };

function current() {
	clearAuth();
	setLoginAuth(loginAuthState({ ...login, available_domains: domains }, { federated: true }).state);
	return get(auth);
}

describe('identity and working-domain session binding', () => {
	it.each([false, true])('starts every fresh password/provider session at home and the domain chooser (provider=%s)', (federated) => {
		for (const available_domains of [[], [domains[0]], domains]) {
			for (const project_id of ['', 'default-a']) {
				const { state, target } = loginAuthState({ ...login, available_domains, project_id, project_name: 'Default' }, { federated });
				expect(target).toBe('/select-domain');
				expect(state).toMatchObject({ domainId: 'tenant-a', identityDomainId: 'tenant-a', isDomainManager: true,
					projectId: project_id || null, projectName: project_id ? 'Default' : null,
					isSystemAdmin: false, canCreateDomain: false, availableDomains: available_domains, federated });
			}
		}
	});

	it.each([false, true])('keeps a default-project hint projectless for password/provider authentication (provider=%s)', (federated) => {
		for (const available_domains of [[domains[0]], domains]) {
			const mapped = loginAuthState({ ...login, available_domains, project_id: ' ', project_name: 'Default', default_project_id: 'hint-only' }, { federated });
			expect(mapped.target).toBe('/select-domain');
			expect(mapped.state).toMatchObject({ projectId: null, projectName: null, federated });
		}
	});

	it.each([false, true])('rejects a fresh working domain outside canonical home or missing home metadata (provider=%s)', (federated) => {
		for (const data of [{ ...login, domain_id: 'tenant-b', available_domains: domains },
			{ ...login, identity_domain_id: '' }, { ...login, domain_id: '' }, { ...login, identity_domain_name: '' }]) {
			expect(() => loginAuthState(data, { federated })).toThrow(SessionDomainError);
		}
	});

	it.each(['rescope', 'refresh', 'me'] as const)('refuses implicit domain, identity or subject changes from %s', (kind) => {
		const map = (data: LoginResponse) => kind === 'rescope' ? rescopeAuthState(data, bound) : kind === 'refresh' ? refreshAuthState(data, bound) : meAuthState(data, bound);
		for (const data of [{ ...login, domain_id: 'tenant-b' }, { ...login, identity_domain_id: 'tenant-b' }, { ...login, user_id: 'other' }, { ...login, identity_domain_id: undefined }]) {
			expect(() => map(data)).toThrow(SessionDomainError);
		}
		expect(map({ ...login, is_domain_manager: false, can_create_domain: true, available_domains: domains })).toMatchObject({ isDomainManager: false, canCreateDomain: true, availableDomains: domains });
	});

	it.each(['refresh', 'me'] as const)('consumes authoritative project revocation from %s without rebinding the session', (kind) => {
		const previous = current();
		setAuth(domainAuthState({ ...login, domain_id: 'tenant-b', project_id: 'project-a', project_name: 'Project A', available_domains: domains }, previous, 'tenant-b'));
		const scoped = get(auth);
		const data = { ...login, token: 'rotated', domain_id: 'tenant-b', project_name: 'Stale project name', roles: [] };
		const update = kind === 'refresh' ? refreshAuthState(data, scoped) : meAuthState({ ...data, auth_method: 'federated' }, scoped);
		expect(update).toMatchObject({ projectId: null, projectName: null });
		if (kind === 'refresh') setAuth(update as SessionStateUpdate);
		else auth.update(state => ({ ...state, ...update }));
		expect(get(auth)).toMatchObject({ projectId: null, projectName: null, userId: previous.userId,
			identityDomainId: 'tenant-a', domainId: 'tenant-b', sessionId: previous.sessionId, federated: true });
		clearAuth();
	});

	it('clears both project fields when /me explicitly reports a null project', () => {
		expect(meAuthState({ ...login, project_id: null, project_name: 'Stale' }, { ...bound, projectId: 'project-a' }))
			.toMatchObject({ projectId: null, projectName: null });
	});

	it.each(['refresh', 'me'] as const)('retains omitted project metadata but updates authoritative same-project metadata from %s', (kind) => {
		const previous = current();
		setAuth({ token: previous.token!, projectId: 'project-a', projectName: 'Project A' });
		const scoped = get(auth);
		const map = (data: LoginResponse) => kind === 'refresh' ? refreshAuthState(data, scoped) : meAuthState(data, scoped);
		const omitted: Partial<LoginResponse> = { ...login };
		delete omitted.project_id;
		delete omitted.project_name;
		const update = map(omitted as LoginResponse);
		expect(update).not.toHaveProperty('projectId');
		expect(update).not.toHaveProperty('projectName');
		auth.update(state => ({ ...state, ...update }));
		expect(get(auth)).toMatchObject({ projectId: 'project-a', projectName: 'Project A' });
		expect(map({ ...login, project_id: 'project-a', project_name: 'Renamed' }))
			.toMatchObject({ projectId: 'project-a', projectName: 'Renamed' });
		clearAuth();
	});

	it.each(['refresh', 'me'] as const)('rejects unexpected nonempty project selection from %s', (kind) => {
		for (const projectId of [null, 'project-a']) {
			const scoped = { ...bound, projectId };
			const data = { ...login, project_id: 'project-b', project_name: 'Project B' };
			expect(() => kind === 'refresh' ? refreshAuthState(data, scoped) : meAuthState(data, scoped)).toThrow(SessionDomainError);
		}
		// Explicit rescope, unlike refresh and /me, is permitted to select a project.
		expect(rescopeAuthState({ ...login, project_id: 'project-b', project_name: 'Project B' }, bound))
			.toMatchObject({ projectId: 'project-b', projectName: 'Project B' });
	});

	it('publishes an explicit target switch without a new logical login or provider rebinding', () => {
		const previous = current();
		setAuth({ ...previous, token: previous.token!, projectId: 'project-a', availableProjects: [{ id: 'project-a', name: 'Old' }] });
		setAuth(domainAuthState({ ...login, token: 'target-access', domain_id: 'tenant-b', domain_name: 'Tenant B', project_id: 'default-b', project_name: 'Default', available_domains: domains }, get(auth), 'tenant-b'));
		expect(get(auth)).toMatchObject({ token: 'target-access', identityDomainId: 'tenant-a', domainId: 'tenant-b', projectId: 'default-b', availableProjects: [], federated: true, sessionId: previous.sessionId });
		clearAuth();
	});

	it('rejects unauthorized targets, foreign response targets, subjects and identities', () => {
		const previous = current();
		const response = { ...login, domain_id: 'tenant-b', available_domains: domains };
		for (const data of [{ ...response, domain_id: 'tenant-a' }, { ...response, user_id: 'other' }, { ...response, identity_domain_id: 'tenant-b' }]) {
			expect(() => domainAuthState(data, previous, 'tenant-b')).toThrow(SessionDomainError);
		}
		expect(() => domainAuthState(response, { ...previous, availableDomains: [domains[0]] }, 'tenant-b')).toThrow(SessionDomainError);
		expect(get(auth).token).toBe('access');
		clearAuth();
	});

	it('keeps scope ownership across token refresh but fences domain, identity and another login', () => {
		const previous = current();
		const owner = sessionScopeKey(previous);
		setAuth({ token: 'rotated' });
		expect(sessionScopeKey(get(auth))).toBe(owner);
		expect(sessionScopeKey({ ...previous, identityDomainId: 'other' })).not.toBe(owner);
		expect(sessionScopeKey({ ...previous, domainId: 'tenant-b' })).not.toBe(owner);
		setLoginAuth({ ...previous, token: 'new-login' });
		expect(sessionScopeKey(get(auth))).not.toBe(owner);
		clearAuth();
	});
});
