import type { Handle } from '@sveltejs/kit';
import { loadPublicSiteConfig } from '$lib/server/config';
import type { PublicSiteConfig } from '$lib/types/siteConfig';
import {
	MOCKUP_COOKIE,
	MOCKUP_QUERY_KEY,
	buildMockupSession,
	getMockupHomePath,
	inactiveMockupSession,
	isMockupPathAllowed,
	isMockupProfileId,
} from '$lib/mockup/contracts';

// 인증 없이 접근 가능한 경로
const PUBLIC_PATHS = ['/', '/login', '/auth/gitlab/callback', '/health'];

// 정적 파일로 판단할 확장자 패턴
const STATIC_EXT = /\.(js|css|svg|png|jpg|jpeg|ico|woff2?|ttf|eot|map|webp|gif)$/;

// 인그레스에서 백엔드로 포워딩되는 접두. 프론트가 받을 일은 없지만 SPA 폴백에서 방어적으로 제외.
// /.well-known 은 MCP OAuth discovery(백엔드 root_router) 이므로 앱 셸 200 대신 404 를 유지한다.
const BACKEND_PREFIXES = ['/api', '/v1', '/.well-known'];

// SPA 폴백 대상 판단 — 로그인 상태의 "문서 내비게이션 404" 만.
// 정적 자산·데이터 요청(__data.json)·SvelteKit 내부·백엔드 경로는 제외해 원래 404를 유지한다.
function shouldSpaFallback(event: Parameters<Handle>[0]['event'], response: Response): boolean {
	if (response.status !== 404) return false;
	const path = event.url.pathname;
	if (STATIC_EXT.test(path) || path.startsWith('/_app/') || path.includes('__data.json')) return false;
	if (BACKEND_PREFIXES.some((p) => path === p || path.startsWith(`${p}/`))) return false;
	const accept = event.request.headers.get('accept') ?? '';
	return accept.includes('text/html');
}

// 홈 라우트 SSR HTML(앱 셸)을 받아 200으로 반환 — 브라우저 URL은 유지되므로 클라이언트 라우터가
// 요청 경로를 렌더한다. 실패 시 null(호출부가 원래 404 응답을 그대로 사용).
async function serveAppShell(
	event: Parameters<Handle>[0]['event'],
	securityHeaders: Record<string, string>,
): Promise<Response | null> {
	try {
		const home = await event.fetch('/');
		if (!home.ok) return null;
		const body = await home.text();
		const headers = new Headers({ 'content-type': 'text/html; charset=utf-8' });
		for (const [key, value] of Object.entries(securityHeaders)) headers.set(key, value);
		return new Response(body, { status: 200, headers });
	} catch {
		return null;
	}
}

// connect-src에 API + S3 URL 추가 (presigned PUT 허용)
function buildConnectSrc(siteConfig: PublicSiteConfig): string {
	const parts = ["'self'"];
	for (const raw of [siteConfig.runtime.api_base, siteConfig.runtime.s3_base]) {
		if (!raw) continue;
		parts.push(raw);
	}
	return parts.join(' ');
}

function addOrigin(parts: Set<string>, raw: string): void {
	if (!raw) return;
	try {
		const url = new URL(raw);
		if (url.protocol === 'http:' || url.protocol === 'https:') {
			parts.add(url.origin);
		}
	} catch {
		// Relative paths stay covered by 'self'.
	}
}

function buildImgSrc(siteConfig: PublicSiteConfig): string {
	const parts = new Set(["'self'", 'data:', 'blob:']);
	for (const raw of [
		siteConfig.runtime.api_base,
		siteConfig.logo_path,
		siteConfig.logo_dark_path,
		siteConfig.logo_light_path,
		siteConfig.favicon_path,
	]) {
		addOrigin(parts, raw);
	}
	return [...parts].join(' ');
}

// frame-src에 Grafana/LibreChat/GitLab origin 추가 (iframe 임베드 허용).
// GitLab은 LibreChat이 임베드된 프레임 안에서 GitLab OIDC 로그인으로 자체
// 리다이렉트할 때 필요 — frame-src는 프레임의 최초 로드뿐 아니라 그 프레임의
// 이후 내비게이션(리다이렉트)까지 통제하므로 목적지인 GitLab도 허용해야 한다.
function buildFrameSrc(siteConfig: PublicSiteConfig): string {
	const parts = ["'self'"];
	if (siteConfig.runtime.grafana_base) {
		parts.push(siteConfig.runtime.grafana_base);
	}
	if (siteConfig.runtime.librechat_base) {
		parts.push(siteConfig.runtime.librechat_base);
	}
	if (siteConfig.runtime.gitlab_base) {
		parts.push(siteConfig.runtime.gitlab_base);
	}
	return parts.join(' ');
}

