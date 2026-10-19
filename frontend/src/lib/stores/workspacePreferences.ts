export interface ResourcePreference { pinned?: boolean; hidden?: boolean; order?: number; visited?: number }
export interface WorkspacePreferences { domains: Record<string, ResourcePreference>; projects: Record<string, ResourcePreference> }
export type ResourceKind = keyof WorkspacePreferences;
export const emptyWorkspacePreferences = (): WorkspacePreferences => ({ domains: {}, projects: {} });

/** Presentation only: callers must intersect every ID with a fresh authorized inventory. */
export function workspacePreferenceKey(identityDomainId: string, userId: string): string {
	return `afterglow.workspace-display.${encodeURIComponent(identityDomainId)}.${encodeURIComponent(userId)}`;
}
export function readWorkspacePreferences(key: string): WorkspacePreferences {
	try {
		const value = JSON.parse(localStorage.getItem(key) ?? '{}');
		const result = emptyWorkspacePreferences();
		for (const kind of ['domains', 'projects'] as const) {
			if (!value[kind] || typeof value[kind] !== 'object' || Array.isArray(value[kind])) continue;
			for (const [id, raw] of Object.entries(value[kind])) {
				if (!raw || typeof raw !== 'object') continue;
				const row = raw as ResourcePreference;
				Object.defineProperty(result[kind], id, { enumerable: true, configurable: true, writable: true, value: {
					pinned: row.pinned === true, hidden: row.hidden === true,
					order: Number.isFinite(row.order) ? row.order : undefined,
					visited: Number.isFinite(row.visited) ? row.visited : undefined,
				} });
			}
		}
		return result;
	} catch { return emptyWorkspacePreferences(); }
}
export function saveWorkspacePreferences(key: string, preferences: WorkspacePreferences): boolean {
	try { localStorage.setItem(key, JSON.stringify(preferences)); return true; } catch { return false; }
}
export function sortWorkspaceResources<T extends { id: string; name: string }>(rows: T[], preferences: Record<string, ResourcePreference>, recent = false): T[] {
	return [...rows].sort((a, b) => recent
		? (preferences[b.id]?.visited ?? 0) - (preferences[a.id]?.visited ?? 0)
		: (preferences[a.id]?.order ?? Number.MAX_SAFE_INTEGER) - (preferences[b.id]?.order ?? Number.MAX_SAFE_INTEGER) || a.name.localeCompare(b.name) || a.id.localeCompare(b.id));
}
