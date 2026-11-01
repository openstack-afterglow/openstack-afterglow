import { writable } from 'svelte/store';
import type { FlavorComposition } from '$lib/types/flavor';

export type FlavorComposerMode = 'compose' | 'saved' | 'catalog';
export interface FlavorResourceDraft {
	mode: FlavorComposerMode;
	composition: FlavorComposition;
	selectedId: string | null;
}
export const defaultFlavorComposition = (): FlavorComposition => ({ vcpus: 2, ram_mb: 4096, gpu_profile_id: null, gpu_count: 0 });
export const resourceDraftReset = writable(0);
let activeKey: string | null = null;
let resourceSelectionOwner: string | undefined;

/** In-memory wizard selections outlive a mounted composer, unlike its request listeners. */
export function claimResourceSelectionScope(owner: string): boolean {
	const changed = resourceSelectionOwner !== undefined && resourceSelectionOwner !== owner;
	resourceSelectionOwner = owner;
	return changed;
}
const PREFIX = 'afterglow:vm-resources:v1:';

export function flavorResourceDraftKey(userId: string | null, homeId: string | null | undefined, projectId: string | null, admin: boolean): string | null {
	return userId && homeId && projectId ? PREFIX + JSON.stringify([userId, homeId, projectId, admin ? 'admin' : 'consumer']) : null;
}
export function activateResourceDraft(key: string | null) { activeKey = key; }
/** Retention accepts legacy odd CPUs so a saved draft is not silently rewritten. */
export function retainableFlavorComposition(value: unknown): value is FlavorComposition {
	if (!value || typeof value !== 'object') return false;
	const c = value as FlavorComposition;
	return Number.isInteger(c.vcpus) && c.vcpus >= 1 && c.vcpus <= 128
		&& Number.isInteger(c.ram_mb) && c.ram_mb >= 1024 && c.ram_mb <= 2097152 && c.ram_mb % 1024 === 0
		&& (c.gpu_profile_id === null || (typeof c.gpu_profile_id === 'string' && c.gpu_profile_id.length > 0 && c.gpu_profile_id.length <= 255))
		&& Number.isInteger(c.gpu_count) && c.gpu_count >= 0 && c.gpu_count <= 16
		&& (c.gpu_profile_id === null ? c.gpu_count === 0 : c.gpu_count >= 1);
}
export function validFlavorComposition(value: unknown): value is FlavorComposition {
	return retainableFlavorComposition(value) && value.vcpus >= 2 && value.vcpus % 2 === 0;
}
export function readResourceDraft(key: string | null): FlavorResourceDraft | null {
	if (!key || typeof localStorage === 'undefined') return null;
	try {
		const value = JSON.parse(localStorage.getItem(key) ?? 'null');
		if (!value || !['compose', 'saved', 'catalog'].includes(value.mode) || !retainableFlavorComposition(value.composition)) return null;
		return { mode: value.mode, composition: { vcpus: value.composition.vcpus, ram_mb: value.composition.ram_mb, gpu_profile_id: value.composition.gpu_profile_id, gpu_count: value.composition.gpu_count }, selectedId: typeof value.selectedId === 'string' ? value.selectedId : null };
	} catch { return null; }
}
export function writeResourceDraft(key: string | null, draft: FlavorResourceDraft) {
	if (!key || typeof localStorage === 'undefined' || !retainableFlavorComposition(draft.composition)) return;
	// Explicit allowlist: no whole wizard/auth objects, secrets, consent or admission snapshots.
	const { vcpus, ram_mb, gpu_profile_id, gpu_count } = draft.composition;
	try { localStorage.setItem(key, JSON.stringify({ mode: draft.mode, composition: { vcpus, ram_mb, gpu_profile_id, gpu_count }, selectedId: draft.selectedId })); } catch { /* storage is optional */ }
}
export function clearActiveResourceDraft() {
	resourceSelectionOwner = undefined;
	try { if (activeKey && typeof localStorage !== 'undefined') localStorage.removeItem(activeKey); } catch { /* storage is optional */ }
	resourceDraftReset.update(value => value + 1);
}
