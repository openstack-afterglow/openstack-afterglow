import { api } from './client';
import type { Project, ProjectAccessMember, AssignableProjectRoles } from '$lib/types/project';

export interface IamContext { domain_id: string; domain_name: string; is_domain_manager: boolean; is_system_admin: boolean }
export interface IamSession { token: () => string; domainId: string; userId: string; isCurrent: () => boolean; canSubmit: () => boolean }
export type IamAssignableRoles = AssignableProjectRoles;
export interface IamUser { id: string; name: string; email: string; enabled: boolean; domain_id: string; protected: boolean }
export interface IamUserWrite { name: string; email: string; enabled: boolean; password?: string; personal_domain_name?: string; project_id?: string; role_ids?: string[] }
export type IamEnrollmentStatus = 'delivery_pending' | 'pending' | 'accepted' | 'revoked' | 'expired' | 'delivery_failed' | 'account_creating' | 'granting' | 'activating' | 'recovery_required' | 'failed';
export interface IamInvitation { id: number; domain_id: string; kind: string; user_id: string | null; recovery_required: boolean; email: string; project_id: string | null; project_name: string; role_ids: string[]; status: IamEnrollmentStatus; expires_at: string; created_at: string; accepted_at: string | null }
export interface LoginPolicy { domain_id: string; password_enabled: boolean; allowed_email_domains: string[]; signup_enabled: boolean; signup_email_domains: string[]; revision: number; configured: boolean; smtp_configured: boolean; usable_provider_count: number }
export type LoginPolicyWrite = Pick<LoginPolicy, 'password_enabled' | 'allowed_email_domains' | 'signup_enabled' | 'signup_email_domains' | 'revision'>;
export interface IamProvider {
	id: string; domain_id: string; name: string; kind: 'oidc' | 'github'; enabled: boolean;
	issuer_url: string | null; client_id: string; scopes: string[];
	keystone_idp_id: string; keystone_protocol_id: string;
	federation_token_type: 'id_token' | 'access_token';
	token_endpoint_auth_method: 'client_secret_basic' | 'client_secret_post' | null;
	verified: boolean; verified_revision: number | null; verified_at: string | null;
	authorization_url: string | null; token_url: string | null; api_url: string | null;
	client_secret_configured: boolean; revision: number; created_at: string; updated_at: string;
}
export type ProviderWrite = Omit<IamProvider, 'id' | 'domain_id' | 'client_secret_configured' | 'created_at' | 'updated_at' | 'revision' | 'verified' | 'verified_revision' | 'verified_at' | 'authorization_url' | 'token_url' | 'api_url'> & Partial<Pick<IamProvider, 'authorization_url' | 'token_url' | 'api_url'>> & { client_secret?: string; revision?: number };
const root = '/api/v1/iam';
const id = encodeURIComponent;

// No tenant argument is accepted: every endpoint derives the domain from the server session.
export function domainIam(session: IamSession) {
	const projectId = undefined;
	// Check synchronously, including the interval before Svelte unmounts a revoked view.
	const dispatch = async <T>(send: () => Promise<T>): Promise<T> => {
		if (!session.isCurrent()) throw new DOMException('', 'AbortError');
		try {
			const result = await send();
			if (!session.isCurrent()) throw new DOMException('', 'AbortError');
			return result;
		} catch (cause) {
			if (!session.isCurrent()) throw new DOMException('', 'AbortError');
			throw cause;
		}
	};
	const mutate = <T>(send: () => Promise<T>) => {
		if (!session.canSubmit()) return Promise.reject<T>(new DOMException('', 'AbortError'));
		return dispatch(send);
	};
	const get = <T>(path: string) => dispatch(() => api.get<T>(root + path, session.token(), projectId, { refresh: true }));
	return {
		context: () => api.get<IamContext>(root + '/context', session.token(), projectId, { refresh: true }),
		users: () => get<{ items: IamUser[] }>('/users'),
		createUser: (body: IamUserWrite) => mutate(() => api.post<IamUser>(root + '/users', body, session.token(), projectId, { replayOnUnauthorized: false })),
		updateUser: (userId: string, body: Partial<IamUserWrite>) => mutate(() => api.patch<IamUser>(`${root}/users/${id(userId)}`, body, session.token(), projectId, { replayOnUnauthorized: false })),
		projects: () => get<{ items: Project[] }>('/projects'),
		members: (project: string) => get<{ items: ProjectAccessMember[] }>(`/projects/${id(project)}/members`),
		roles: (project: string) => get<IamAssignableRoles>(`/projects/${id(project)}/assignable-roles`),
		assignRoles: (project: string, user: string, roleIds: string[]) => mutate(() => api.put(`${root}/projects/${id(project)}/members/${id(user)}/roles`, { role_ids: roleIds }, session.token(), projectId, { replayOnUnauthorized: false })),
		removeMember: (project: string, user: string) => mutate(() => api.delete(`${root}/projects/${id(project)}/members/${id(user)}`, session.token(), projectId, { replayOnUnauthorized: false })),
		invitations: () => get<{ items: IamInvitation[] }>('/invitations'),
		invite: (email: string, project: string | undefined, roleIds: string[]) => mutate(() => api.post<IamInvitation>(root + '/invitations', { email, ...(project ? { project_id: project, role_ids: roleIds } : {}) }, session.token(), projectId, { replayOnUnauthorized: false })),
		revoke: (invitation: number) => mutate(() => api.delete(`${root}/invitations/${id(String(invitation))}`, session.token(), projectId, { replayOnUnauthorized: false })),
		operations: () => get<{ items: IamInvitation[] }>('/operations'),
		recoverOperation: (operation: number) => mutate(() => api.delete(`${root}/operations/${id(String(operation))}`, session.token(), projectId, { replayOnUnauthorized: false })),
		policy: () => get<LoginPolicy>('/login-policy'),
		savePolicy: (body: LoginPolicyWrite) => mutate(() => api.put<LoginPolicy>(root + '/login-policy', body, session.token(), projectId, { replayOnUnauthorized: false })),
		providers: () => get<{ items: IamProvider[] }>('/providers'),
		createProvider: (body: ProviderWrite) => mutate(() => api.post<IamProvider>(root + '/providers', body, session.token(), projectId, { replayOnUnauthorized: false })),
		updateProvider: (provider: string, body: Partial<ProviderWrite>) => mutate(() => api.patch<IamProvider>(`${root}/providers/${id(provider)}`, body, session.token(), projectId, { replayOnUnauthorized: false })),
		deleteProvider: (provider: string) => mutate(() => api.delete(`${root}/providers/${id(provider)}`, session.token(), projectId, { replayOnUnauthorized: false }))
	};
}
