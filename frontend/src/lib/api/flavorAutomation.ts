import { api } from './client';
import type { ComputeAuthority } from './computePools';

export interface FlavorAutomationStatus {
	enabled: boolean;
	revision: number;
	last_run: string | null;
	status: 'disabled' | 'idle' | 'running' | 'complete' | 'unavailable';
	error: string | null;
	readiness: { verified: boolean; reason: string };
	items: Array<{ id: string; name: string; display_name?: string | null; origin?: 'managed' | 'adopted_cpu' | 'native'; enforcement?: 'native_private_acl' | 'afterglow_only'; control_state?: 'controlled' | 'unknown' | 'public_external_bypass' | 'excluded' | 'unqualified'; vcpus: number; ram: number; disk: number; gpu_resource_class: string | null; gpu_count: number | null; status: 'created' | 'unchanged' | 'retained' | 'retired' | 'conflict'; projects: number; reason?: string }>;
	diagnostics: Array<{ code: string; message: string }>;
}

export interface GpuAutomationProfile {
	name: string;
	display_name: string;
	enabled: boolean;
	resource_class: string;
	resource_requirements: Record<string, number>;
	extra_specs: Record<string, string>;
	alias_resource_classes?: Record<string, string>;
}
export interface PciAlias {
	name: string;
	vendor_id: string | null;
	product_id: string | null;
	resource_class: string | null;
	kind: 'gpu' | 'audio' | 'unknown';
	device_name: string | null;
	selectable: boolean;
	mapped_groups: string[];
}
export interface PciDevicesSnapshot {
	alias_source: { state: 'ready' | 'partial' | 'unavailable'; source: 'nova_api_config'; observed_at: string | null; message: string | null };
	aliases: PciAlias[];
	inventory: {
		state: 'ready' | 'partial' | 'unavailable';
		devices: Array<{ host: string; provider_uuid: string; provider_name: string; pci_address: string | null; resource_class: string; vendor_id: string | null; product_id: string | null; kind: 'gpu' | 'audio' | 'unknown'; total: number; reserved: number; used: number | null; mapped_groups: string[] }>;
		errors: string[];
	};
}
export function gpuAliasGroup(snapshot: PciDevicesSnapshot, primary: string, companions: string[], confirmUnknown = false): Pick<GpuProfileDraft, 'resource_class' | 'resources' | 'specs' | 'aliases'> | null {
	if (snapshot.alias_source.state !== 'ready' || new Set([primary, ...companions]).size !== companions.length + 1 || companions.length > 15) return null;
	const chosen = [primary, ...companions].map((name, index) => {
		const matches = snapshot.aliases.filter(alias => alias.name === name);
		const alias = matches.length === 1 ? matches[0] : null;
		return alias?.selectable && (alias.kind === (index === 0 ? 'gpu' : 'audio') || (confirmUnknown && alias.kind === 'unknown')) && alias.resource_class && resourceClass.test(alias.resource_class) ? alias : null;
	});
	if (chosen.some(alias => !alias)) return null;
	const resources: Record<string, number> = {}, aliases: Record<string, string> = {};
	for (const alias of chosen) { const rc = alias!.resource_class!; resources[rc] = (resources[rc] ?? 0) + 1; aliases[alias!.name] = rc; }
	if (resources[chosen[0]!.resource_class!] !== 1) return null;
	return { resource_class: chosen[0]!.resource_class!, resources: JSON.stringify(resources, null, 2), specs: JSON.stringify({ 'pci_passthrough:alias': chosen.map(alias => `${alias!.name}:1`).join(',') }, null, 2), aliases: JSON.stringify(aliases, null, 2) };
}
export function gpuAliasSelection(snapshot: PciDevicesSnapshot, profile: GpuAutomationProfile): { primary: string; companions: string[]; confirmUnknown: false } | null {
	if (Object.keys(profile.extra_specs).length !== 1 || !Object.hasOwn(profile.extra_specs, 'pci_passthrough:alias')) return null;
	const requests = profile.extra_specs['pci_passthrough:alias'].split(',');
	if (!requests.length || requests.some(request => !/^[A-Za-z0-9_.-]{1,128}:1$/.test(request))) return null;
	const [primary, ...companions] = requests.map(request => request.slice(0, -2));
	const generated = gpuAliasGroup(snapshot, primary, companions);
	if (!generated || generated.resource_class !== profile.resource_class) return null;
	for (const [saved, compiled] of [[profile.resource_requirements, JSON.parse(generated.resources)], [profile.alias_resource_classes ?? {}, JSON.parse(generated.aliases)]] as Array<[Record<string, unknown>, Record<string, unknown>]>) {
		if (Object.keys(saved).length !== Object.keys(compiled).length || Object.entries(saved).some(([key, value]) => !Object.hasOwn(compiled, key) || compiled[key] !== value)) return null;
	}
	return { primary, companions, confirmUnknown: false };
}
export interface AutomationHost {
	id: string;
	name: string;
	removed: boolean;
	observed_at: string;
	cpu: Record<string, number>;
	pcpu?: Record<string, number>;
	ram: Record<string, number>;
	gpu: Record<string, number>;
	state?: string;
	status?: string;
}
export interface FlavorAutomationPolicy {
	revision: number;
	hosts: AutomationHost[];
	gpu_profiles: GpuAutomationProfile[];
}
export interface GpuProfileDraft {
	name: string;
	display_name: string;
	enabled: boolean;
	resource_class: string;
	resources: string;
	specs: string;
	aliases: string;
}
const resourceClass = /^CUSTOM_PCI_[0-9A-F]{4}_[0-9A-F]{4}$/;
export function parseGpuProfiles(drafts: GpuProfileDraft[]): GpuAutomationProfile[] | null {
	if (drafts.length > 128) return null;
	const names = new Set<string>(), primaries = new Set<string>(), aliases = new Map<string, string>(), kinds = new Map<string, string>();
	try {
		return drafts.map(draft => {
			const requirements: unknown = JSON.parse(draft.resources), specs: unknown = JSON.parse(draft.specs), mapping: unknown = JSON.parse(draft.aliases);
			if (!/^[a-z0-9][a-z0-9-]{0,63}$/.test(draft.name) || names.has(draft.name) || primaries.has(draft.resource_class) || !draft.display_name.trim() || draft.display_name !== draft.display_name.trim() || draft.display_name.length > 128 || /[\x00-\x1f]/.test(draft.display_name) || !resourceClass.test(draft.resource_class)) throw new Error();
			if (!requirements || Array.isArray(requirements) || typeof requirements !== 'object' || !specs || Array.isArray(specs) || typeof specs !== 'object' || !mapping || Array.isArray(mapping) || typeof mapping !== 'object') throw new Error();
			const resources = requirements as Record<string, number>, extra = specs as Record<string, string>, aliasMap = mapping as Record<string, string>;
			if (resources[draft.resource_class] !== 1 || Object.keys(resources).length > 16 || !Object.keys(extra).length || Object.keys(extra).length > 128 || Object.keys(aliasMap).length > 16) throw new Error();
			if (Object.entries(resources).some(([key, value]) => !resourceClass.test(key) || !Number.isSafeInteger(value) || value < 1 || value > 2_147_483_647)) throw new Error();
			if (Object.entries(extra).some(([key, value]) => !key || key.length > 255 || /^afterglow:/i.test(key) || ['is_public', 'description', 'name', 'id'].includes(key) || typeof value !== 'string' || !value || value.length > 4096 || /[\x00-\x1f]/.test(key + value))) throw new Error();
			if ((Object.hasOwn(extra, 'hw:cpu_policy') && !['shared', 'dedicated'].includes(extra['hw:cpu_policy'])) || extra['hw:emulator_threads_policy'] === 'isolate') throw new Error();
			if (Object.entries(aliasMap).some(([alias, rc]) => !/^[A-Za-z0-9_.-]{1,128}$/.test(alias) || typeof rc !== 'string' || !Object.hasOwn(resources, rc))) throw new Error();
			const aliasCounts: Record<string, number> = {}, explicit: Record<string, number> = {};
			for (const [key, value] of Object.entries(extra)) {
				if (key.startsWith('resources')) {
					const match = /^resources(?:[A-Za-z0-9_-]{1,64})?:([A-Z][A-Z0-9_]{0,254})$/.exec(key);
					if (!match || !/^[1-9][0-9]{0,8}$/.test(value) || !Object.hasOwn(resources, match[1])) throw new Error();
					explicit[match[1]] = (explicit[match[1]] ?? 0) + Number(value);
				}
				if (key === 'pci_passthrough:alias') for (const item of value.split(',')) {
					const match = /^([A-Za-z0-9_.-]{1,128}):([1-9][0-9]{0,8})$/.exec(item);
					if (!match || Object.hasOwn(aliasCounts, match[1])) throw new Error();
					aliasCounts[match[1]] = Number(match[2]);
				}
			}
			const requestedAliases = Object.keys(aliasCounts);
			if (Object.values(aliasCounts).reduce((sum, count) => sum + count, 0) > 16) throw new Error();
			if (!Object.keys(aliasMap).length && requestedAliases.length === 1 && Object.keys(resources).length === 1) aliasMap[requestedAliases[0]] = draft.resource_class;
			if (requestedAliases.some(alias => !aliasMap[alias]) || Object.keys(aliasMap).some(alias => !Object.hasOwn(aliasCounts, alias))) throw new Error();
			for (const [alias, rc] of Object.entries(aliasMap)) { if (aliases.has(alias) && aliases.get(alias) !== rc) throw new Error(); aliases.set(alias, rc); }
			const aliasResources: Record<string, number> = {};
			for (const [alias, count] of Object.entries(aliasCounts)) aliasResources[aliasMap[alias]] = (aliasResources[aliasMap[alias]] ?? 0) + count;
			if (Object.keys(aliasResources).some(rc => Object.hasOwn(explicit, rc))) throw new Error();
			if (!requestedAliases.length || Object.keys(aliasResources).length !== Object.keys(resources).length || Object.entries(resources).some(([rc, count]) => aliasResources[rc] !== count)) throw new Error();
			for (const rc of Object.keys(resources)) { const kind = rc === draft.resource_class ? 'gpu' : 'companion'; if (kinds.has(rc) && kinds.get(rc) !== kind) throw new Error(); kinds.set(rc, kind); }
			names.add(draft.name); primaries.add(draft.resource_class);
			return { name: draft.name, display_name: draft.display_name, enabled: draft.enabled, resource_class: draft.resource_class, resource_requirements: resources, extra_specs: extra, alias_resource_classes: aliasMap };
		});
	} catch { return null; }
}
export function flavorAutomation(authority: ComputeAuthority) {
	const root = '/api/v1/admin/flavor-automation';
	const dispatch = async <T>(send: () => Promise<T>, mutation = false): Promise<T> => {
		if (!authority.isCurrent() || (mutation && !authority.canSubmit())) throw new DOMException('', 'AbortError');
		try {
			const result = await send();
			if (!authority.isCurrent()) throw new DOMException('', 'AbortError');
			return result;
		} catch (cause) {
			if (!authority.isCurrent()) throw new DOMException('', 'AbortError');
			throw cause;
		}
	};
	const beforeDispatch = () => {
		if (!authority.isCurrent() || !authority.canSubmit()) throw new DOMException('', 'AbortError');
	};
	return {
		load: () => dispatch(() => api.get<FlavorAutomationStatus>(root, authority.token(), authority.projectId(), { cache: 'no-store' })),
		save: (revision: number, enabled: boolean) => dispatch(() => api.put<FlavorAutomationStatus>(root, { revision, enabled }, authority.token(), authority.projectId(), { replayOnUnauthorized: false, beforeDispatch }), true),
		reconcile: () => dispatch(() => api.post<FlavorAutomationStatus>(root + '/reconcile', {}, authority.token(), authority.projectId(), { replayOnUnauthorized: false, beforeDispatch }), true),
		policy: () => dispatch(() => api.get<FlavorAutomationPolicy>(root + '/policy', authority.token(), authority.projectId(), { cache: 'no-store' })),
		pciDevices: () => dispatch(() => api.get<PciDevicesSnapshot>(root + '/pci-devices', authority.token(), authority.projectId(), { cache: 'no-store' })),
		saveProfiles: (revision: number, gpu_profiles: GpuAutomationProfile[]) => dispatch(() => api.put<FlavorAutomationPolicy>(root + '/policy', { revision, gpu_profiles }, authority.token(), authority.projectId(), { replayOnUnauthorized: false, beforeDispatch }), true),
		discover: () => dispatch(() => api.post<FlavorAutomationPolicy>(root + '/discover', {}, authority.token(), authority.projectId(), { replayOnUnauthorized: false, beforeDispatch }), true),
		host: (id: string, revision: number, removed: boolean) => dispatch(() => api.put<FlavorAutomationPolicy>(`${root}/hosts/${encodeURIComponent(id)}`, { revision, removed }, authority.token(), authority.projectId(), { replayOnUnauthorized: false, beforeDispatch }), true)
	};
}
