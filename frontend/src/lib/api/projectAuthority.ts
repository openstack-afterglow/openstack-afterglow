import { api } from './client';
import type { IamSession } from './domainIam';
import type { EligibleProjectUser, ProjectOwnership, ProjectCreators, Project, ProjectAccessMember, AssignableProjectRoles } from '$lib/types/project';

// Native lifecycle writes must never be replayed after an uncertain response or 401.
export function projectAuthority(session: IamSession, callerProject?: string) {
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
	const root = (project: string) => `/api/v1/projects/${encodeURIComponent(project)}`;
	return {
		projects: () => dispatch(() => api.get<{ items: Project[] }>(`/api/v1/projects?domain_id=${encodeURIComponent(session.domainId)}`, session.token(), callerProject, { cache: 'no-store' })),
		members: (project: string) => dispatch(() => api.get<{ items: ProjectAccessMember[] }>(`${root(project)}/members`, session.token(), callerProject, { cache: 'no-store' })),
		roles: (project: string) => dispatch(() => api.get<AssignableProjectRoles>(`${root(project)}/assignable-roles`, session.token(), callerProject, { cache: 'no-store' })),
		assignRoles: (project: string, user: string, roleIds: string[]) => {
			if (!session.canSubmit()) return Promise.reject(new DOMException('', 'AbortError'));
			return dispatch(() => api.put(`${root(project)}/members/${encodeURIComponent(user)}/roles`, { role_ids: roleIds }, session.token(), callerProject, { replayOnUnauthorized: false }));
		},
		removeMember: (project: string, user: string) => {
			if (!session.canSubmit()) return Promise.reject(new DOMException('', 'AbortError'));
			return dispatch(() => api.delete(`${root(project)}/members/${encodeURIComponent(user)}`, session.token(), callerProject, { replayOnUnauthorized: false }));
		},
		create: (name: string, description: string) => {
			if (!session.canSubmit()) return Promise.reject<{ id: string; name: string }>(new DOMException('', 'AbortError'));
			return dispatch(() => api.post<{ id: string; name: string }>('/api/v1/projects', { name, description, domain_id: session.domainId }, session.token(), callerProject, { replayOnUnauthorized: false, suppressAuthRedirect: true, cache: 'no-store' }));
		},
		eligibleUsers: (project: string) => dispatch(() => api.get<EligibleProjectUser[]>(`${root(project)}/eligible-users`, session.token(), callerProject, { refresh: true })),
		ownership: (project: string) => dispatch(() => api.get<ProjectOwnership>(`${root(project)}/ownership`, session.token(), callerProject, { refresh: true })),
		creators: () => dispatch(() => api.get<ProjectCreators>(`/api/v1/projects/creators?domain_id=${encodeURIComponent(session.domainId)}`, session.token(), callerProject, { refresh: true })),
		setCreator: (user: string, enabled: boolean) => {
			if (!session.canSubmit()) return Promise.reject<ProjectCreators>(new DOMException('', 'AbortError'));
			return dispatch(() => api.put<ProjectCreators>(`/api/v1/projects/creators/${encodeURIComponent(user)}`, { domain_id: session.domainId, enabled }, session.token(), callerProject, { replayOnUnauthorized: false }));
		},
		transfer: (project: string, user: string) => {
			if (!session.canSubmit()) return Promise.reject<ProjectOwnership>(new DOMException('', 'AbortError'));
			return dispatch(() => api.post<ProjectOwnership>(`${root(project)}/ownership-transfer`, { user_id: user }, session.token(), callerProject, { replayOnUnauthorized: false }));
		}
	};
}