// 모든 응답에 추가할 보안 헤더
function buildSecurityHeaders(siteConfig: PublicSiteConfig): Record<string, string> {
	return {
		'X-Frame-Options': 'DENY',
		'X-Content-Type-Options': 'nosniff',
		'Referrer-Policy': 'strict-origin-when-cross-origin',
		'Permissions-Policy': 'camera=(), microphone=(), geolocation=()',
		'X-XSS-Protection': '0',
		'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
		// SvelteKit은 인라인 스타일/스크립트를 사용하므로 unsafe-inline 허용
		'Content-Security-Policy':
			`default-src 'self'; ` +
			`script-src 'self' 'unsafe-inline'; ` +
			`style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; ` +
			`img-src ${buildImgSrc(siteConfig)}; ` +
			`connect-src ${buildConnectSrc(siteConfig)}; ` +
			`font-src 'self' https://fonts.gstatic.com; ` +
			`frame-src ${buildFrameSrc(siteConfig)}; ` +
			`frame-ancestors 'none'`,
	};
}

export const handle: Handle = async ({ event, resolve }) => {
	const siteConfig = loadPublicSiteConfig();
	const securityHeaders = buildSecurityHeaders(siteConfig);
	event.locals.siteConfig = siteConfig;
	const path = event.url.pathname;

	const requestedMockup = event.url.searchParams.get(MOCKUP_QUERY_KEY);
	let mockup = inactiveMockupSession();
	if (isMockupProfileId(requestedMockup)) {
		// Mockup activation is bootstrapped by the explicit query only. The client
		// keeps the profile in sessionStorage so one tab cannot contaminate another.
		mockup = buildMockupSession(requestedMockup);
	} else if (requestedMockup === 'off') {
		event.cookies.delete(MOCKUP_COOKIE, { path: '/' });
	} else {
		// Clear legacy persisted cookies; they must never activate mockup mode.
		if (event.cookies.get(MOCKUP_COOKIE)) event.cookies.delete(MOCKUP_COOKIE, { path: '/' });
	}
	event.locals.mockup = mockup;
	if (mockup.profile && event.route.id !== null && !isMockupPathAllowed(mockup.profile, path)) {
		return new Response(null, {
			status: 302,
			headers: { Location: `${getMockupHomePath(mockup.profile)}?${MOCKUP_QUERY_KEY}=${mockup.profile}` },
		});
	}

	// 공개 경로, 정적 리소스, SvelteKit 내부 경로는 통과
	if (
		PUBLIC_PATHS.includes(path) ||
		path.startsWith('/_app/') ||
		path.startsWith('/favicon') ||
		path.startsWith('/logo') ||
		STATIC_EXT.test(path)
	) {
		const response = await resolve(event);
		for (const [key, value] of Object.entries(securityHeaders)) {
			response.headers.set(key, value);
		}
		return response;
	}

	// 서버 사이드에서는 localStorage에 접근할 수 없으므로,
	// 클라이언트의 auth.ts에서 설정한 마커 쿠키로 로그인 여부를 판단.
	// (토큰 자체는 쿠키에 없으므로 쿠키 탈취 시 실제 API 호출은 불가)
	if (mockup.profile) {
		if (isMockupPathAllowed(mockup.profile, path)) {
			const response = await resolve(event);
			for (const [key, value] of Object.entries(securityHeaders)) {
				response.headers.set(key, value);
			}
			return response;
		}
		return new Response(null, {
			status: 302,
			headers: { Location: `${getMockupHomePath(mockup.profile)}?${MOCKUP_QUERY_KEY}=${mockup.profile}` },
		});
	}

	const sessionCookie = event.cookies.get('afterglow_session');
	if (!sessionCookie) {
		return new Response(null, {
			status: 302,
			headers: { Location: '/login' },
		});
	}

	const response = await resolve(event);

	// SPA 폴백: 로그인 상태에서 문서 내비게이션이 404면 앱 셸(홈 SSR)을 200으로 내려
	// 클라이언트 라우터가 요청 경로를 렌더하게 한다(요청 URL 유지, 리다이렉트 아님).
	// SSR 시점엔 localStorage 토큰·클라 전용 데이터가 없어 유효 라우트도 404로 끝날 수 있으나,
	// 클라이언트에서는 정상 렌더되므로 딥링크·새로고침이 동작한다.
	if (shouldSpaFallback(event, response)) {
		const shell = await serveAppShell(event, securityHeaders);
		if (shell) return shell;
	}

	for (const [key, value] of Object.entries(securityHeaders)) {
		response.headers.set(key, value);
	}
	return response;
};
