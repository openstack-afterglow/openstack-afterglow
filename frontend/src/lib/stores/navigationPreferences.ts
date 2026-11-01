export interface NavigationPreferences { pinned: string[] }
export const emptyNavigationPreferences = (): NavigationPreferences => ({ pinned: [] });

/** Only public destination paths are stored; current visibility always decides what can render. */
export function navigationPreferenceKey(home: string, user: string, surface: string): string {
	return `afterglow.navigation.${encodeURIComponent(home)}.${encodeURIComponent(user)}.${surface}`;
}

export function readNavigationPreferences(key: string): NavigationPreferences {
	try {
		const value = JSON.parse(localStorage.getItem(key) ?? '{}');
		const paths = (rows: unknown, limit: number) => Array.isArray(rows)
			? [...new Set(rows.filter((row): row is string => typeof row === 'string' && /^\/(dashboard|admin|palimpsest|docs)(\/|$)/.test(row)))].slice(0, limit)
			: [];
		return { pinned: paths(value?.pinned, 20) };
	} catch { return emptyNavigationPreferences(); }
}

export function saveNavigationPreferences(key: string, preferences: NavigationPreferences): boolean {
	try { localStorage.setItem(key, JSON.stringify(preferences)); return true; } catch { return false; }
}
