export interface SessionRefreshState {
	token: string | null;
	refreshToken: string | null;
	accessExpiresAt: number | null;
	isMock: boolean;
	isLoggingOut: boolean;
}

interface SessionRefreshLifecycleOptions {
	getSession: () => SessionRefreshState;
	refreshSession: () => Promise<string | null>;
}

const REFRESH_LEEWAY_SECONDS = 120;
const REFRESH_INTERVAL_MS = 60_000;

/**
 * Refreshes an expiring real session when the app mounts, resumes, or reaches
 * the periodic fallback. The state reader is evaluated for every check so
 * handlers never act on the session that existed when they were registered.
 */
export function startSessionRefreshLifecycle({
	getSession,
	refreshSession,
}: SessionRefreshLifecycleOptions): () => void {
	const refreshIfExpiring = () => {
		const session = getSession();
		if (
			session.isMock ||
			session.isLoggingOut ||
			!session.token ||
			!session.refreshToken ||
			session.accessExpiresAt == null ||
			session.accessExpiresAt > Math.floor(Date.now() / 1000) + REFRESH_LEEWAY_SECONDS
		) {
			return;
		}

		void refreshSession().catch(() => {
			// Request-driven recovery owns terminal auth; transient failures retry later.
		});
	};

	const onVisibilityChange = () => {
		if (document.visibilityState === 'visible') refreshIfExpiring();
	};

	refreshIfExpiring();
	window.addEventListener('focus', refreshIfExpiring);
	document.addEventListener('visibilitychange', onVisibilityChange);
	const interval = window.setInterval(refreshIfExpiring, REFRESH_INTERVAL_MS);

	return () => {
		window.removeEventListener('focus', refreshIfExpiring);
		document.removeEventListener('visibilitychange', onVisibilityChange);
		window.clearInterval(interval);
	};
}
