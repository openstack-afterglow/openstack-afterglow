import { api, ApiError } from './client';

export const vaultKinds = [
	'user_note', 'profile', 'coding_standards', 'project', 'short_term', 'long_term',
	'log', 'handoff', 'role_memory', 'worktree', 'knowledge', 'spec', 'change', 'wiki', 'persona'
] as const;
export const vaultRoles = ['coordinator', 'builder', 'investigator', 'reviewer'] as const;
export type VaultKind = (typeof vaultKinds)[number];
export type VaultRole = (typeof vaultRoles)[number];
export type VaultScope = 'domain' | 'global';
const appendOnlyKinds: Partial<Record<VaultKind, true>> = { long_term: true, log: true, handoff: true, role_memory: true, worktree: true };
export function isAppendOnly(kind: VaultKind): boolean {
	return Object.hasOwn(appendOnlyKinds, kind);
}
export const vaultSlots = { profile: 'profile', coding_standards: 'coding-standards', short_term: 'short-term' } as const;
export type VaultSlot = keyof typeof vaultSlots;

export function isVaultSlot(kind: string): kind is VaultSlot {
	return Object.hasOwn(vaultSlots, kind);
}

export interface VaultNote {
	id: number;
	kind: VaultKind;
	slug: string;
	title: string;
	content: string;
	hash: string;
	scope: VaultScope;
	project_key: string | null;
	role: VaultRole | null;
	revision: number;
}

export interface VaultRevision {
	revision: number;
	title: string;
	content: string;
	created_at: string;
}

interface NewVaultNote {
	kind: VaultKind;
	slug: string;
	title: string;
	content: string;
	mode: 'create' | 'append';
	scope: VaultScope;
	project_key?: string;
	role?: VaultRole;
}

export interface VaultDocument {
	filename: 'memory.md';
	content_type: 'text/markdown';
	content: string;
}

type VaultSlotResult = { exists: false } | ({ exists: true } & VaultNote);
export type VaultSelection = { id: number } | { slot: VaultSlot };
export const vaultPageSize = 25;
export const vaultContentLimit = 100_000;
const base = '/api/v1/chat/vault';

export function vaultApi(token: string, projectId: string, signal: AbortSignal) {
	const options = { signal, cache: 'no-store', replayOnUnauthorized: false } as const;
	const read = <T>(path: string) => api.get<T>(`${base}/${path}`, token, projectId, options);
	return {
		list(kind: VaultKind | '', query: string, before?: number) {
			const params = new URLSearchParams({ limit: String(vaultPageSize) });
			if (kind) params.set('kind', kind);
			if (query) params.set('query', query);
			if (before !== undefined) params.set('before', String(before));
			return read<VaultNote[]>(`${query ? 'search' : 'notes'}?${params}`);
		},
		async note(selection: VaultSelection): Promise<VaultNote | null> {
			if ('id' in selection) return read<VaultNote>(`notes/${selection.id}`);
			const result = await read<VaultSlotResult>(vaultSlots[selection.slot]);
			return result.exists ? result : null;
		},
		revisions(id: number, before?: number) {
			const params = new URLSearchParams({ limit: String(vaultPageSize) });
			if (before !== undefined) params.set('before', String(before));
			return read<VaultRevision[]>(`notes/${id}/revisions?${params}`);
		},
		document: () => read<VaultDocument>('document'),
		create: (body: NewVaultNote) => api.post<VaultNote>(`${base}/notes`, body, token, projectId, options),
		replace(selection: VaultSelection, body: { content: string; title: string; expectedHash?: string }) {
			return 'id' in selection
				? api.patch<VaultNote>(`${base}/notes/${selection.id}`, body, token, projectId, options)
				: api.put<VaultNote>(`${base}/${vaultSlots[selection.slot]}`, {
					content: body.content, expectedHash: body.expectedHash
				}, token, projectId, options);
		}
	};
}

export function isVaultError(error: unknown, code: string): boolean {
	return error instanceof ApiError && (error.code === code || error.message === code);
}
