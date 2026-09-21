// 사용자에게 노출되는 이름은 "튜토리얼"이다: URL은 ?tutorial=on|admin|off.
// (내부 심볼의 Mockup 접두어는 가상 데이터 레이어를 가리키는 구현 용어로 유지한다.)
export type MockupProfileId = 'on' | 'admin';

export const MOCKUP_QUERY_KEY = 'tutorial';
export const MOCKUP_COOKIE = 'afterglow_mockup';
export const MOCKUP_STORAGE_KEY = 'afterglow_mock_auth';
// sessionStorage keeps the client activation scoped to one browser tab.
export const MOCKUP_SESSION_KEY = 'afterglow_mockup_profile';
export const MOCK_MCP_CONSENT_TICKET = 'mock-consent-ticket-0000000000000000000000000';

export interface MockupSession {
	active: boolean;
	profile: MockupProfileId | null;
	homePath: '/' | '/dashboard' | '/admin';
	allowedPaths: string[];
	bannerLabel: string;
	bannerMessage: string;
}

// 튜토리얼은 실제 콘솔과 동일한 화면 구조를 보여주기 위해 /dashboard 전체를 허용한다
// (미지원 API는 transport가 409로 응답 — 페이지 구조는 그대로 유지된다).
const TUTORIAL_ALLOWED_PATHS = [
	'/',
	'/login',
	'/select-project',
	'/oauth/mcp/authorize',
	'/dashboard',
] as const;

export const ADMIN_ALLOWED_PATHS = [
	'/',
	'/login',
	'/admin',
	'/admin/instances',
	'/admin/volumes',
	'/admin/libraries',
	'/admin/topology',
	'/admin/containers',
	'/admin/secrets',
	'/admin/monitoring',
	'/admin/services',
	'/admin/users',
] as const;

const PROFILE_ALLOWED_PATHS: Record<MockupProfileId, readonly string[]> = {
	on: TUTORIAL_ALLOWED_PATHS,
	admin: ADMIN_ALLOWED_PATHS,
};

const PROFILE_HOME_PATH: Record<MockupProfileId, MockupSession['homePath']> = {
	on: '/dashboard',
	admin: '/admin',
};

const PROFILE_BANNER_LABEL: Record<MockupProfileId, string> = {
	on: '튜토리얼',
	admin: '관리자 미리보기',
};

const PROFILE_BANNER_MESSAGE: Record<MockupProfileId, string> = {
	on: '체험 모드입니다. 실제 리소스는 생성되지 않습니다.',
	admin: '실제 API 호출 없이 가상 데이터로 렌더링 중입니다.',
};

export const MOCKUP_SERVICE_OVERRIDES = {
	magnum: true,
	manila: true,
	zun: true,
	cloud_shell: false,
	k3s: true,
	trove: true,
	swift: true,
	barbican: true,
	waygate: false,
	chat: false,
	mcp: true,
} as const;

export function isMockupProfileId(value: unknown): value is MockupProfileId {
	return value === 'on' || value === 'admin';
}

export function inactiveMockupSession(): MockupSession {
	return {
		active: false,
		profile: null,
		homePath: '/',
		allowedPaths: [],
		bannerLabel: '',
		bannerMessage: '',
	};
}

export function buildMockupSession(profile: MockupProfileId): MockupSession {
	return {
		active: true,
		profile,
		homePath: PROFILE_HOME_PATH[profile],
		allowedPaths: [...PROFILE_ALLOWED_PATHS[profile]],
		bannerLabel: PROFILE_BANNER_LABEL[profile],
		bannerMessage: PROFILE_BANNER_MESSAGE[profile],
	};
}

export function isMockupPathAllowed(profile: MockupProfileId, pathname: string): boolean {
	if (PROFILE_ALLOWED_PATHS[profile].includes(pathname)) return true;
	// 튜토리얼은 대시보드 전체를 실제와 동일하게 탐색할 수 있다.
	return profile === 'on' && pathname.startsWith('/dashboard/');
}

export function getMockupHomePath(profile: MockupProfileId): '/dashboard' | '/admin' {
	return PROFILE_HOME_PATH[profile] as '/dashboard' | '/admin';
}
