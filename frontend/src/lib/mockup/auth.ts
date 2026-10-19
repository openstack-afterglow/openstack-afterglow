import type { AuthState } from '$lib/stores/auth';
import type { MockupProfileId } from '$lib/mockup/contracts';

// Synthetic tutorial domain; never a real Keystone identity.
const MOCK_DOMAIN = {
	domainId: 'mock-domain', domainName: 'Demo',
	identityDomainId: 'mock-domain', identityDomainName: 'Demo',
	availableDomains: [{ id: 'mock-domain', name: 'Demo' }],
	canCreateDomain: false, isDomainManager: false,
};

const MOCK_EXPIRES_AT = Math.floor(new Date('2026-12-31T23:59:59Z').getTime() / 1000);

export function buildMockAuth(profile: MockupProfileId, pathname: string): AuthState {
	if (profile === 'admin') {
		return {
			token: 'mock-token-admin',
			refreshToken: 'mock-refresh-admin',
			accessExpiresAt: MOCK_EXPIRES_AT,
			userId: 'mock-admin-1',
			username: 'demo-admin',
			projectId: 'mock-admin-project',
			projectName: 'Admin Demo Project',
			availableProjects: [],
			roles: ['admin'],
			isSystemAdmin: true,
			federated: false,
			...MOCK_DOMAIN,
		};
	}

	if (pathname === '/select-project') {
		return {
			token: 'mock-token-tutorial-projectless',
			refreshToken: 'mock-refresh-tutorial-projectless',
			accessExpiresAt: MOCK_EXPIRES_AT,
			userId: 'mock-user-1',
			username: 'demo-user',
			projectId: null,
			projectName: null,
			availableProjects: [],
			roles: ['member'],
			isSystemAdmin: false,
			federated: false,
			...MOCK_DOMAIN,
		};
	}

	return {
		token: 'mock-token-tutorial-scoped',
		refreshToken: 'mock-refresh-tutorial-scoped',
		accessExpiresAt: MOCK_EXPIRES_AT,
		userId: 'mock-user-1',
		username: 'demo-user',
		projectId: 'mock-project-1',
		projectName: 'Sample Cloud Demo',
		availableProjects: [],
		roles: ['member'],
		isSystemAdmin: false,
		federated: false,
		...MOCK_DOMAIN,
	};
}
