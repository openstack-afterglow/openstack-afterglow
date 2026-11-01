import { describe, expect, it, vi, beforeEach } from 'vitest';
const mocks = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), post: vi.fn() }));
vi.mock('./client', () => ({ api: mocks }));
import { flavorAutomation, parseGpuProfiles, gpuAliasGroup, gpuAliasSelection, type PciDevicesSnapshot, type GpuProfileDraft } from './flavorAutomation';
const gpu = 'CUSTOM_PCI_10DE_2504', audio = 'CUSTOM_PCI_10DE_228E';
const draft = (name = '3060lhr', rc = gpu): GpuProfileDraft => ({ name, display_name: name, enabled: false, resource_class: rc, resources: JSON.stringify({ [rc]: 1 }), specs: JSON.stringify({ 'pci_passthrough:alias': `${name}:1`, 'hw:cpu_policy': 'dedicated' }), aliases: '{}' });
beforeEach(() => vi.resetAllMocks());
const pciSnapshot = (): PciDevicesSnapshot => ({ alias_source: { state: 'ready', source: 'nova_api_config', observed_at: null, message: null }, aliases: [
	{ name: 'RTX-3060-LHR', vendor_id: '10DE', product_id: '2504', resource_class: gpu, kind: 'gpu', device_name: 'RTX 3060 LHR', selectable: true, mapped_groups: [] },
	{ name: 'RTX-3060-Audio', vendor_id: '10DE', product_id: '228E', resource_class: audio, kind: 'audio', device_name: 'Audio', selectable: true, mapped_groups: [] }
], inventory: { state: 'unavailable', devices: [], errors: ['Placement unavailable'] } });
describe('configured PCI alias group compilation', () => {
	it('compiles exact case-preserved alias names and resource counts without using Placement usage', () => {
		const result = gpuAliasGroup(pciSnapshot(), 'RTX-3060-LHR', ['RTX-3060-Audio']);
		expect(result).not.toBeNull();
		expect(parseGpuProfiles([{ ...draft(), ...result! }])![0]).toEqual({ name: '3060lhr', display_name: '3060lhr', enabled: false, resource_class: gpu, resource_requirements: { [gpu]: 1, [audio]: 1 }, extra_specs: { 'pci_passthrough:alias': 'RTX-3060-LHR:1,RTX-3060-Audio:1' }, alias_resource_classes: { 'RTX-3060-LHR': gpu, 'RTX-3060-Audio': audio } });
	});
	it.each(['partial', 'unavailable'] as const)('does not approve a %s configuration source', state => {
		const snapshot = pciSnapshot(); snapshot.alias_source.state = state;
		expect(gpuAliasGroup(snapshot, 'RTX-3060-LHR', [])).toBeNull();
	});
	it('rejects duplicate, unsupported, unknown, wrong-kind and inexact names', () => {
		const snapshot = pciSnapshot();
		expect(gpuAliasGroup(snapshot, 'rtx-3060-lhr', [])).toBeNull();
		expect(gpuAliasGroup(snapshot, 'RTX-3060-Audio', [])).toBeNull();
		expect(gpuAliasGroup(snapshot, 'RTX-3060-LHR', ['RTX-3060-LHR'])).toBeNull();
		expect(gpuAliasGroup(snapshot, 'RTX-3060-LHR', ['RTX-3060-Audio', 'RTX-3060-Audio'])).toBeNull();
		snapshot.aliases[1].kind = 'unknown'; expect(gpuAliasGroup(snapshot, 'RTX-3060-LHR', ['RTX-3060-Audio'])).toBeNull();
		snapshot.aliases[0].selectable = false; expect(gpuAliasGroup(snapshot, 'RTX-3060-LHR', [])).toBeNull();
		snapshot.aliases[0].selectable = true; snapshot.aliases.push({ ...snapshot.aliases[0] }); expect(gpuAliasGroup(snapshot, 'RTX-3060-LHR', [])).toBeNull();
	});
	it('requires separate confirmation for explicit unknown GPU and companion roles', () => {
		const snapshot = pciSnapshot(); snapshot.aliases.forEach(alias => alias.kind = 'unknown');
		expect(gpuAliasGroup(snapshot, 'RTX-3060-LHR', ['RTX-3060-Audio'])).toBeNull();
		const group = gpuAliasGroup(snapshot, 'RTX-3060-LHR', ['RTX-3060-Audio'], true)!;
		expect(JSON.parse(group.aliases)).toEqual({ 'RTX-3060-LHR': gpu, 'RTX-3060-Audio': audio });
		snapshot.alias_source.state = 'partial'; expect(gpuAliasGroup(snapshot, 'RTX-3060-LHR', ['RTX-3060-Audio'], true)).toBeNull();
	});
	it('reconstructs only exact supported unit-alias groups and leaves custom or uncertain profiles advanced', () => {
		const snapshot = pciSnapshot();
		const group = gpuAliasGroup(snapshot, 'RTX-3060-LHR', ['RTX-3060-Audio'])!;
		const profile = parseGpuProfiles([{ ...draft(), ...group }])![0];
		expect(gpuAliasSelection(snapshot, profile)).toEqual({ primary: 'RTX-3060-LHR', companions: ['RTX-3060-Audio'], confirmUnknown: false });
		expect(gpuAliasSelection(snapshot, { ...profile, extra_specs: { ...profile.extra_specs, 'custom:operator': 'keep' } })).toBeNull();
		expect(gpuAliasSelection(snapshot, { ...profile, alias_resource_classes: {} })).toBeNull();
		expect(gpuAliasSelection(snapshot, { ...profile, resource_requirements: { [gpu]: 1, [audio]: 2 } })).toBeNull();
		expect(gpuAliasSelection(snapshot, { ...profile, extra_specs: { 'pci_passthrough:alias': 'RTX-3060-LHR:1,RTX-3060-Audio:2' } })).toBeNull();
		snapshot.aliases[1].kind = 'unknown'; expect(gpuAliasSelection(snapshot, profile)).toBeNull();
		snapshot.aliases[1].kind = 'audio'; snapshot.aliases[1].selectable = false; expect(gpuAliasSelection(snapshot, profile)).toBeNull();
		snapshot.aliases[1].selectable = true; snapshot.alias_source.state = 'partial'; expect(gpuAliasSelection(snapshot, profile)).toBeNull();
	});
});
describe('exact GPU profile approval input', () => {
	it('accepts an empty initial policy and preserves separate exact slugs without approving them', () => {
		expect(parseGpuProfiles([])).toEqual([]);
		const profiles = parseGpuProfiles([draft('3060', 'CUSTOM_PCI_10DE_2503'), draft(), draft('4090', 'CUSTOM_PCI_10DE_2684')])!;
		expect(profiles.map(row => row.name)).toEqual(['3060', '3060lhr', '4090']);
		expect(profiles.every(row => !row.enabled)).toBe(true);
		expect(profiles[0].extra_specs['hw:cpu_policy']).toBe('dedicated');
	});
	it('rejects companion alias ambiguity until exact mapping is supplied', () => {
		const input = { ...draft(), resources: JSON.stringify({ [gpu]: 1, [audio]: 1 }), specs: JSON.stringify({ 'pci_passthrough:alias': 'graphics:1,sound:1' }) };
		expect(parseGpuProfiles([input])).toBeNull();
		input.aliases = JSON.stringify({ graphics: gpu, sound: audio });
		expect(parseGpuProfiles([input])![0].alias_resource_classes).toEqual({ graphics: gpu, sound: audio });
		input.aliases = JSON.stringify({ graphics: audio, sound: audio }); expect(parseGpuProfiles([input])).toBeNull();
	});
	it('rejects Placement-only physical demand because reservations do not attach devices', () => {
		expect(parseGpuProfiles([{ ...draft(), specs: JSON.stringify({ [`resourcesgpu:${gpu}`]: '1' }) }])).toBeNull();
		const input = { ...draft(), resources: JSON.stringify({ [gpu]: 1, [audio]: 1 }), specs: JSON.stringify({ 'pci_passthrough:alias': 'graphics:1', [`resourcesaudio:${audio}`]: '1' }), aliases: JSON.stringify({ graphics: gpu }) };
		expect(parseGpuProfiles([input])).toBeNull();
		input.specs = JSON.stringify({ 'pci_passthrough:alias': 'graphics:1,sound:1' });
		input.aliases = JSON.stringify({ graphics: gpu, sound: audio });
		expect(parseGpuProfiles([input])![0].resource_requirements).toEqual({ [gpu]: 1, [audio]: 1 });
		input.specs = JSON.stringify({ 'pci_passthrough:alias': 'graphics:1,sound:1', [`resourcesgpu:${gpu}`]: '1' });
		expect(parseGpuProfiles([input])).toBeNull();
	});
	it('allows shared companion aliases only when exact resource mappings agree', () => {
		const profile = (name: string, rc: string) => ({ ...draft(name, rc), resources: JSON.stringify({ [rc]: 1, [audio]: 1 }), specs: JSON.stringify({ 'pci_passthrough:alias': `${name}:1,sound:1` }), aliases: JSON.stringify({ [name]: rc, sound: audio }) });
		const first = profile('3060lhr', gpu), second = profile('4090', 'CUSTOM_PCI_10DE_2684');
		expect(parseGpuProfiles([first, second])?.map(row => row.name)).toEqual(['3060lhr', '4090']);
		const otherAudio = 'CUSTOM_PCI_10DE_22BA';
		second.resources = JSON.stringify({ CUSTOM_PCI_10DE_2684: 1, [otherAudio]: 1 });
		second.aliases = JSON.stringify({ '4090': 'CUSTOM_PCI_10DE_2684', sound: otherAudio });
		expect(parseGpuProfiles([first, second])).toBeNull();
		expect(parseGpuProfiles([{ ...first, specs: JSON.stringify({ 'pci_passthrough:alias': '3060lhr:1,sound:1,sound:1' }) }])).toBeNull();
	});
	it('rejects mismatched native scheduling counts, duplicate identities, and ownership annotations', () => {
		expect(parseGpuProfiles([{ ...draft(), specs: JSON.stringify({ [`resources:${gpu}`]: '2' }) }])).toBeNull();
		expect(parseGpuProfiles([draft(), { ...draft(), name: 'other' }])).toBeNull();
		expect(parseGpuProfiles([{ ...draft(), specs: JSON.stringify({ 'afterglow:frontend_visible': 'true' }) }])).toBeNull();
		expect(parseGpuProfiles([{ ...draft(), specs: '{"hw:cpu_policy":3}' }])).toBeNull();
		expect(parseGpuProfiles([{ ...draft(), name: 'RTX 3060' }])).toBeNull();
	});
	it('rejects unrepresentable physical CPU policies', () => {
		expect(parseGpuProfiles([{ ...draft(), specs: JSON.stringify({ 'pci_passthrough:alias': '3060lhr:1', 'hw:cpu_policy': 'mixed' }) }])).toBeNull();
		expect(parseGpuProfiles([{ ...draft(), specs: JSON.stringify({ 'pci_passthrough:alias': '3060lhr:1', 'hw:emulator_threads_policy': 'isolate' }) }])).toBeNull();
	});
});
describe('policy transport authority and replay fences', () => {
	it('uses fresh bearer and no-store policy reads; mutations never replay on unauthorized', async () => {
		let token = 'first'; const authority = { token: () => token, projectId: () => 'admin-project', isCurrent: () => true, canSubmit: () => true };
		const api = flavorAutomation(authority); mocks.get.mockResolvedValue({ revision: 1, hosts: [], gpu_profiles: [] });
		await api.policy(); await api.pciDevices(); token = 'rotated'; mocks.put.mockResolvedValue({ revision: 2 }); await api.saveProfiles(1, []); await api.host('exact/id', 2, true); await api.discover();
		expect(mocks.get).toHaveBeenCalledWith('/api/v1/admin/flavor-automation/policy', 'first', 'admin-project', { cache: 'no-store' });
		expect(mocks.get).toHaveBeenCalledWith('/api/v1/admin/flavor-automation/pci-devices', 'first', 'admin-project', { cache: 'no-store' });
		expect(mocks.put).toHaveBeenCalledWith('/api/v1/admin/flavor-automation/policy', { revision: 1, gpu_profiles: [] }, 'rotated', 'admin-project', expect.objectContaining({ replayOnUnauthorized: false }));
		expect(mocks.put).toHaveBeenCalledWith('/api/v1/admin/flavor-automation/hosts/exact%2Fid', { revision: 2, removed: true }, 'rotated', 'admin-project', expect.objectContaining({ replayOnUnauthorized: false }));
		expect(mocks.post).toHaveBeenCalledWith('/api/v1/admin/flavor-automation/discover', {}, 'rotated', 'admin-project', expect.objectContaining({ replayOnUnauthorized: false }));
	});
	it('refuses revoked write authority and discards late responses', async () => {
		let current = true; const api = flavorAutomation({ token: () => 'token', projectId: () => undefined, isCurrent: () => current, canSubmit: () => false });
		await expect(api.host('host', 0, true)).rejects.toMatchObject({ name: 'AbortError' }); expect(mocks.put).not.toHaveBeenCalled();
		const pending = Promise.withResolvers<unknown>(); mocks.get.mockReturnValue(pending.promise); const result = api.policy(); current = false; pending.resolve({ revision: 999 });
		await expect(result).rejects.toMatchObject({ name: 'AbortError' });
	});
	it('discards a late PCI snapshot when admin scope is no longer current', async () => {
		let current = true;
		const pending = Promise.withResolvers<PciDevicesSnapshot>(); mocks.get.mockReturnValue(pending.promise);
		const api = flavorAutomation({ token: () => 'token', projectId: () => 'admin-project', isCurrent: () => current, canSubmit: () => current });
		const result = api.pciDevices(); current = false; pending.resolve(pciSnapshot());
		await expect(result).rejects.toMatchObject({ name: 'AbortError' });
	});
});
