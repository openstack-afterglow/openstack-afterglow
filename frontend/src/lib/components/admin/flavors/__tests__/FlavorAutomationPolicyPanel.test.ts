import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { get } from 'svelte/store';
import { auth, authReady, projectSwitching, logoutInProgress, acceptAuthVerification, getAuthVerificationEpoch } from '$lib/stores/auth';
import type { FlavorAutomationPolicy, PciDevicesSnapshot } from '$lib/api/flavorAutomation';
import { t } from '$lib/i18n/ns/compute-pools';
const mocks = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), post: vi.fn(), confirm: vi.fn() }));
vi.mock('$lib/api/client', () => ({ api: mocks, ApiError: class ApiError extends Error { constructor(public status: number, message: string) { super(message); } } }));
vi.mock('$lib/stores/confirm.svelte', () => ({ confirmDialog: mocks.confirm }));
import { ApiError } from '$lib/api/client';
import FlavorAutomationPolicyPanel from '../FlavorAutomationPolicyPanel.svelte';
const original = get(auth);
const root = '/api/v1/admin/flavor-automation';
const snapshot = (): FlavorAutomationPolicy => ({ revision: 7, gpu_profiles: [], hosts: [
	{ id: 'host-down', name: 'Down host', removed: false, observed_at: '2026-10-30T00:00:00Z', state: 'down', status: 'disabled', cpu: { capacity: 0, min: 1, step: 1 }, pcpu: { capacity: 16, min: 1, step: 1 }, ram: { total: 65536 }, gpu: { CUSTOM_PCI_10DE_2684: 1 } },
	{ id: 'host-missing', name: 'Missing host', removed: false, observed_at: '2026-10-29T00:00:00Z', state: 'missing', cpu: { total: 8 }, ram: { total: 32768 }, gpu: {} },
	{ id: 'host-retired', name: 'Removed host', removed: true, observed_at: '2026-10-28T00:00:00Z', state: 'up', cpu: { total: 16 }, ram: { total: 65536 }, gpu: {} }
] });
const pciSnapshot = (): PciDevicesSnapshot => ({ alias_source: { state: 'ready', source: 'nova_api_config', observed_at: '2026-10-30T00:00:00Z', message: null }, aliases: [
	{ name: 'RTX-3060-LHR', vendor_id: '10DE', product_id: '2504', resource_class: 'CUSTOM_PCI_10DE_2504', kind: 'gpu', device_name: 'RTX 3060 LHR', selectable: true, mapped_groups: [] },
	{ name: 'RTX-3060-Audio', vendor_id: '10DE', product_id: '228E', resource_class: 'CUSTOM_PCI_10DE_228E', kind: 'audio', device_name: 'Audio', selectable: true, mapped_groups: [] },
	{ name: 'Unknown-alias', vendor_id: null, product_id: null, resource_class: null, kind: 'unknown', device_name: null, selectable: false, mapped_groups: [] },
	{ name: 'Unsupported-GPU', vendor_id: '10DE', product_id: '2684', resource_class: 'CUSTOM_PCI_10DE_2684', kind: 'gpu', device_name: '4090', selectable: false, mapped_groups: [] }
], inventory: { state: 'partial', errors: ['Usage unavailable'], devices: [{ host: 'compute-1', provider_uuid: 'pci-provider', provider_name: 'compute-1_0000:01:00.1', pci_address: '0000:01:00.1', resource_class: 'CUSTOM_PCI_10DE_228E', vendor_id: '10DE', product_id: '228E', kind: 'audio', total: 2, reserved: 0, used: null, mapped_groups: [] }] } });
beforeEach(() => { vi.resetAllMocks(); auth.set({ ...original, token: 'token', sessionId: 'session-a', userId: 'admin', projectId: 'admin-project', isSystemAdmin: true }); authReady.set(true); projectSwitching.set(false); logoutInProgress.set(false); mocks.get.mockImplementation(path => Promise.resolve(path.endsWith('/pci-devices') ? pciSnapshot() : snapshot())); mocks.confirm.mockResolvedValue(true); });
afterEach(() => { cleanup(); auth.set(original); });
async function addTemplate() {
	await fireEvent.click(screen.getByRole('button', { name: t('addProfile') }));
	await fireEvent.input(screen.getByLabelText(t('profileSlug')), { target: { value: '3060lhr' } });
	await fireEvent.input(screen.getByLabelText(t('profileDisplayName')), { target: { value: 'RTX 3060 LHR' } });
	await fireEvent.click(screen.getByRole('button', { name: t('pciPrimaryAlias') }));
	await fireEvent.click(await screen.findByRole('option', { name: /RTX-3060-LHR/ }));
}
describe('retained host and GPU approval controls', () => {
	it('reads without discovery or approval and distinguishes down, missing and explicit removal', async () => {
		render(FlavorAutomationPolicyPanel); await screen.findByText(t('profilesEmpty'));
		expect(mocks.get).toHaveBeenCalledWith(root + '/policy', 'token', 'admin-project', { cache: 'no-store' });
		const down = screen.getByRole('heading', { name: 'Down host' }).closest('li')!;
		const missing = screen.getByRole('heading', { name: 'Missing host' }).closest('li')!;
		const removed = screen.getByRole('heading', { name: 'Removed host' }).closest('li')!;
		expect(down.textContent).toContain(t('hostDown')); expect(down.textContent).toContain(t('hostIncluded'));
		expect(missing.textContent).toContain(t('hostMissing')); expect(missing.textContent).toContain(t('hostIncluded'));
		expect(removed.textContent).toContain(t('hostRemoved'));
		expect(within(down).getByRole('button', { name: t('removeHost') })).toBeTruthy();
		expect(within(removed).getByRole('button', { name: t('reincludeHost') })).toBeTruthy();
		expect(mocks.put).not.toHaveBeenCalled(); expect(mocks.post).not.toHaveBeenCalled();
	});
	it('keeps retained VCPU and PCPU inventory distinct in the host disclosure', async () => {
		render(FlavorAutomationPolicyPanel); await screen.findByText('Down host');
		const row = screen.getByRole('heading', { name: 'Down host' }).closest('li')!;
		await fireEvent.click(within(row).getByText(t('supportedInventory'), { exact: false }));
		const vcpu = within(row).getByText('VCPU').closest('div')!, pcpu = within(row).getByText('PCPU').closest('div')!;
		expect(vcpu.textContent).toContain('"capacity": 0');
		expect(pcpu.textContent).toContain('"capacity": 16');
		expect(mocks.put).not.toHaveBeenCalled();
	});
	it('saves a valid new template as unapproved until explicit checkbox consent', async () => {
		mocks.put.mockImplementation((_path, body) => Promise.resolve({ ...snapshot(), revision: 8, gpu_profiles: body.gpu_profiles }));
		render(FlavorAutomationPolicyPanel); await screen.findByText(t('profilesEmpty')); await addTemplate();
		expect((screen.getByRole('checkbox', { name: t('approveProfile') }) as HTMLInputElement).checked).toBe(false);
		await fireEvent.click(screen.getByRole('button', { name: t('saveProfiles') }));
		await waitFor(() => expect(mocks.put).toHaveBeenCalledTimes(1));
		expect(mocks.put.mock.calls[0]).toEqual([root + '/policy', { revision: 7, gpu_profiles: [{ name: '3060lhr', display_name: 'RTX 3060 LHR', enabled: false, resource_class: 'CUSTOM_PCI_10DE_2504', resource_requirements: { CUSTOM_PCI_10DE_2504: 1 }, extra_specs: { 'pci_passthrough:alias': 'RTX-3060-LHR:1' }, alias_resource_classes: { 'RTX-3060-LHR': 'CUSTOM_PCI_10DE_2504' } }] }, 'token', 'admin-project', expect.objectContaining({ replayOnUnauthorized: false })]);
		await screen.findByText(t('saved'));
		await waitFor(() => expect((screen.getByRole('button', { name: t('refresh') }) as HTMLButtonElement).disabled).toBe(false));
		await fireEvent.click(screen.getByRole('checkbox', { name: t('approveProfile') }));
		await fireEvent.click(screen.getByRole('button', { name: t('saveProfiles') }));
		await waitFor(() => expect(mocks.put).toHaveBeenCalledTimes(2));
		expect(mocks.put.mock.calls[1][1].revision).toBe(8); expect(mocks.put.mock.calls[1][1].gpu_profiles[0].enabled).toBe(true);
	});
	it('blocks malformed resource quantities and protected specs before dispatch', async () => {
		const policy = snapshot(); policy.gpu_profiles = [{ name: '3060lhr', display_name: 'RTX 3060 LHR', enabled: false, resource_class: 'CUSTOM_PCI_10DE_2504', resource_requirements: { CUSTOM_PCI_10DE_2504: 1 }, extra_specs: { 'pci_passthrough:alias': 'RTX-3060-LHR:1', 'custom:operator': 'preserve' }, alias_resource_classes: { 'RTX-3060-LHR': 'CUSTOM_PCI_10DE_2504' } }];
		mocks.get.mockImplementation(path => Promise.resolve(path.endsWith('/pci-devices') ? pciSnapshot() : policy));
		render(FlavorAutomationPolicyPanel); await screen.findByLabelText(t('profileResources'));
		await fireEvent.input(screen.getByLabelText(t('profileResources')), { target: { value: '{"CUSTOM_PCI_10DE_2504":2}' } });
		expect((screen.getByRole('button', { name: t('saveProfiles') }) as HTMLButtonElement).disabled).toBe(true);
		await fireEvent.input(screen.getByLabelText(t('profileResources')), { target: { value: '{"CUSTOM_PCI_10DE_2504":1}' } });
		await fireEvent.input(screen.getByLabelText(t('profileSpecs')), { target: { value: '{"afterglow:managed_by":"manual"}' } });
		expect(screen.getByText(t('invalidProfile'))).toBeTruthy(); expect(mocks.put).not.toHaveBeenCalled();
	});
	it('requires explicit stock Nova removal confirmation and exact host revision', async () => {
		mocks.put.mockResolvedValue({ ...snapshot(), revision: 8 });
		render(FlavorAutomationPolicyPanel); await screen.findByText('Down host');
		const down = screen.getByRole('heading', { name: 'Down host' }).closest('li')!;
		await fireEvent.click(within(down).getByRole('button', { name: t('removeHost') }));
		await waitFor(() => expect(mocks.put).toHaveBeenCalledWith(root + '/hosts/host-down', { revision: 7, removed: true }, 'token', 'admin-project', expect.objectContaining({ replayOnUnauthorized: false })));
		expect(mocks.confirm).toHaveBeenCalledWith(t('removeHostConfirm', { name: 'Down host', id: 'host-down' }), { confirmLabel: t('removeHost'), confirmVariant: 'danger' });
	});
	it('re-inclusion explicitly does not enable native maintenance services', async () => {
		mocks.put.mockResolvedValue({ ...snapshot(), revision: 8 });
		render(FlavorAutomationPolicyPanel); await screen.findByText('Removed host');
		await fireEvent.click(screen.getByRole('button', { name: t('reincludeHost') }));
		await waitFor(() => expect(mocks.put).toHaveBeenCalledWith(root + '/hosts/host-retired', { revision: 7, removed: false }, 'token', 'admin-project', expect.objectContaining({ replayOnUnauthorized: false })));
		expect(mocks.confirm.mock.calls[0][0]).toBe(t('reincludeConfirm', { name: 'Removed host', id: 'host-retired' }));
		expect(mocks.post).not.toHaveBeenCalled();
	});
	it('does not replay uncertain discovery or overwrite drafts after revision conflict', async () => {
		mocks.post.mockRejectedValue(new ApiError(503, 'Observation unavailable'));
		render(FlavorAutomationPolicyPanel); await screen.findByText(t('profilesEmpty'));
		await fireEvent.click(screen.getByRole('button', { name: t('discoverHosts') })); await screen.findByText(t('unknownOutcome'));
		expect(mocks.post).toHaveBeenCalledTimes(1); expect((screen.getByRole('button', { name: t('discoverHosts') }) as HTMLButtonElement).disabled).toBe(true);
		await fireEvent.click(screen.getByRole('button', { name: t('refresh') })); await screen.findByText(t('profilesEmpty')); await addTemplate();
		mocks.put.mockRejectedValue(new ApiError(409, 'revision conflict'));
		await fireEvent.click(screen.getByRole('button', { name: t('saveProfiles') })); await screen.findByText(t('conflict'));
		expect((screen.getByLabelText(t('profileSlug')) as HTMLInputElement).value).toBe('3060lhr');
		expect((screen.getByRole('button', { name: t('saveProfiles') }) as HTMLButtonElement).disabled).toBe(true); expect(mocks.put).toHaveBeenCalledTimes(1);
	});
	it('discards pending confirmation across session ABA before host mutation', async () => {
		const confirmation = Promise.withResolvers<boolean>(); mocks.confirm.mockReturnValue(confirmation.promise);
		render(FlavorAutomationPolicyPanel); await screen.findByText('Removed host');
		await fireEvent.click(screen.getByRole('button', { name: t('reincludeHost') })); await waitFor(() => expect(mocks.confirm).toHaveBeenCalledTimes(1));
		const prior = get(auth); auth.set({ ...prior, sessionId: 'other' }); auth.set(prior); confirmation.resolve(true); await Promise.resolve();
		expect(mocks.put).not.toHaveBeenCalled();
	});
	it('discards late discovery after scope change and unmount', async () => {
		const pending = Promise.withResolvers<FlavorAutomationPolicy>(); mocks.post.mockReturnValue(pending.promise);
		const changed = vi.fn(), view = render(FlavorAutomationPolicyPanel, { onChanged: changed }); await screen.findByText('Down host');
		await fireEvent.click(screen.getByRole('button', { name: t('discoverHosts') }));
		auth.update(state => ({ ...state, projectId: 'other-project' })); view.unmount(); pending.resolve({ ...snapshot(), revision: 999 }); await Promise.resolve();
		expect(changed).not.toHaveBeenCalled(); expect(screen.queryByText(t('revision', { revision: 999 }))).toBeNull();
	});
	it('creates exact GPU and audio mappings without JSON and keeps blank display name optional', async () => {
		mocks.put.mockImplementation((_path, body) => Promise.resolve({ ...snapshot(), revision: 8, gpu_profiles: body.gpu_profiles }));
		render(FlavorAutomationPolicyPanel); await screen.findByText(t('profilesEmpty')); await addTemplate();
		await fireEvent.input(screen.getByLabelText(t('profileDisplayName')), { target: { value: '' } });
		await fireEvent.click(screen.getByRole('checkbox', { name: /RTX-3060-Audio/ }));
		expect(screen.queryByLabelText(t('profileSpecs'))).toBeNull();
		await fireEvent.click(screen.getByRole('button', { name: t('saveProfiles') }));
		await waitFor(() => expect(mocks.put).toHaveBeenCalledTimes(1));
		expect(mocks.put.mock.calls[0][1].gpu_profiles[0]).toEqual({ name: '3060lhr', display_name: '3060lhr', enabled: false, resource_class: 'CUSTOM_PCI_10DE_2504', resource_requirements: { CUSTOM_PCI_10DE_2504: 1, CUSTOM_PCI_10DE_228E: 1 }, extra_specs: { 'pci_passthrough:alias': 'RTX-3060-LHR:1,RTX-3060-Audio:1' }, alias_resource_classes: { 'RTX-3060-LHR': 'CUSTOM_PCI_10DE_2504', 'RTX-3060-Audio': 'CUSTOM_PCI_10DE_228E' } });
	});
	it('shows configured aliases without inventory and nullable allocated use without claiming zero', async () => {
		render(FlavorAutomationPolicyPanel); await screen.findByText(t('profilesEmpty'));
		expect(mocks.get).toHaveBeenCalledWith(root + '/pci-devices', 'token', 'admin-project', { cache: 'no-store' });
		const aliases = screen.getByRole('list', { name: t('pciConfiguredAliases') });
		expect(within(aliases).getByText('RTX-3060-LHR')).toBeTruthy();
		expect(within(aliases).getByText('Unknown-alias')).toBeTruthy();
		const inventory = screen.getByRole('list', { name: t('pciInventory') });
		expect(inventory.textContent).toContain(`${t('pciAllocated')}: ${t('unknown')}`);
		expect(inventory.textContent).toContain(t('pciUnmapped'));
		expect(screen.getByText(t('pciHelp'))).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: t('addProfile') }));
		await fireEvent.click(screen.getByRole('button', { name: t('pciPrimaryAlias') }));
		expect(screen.queryByRole('option', { name: /Unknown-alias|Unsupported-GPU|RTX-3060-Audio/ })).toBeNull();
	});
	it.each(['partial', 'unavailable'] as const)('blocks new alias grouping for a %s source while preserving custom legacy specs', async state => {
		const devices = pciSnapshot(); devices.alias_source.state = state;
		const profile = { name: 'legacy', display_name: 'Custom legacy', enabled: true, resource_class: 'CUSTOM_PCI_10DE_2504', resource_requirements: { CUSTOM_PCI_10DE_2504: 1 }, extra_specs: { 'pci_passthrough:alias': 'old-exact:1', 'hw:cpu_policy': 'dedicated', 'custom:operator': 'keep-me' }, alias_resource_classes: { 'old-exact': 'CUSTOM_PCI_10DE_2504' } };
		mocks.get.mockImplementation(path => Promise.resolve(path.endsWith('/pci-devices') ? devices : { ...snapshot(), gpu_profiles: [profile] }));
		mocks.put.mockImplementation((_path, body) => Promise.resolve({ ...snapshot(), revision: 8, gpu_profiles: body.gpu_profiles }));
		render(FlavorAutomationPolicyPanel); await screen.findByLabelText(t('profileSpecs'));
		expect((screen.getByRole('button', { name: t('addProfile') }) as HTMLButtonElement).disabled).toBe(true);
		await fireEvent.input(screen.getByLabelText(t('profileDisplayName')), { target: { value: 'Renamed legacy' } });
		await fireEvent.click(screen.getByRole('button', { name: t('saveProfiles') }));
		await waitFor(() => expect(mocks.put).toHaveBeenCalledTimes(1));
		expect(mocks.put.mock.calls[0][1].gpu_profiles[0]).toEqual({ ...profile, display_name: 'Renamed legacy' });
	});
	it('keeps existing policies usable after a PCI read failure and discards stale PCI reads across session ABA', async () => {
		const pending = Promise.withResolvers<PciDevicesSnapshot>();
		mocks.get.mockImplementation(path => path.endsWith('/pci-devices') ? pending.promise : Promise.resolve(snapshot()));
		const view = render(FlavorAutomationPolicyPanel); await waitFor(() => expect(mocks.get).toHaveBeenCalledTimes(2));
		mocks.get.mockImplementation(path => path.endsWith('/pci-devices') ? Promise.reject(new ApiError(503, 'Unavailable')) : Promise.resolve(snapshot()));
		const prior = get(auth); auth.set({ ...prior, sessionId: 'other' }); auth.set(prior);
		expect(get(authReady)).toBe(false);
		await waitFor(() => expect(screen.queryByText('Down host')).toBeNull());
		expect(mocks.get).toHaveBeenCalledTimes(2);
		expect(acceptAuthVerification(getAuthVerificationEpoch(), {})).toBe(true);
		await screen.findByText(t('pciLoadFailed')); await screen.findByText('Down host');
		expect(mocks.get).toHaveBeenCalledWith(root + '/policy', 'token', 'admin-project', { cache: 'no-store' });
		expect(mocks.get.mock.calls.filter(([path]) => path === root + '/policy')).toHaveLength(2);
		pending.resolve(pciSnapshot()); await pending.promise; await Promise.resolve();
		expect((screen.getByRole('button', { name: t('addProfile') }) as HTMLButtonElement).disabled).toBe(true);
		expect(screen.queryByText('RTX-3060-LHR')).toBeNull(); view.unmount();
	});
	it.each(['primary', 'companion'] as const)('requires distinct explicit consent for an unclassified %s role and resets consent after alias changes', async role => {
		const devices = pciSnapshot();
		devices.aliases.push({ name: 'New-device', vendor_id: '1234', product_id: '5678', resource_class: 'CUSTOM_PCI_1234_5678', kind: 'unknown', device_name: null, selectable: true, mapped_groups: [] });
		mocks.get.mockImplementation(path => Promise.resolve(path.endsWith('/pci-devices') ? devices : snapshot()));
		mocks.put.mockImplementation((_path, body) => Promise.resolve({ ...snapshot(), revision: 8, gpu_profiles: body.gpu_profiles }));
		render(FlavorAutomationPolicyPanel); await screen.findByText(t('profilesEmpty'));
		await fireEvent.click(screen.getByRole('button', { name: t('addProfile') }));
		await fireEvent.input(screen.getByLabelText(t('profileSlug')), { target: { value: 'new-device' } });
		await fireEvent.click(screen.getByRole('button', { name: t('pciPrimaryAlias') }));
		await fireEvent.click(await screen.findByRole('option', { name: role === 'primary' ? /New-device/ : /RTX-3060-LHR/ }));
		if (role === 'companion') await fireEvent.click(screen.getByRole('checkbox', { name: /New-device/ }));
		const save = screen.getByRole('button', { name: t('saveProfiles') });
		expect((save as HTMLButtonElement).disabled).toBe(true);
		expect((screen.getByRole('checkbox', { name: t('approveProfile') }) as HTMLInputElement).checked).toBe(false);
		await fireEvent.click(screen.getByRole('checkbox', { name: t('pciConfirmUnknown') }));
		expect((save as HTMLButtonElement).disabled).toBe(false);
		await fireEvent.click(screen.getByRole('checkbox', { name: /RTX-3060-Audio/ }));
		expect((screen.getByRole('checkbox', { name: t('pciConfirmUnknown') }) as HTMLInputElement).checked).toBe(false);
		expect((save as HTMLButtonElement).disabled).toBe(true);
		await fireEvent.click(screen.getByRole('checkbox', { name: t('pciConfirmUnknown') })); await fireEvent.click(save);
		await waitFor(() => expect(mocks.put).toHaveBeenCalledTimes(1));
		expect(mocks.put.mock.calls[0][1].gpu_profiles[0].enabled).toBe(false);
		expect(mocks.put.mock.calls[0][1].gpu_profiles[0].alias_resource_classes['New-device']).toBe('CUSTOM_PCI_1234_5678');
	});
	it('keeps generated groups guided after save and refresh while preserving untouched custom profiles', async () => {
		const custom = { name: 'custom', display_name: 'Custom template', enabled: true, resource_class: 'CUSTOM_PCI_10DE_2684', resource_requirements: { CUSTOM_PCI_10DE_2684: 1 }, extra_specs: { 'pci_passthrough:alias': 'old-custom:1', 'hw:cpu_policy': 'dedicated', 'custom:operator': 'do-not-drop' }, alias_resource_classes: { 'old-custom': 'CUSTOM_PCI_10DE_2684' } };
		let policy = { ...snapshot(), gpu_profiles: [custom] };
		mocks.get.mockImplementation(path => Promise.resolve(path.endsWith('/pci-devices') ? pciSnapshot() : policy));
		mocks.put.mockImplementation((_path, body) => { policy = { ...policy, revision: policy.revision + 1, gpu_profiles: body.gpu_profiles }; return Promise.resolve(policy); });
		render(FlavorAutomationPolicyPanel); await screen.findByLabelText(t('profileSpecs'));
		await fireEvent.click(screen.getByRole('button', { name: t('addProfile') }));
		const created = screen.getByRole('group', { name: t('newProfile') });
		await fireEvent.input(within(created).getByLabelText(t('profileSlug')), { target: { value: '3060lhr' } });
		await fireEvent.click(within(created).getByRole('button', { name: t('pciPrimaryAlias') }));
		await fireEvent.click(await screen.findByRole('option', { name: /RTX-3060-LHR/ }));
		await fireEvent.click(screen.getByRole('button', { name: t('saveProfiles') }));
		await screen.findByText(t('saved'));
		await waitFor(() => expect((screen.getByRole('button', { name: t('refresh') }) as HTMLButtonElement).disabled).toBe(false));
		expect(mocks.put.mock.calls[0][1].gpu_profiles[0]).toEqual(custom);
		expect(within(screen.getByRole('group', { name: '3060lhr' })).getByRole('button', { name: t('pciPrimaryAlias') })).toBeTruthy();
		await fireEvent.click(within(screen.getByRole('group', { name: '3060lhr' })).getByRole('checkbox', { name: /RTX-3060-Audio/ }));
		await fireEvent.click(screen.getByRole('button', { name: t('saveProfiles') }));
		await waitFor(() => expect(mocks.put).toHaveBeenCalledTimes(2));
		expect(mocks.put.mock.calls[1][1].gpu_profiles[0]).toEqual(custom);
		expect(mocks.put.mock.calls[1][1].gpu_profiles[1].extra_specs).toEqual({ 'pci_passthrough:alias': 'RTX-3060-LHR:1,RTX-3060-Audio:1' });
		await waitFor(() => expect((screen.getByRole('button', { name: t('refresh') }) as HTMLButtonElement).disabled).toBe(false));
		await fireEvent.click(screen.getByRole('button', { name: t('refresh') }));
		await waitFor(() => expect(mocks.get.mock.calls.filter(([path]) => path === root + '/policy')).toHaveLength(2));
		const restored = await screen.findByRole('group', { name: '3060lhr' });
		expect(within(restored).queryByLabelText(t('profileSpecs'))).toBeNull();
		await fireEvent.click(within(restored).getByRole('checkbox', { name: /RTX-3060-Audio/ }));
		await fireEvent.click(screen.getByRole('button', { name: t('saveProfiles') }));
		await waitFor(() => expect(mocks.put).toHaveBeenCalledTimes(3));
		expect(mocks.put.mock.calls[2][1].gpu_profiles[0]).toEqual(custom);
		expect(mocks.put.mock.calls[2][1].gpu_profiles[1].extra_specs).toEqual({ 'pci_passthrough:alias': 'RTX-3060-LHR:1' });
	});
	it.each(['ready', 'partial', 'unavailable'] as const)('summarizes %s PCI diagnostics locally without exposing backend messages or traces', async state => {
		const devices = pciSnapshot();
		devices.alias_source.state = state; devices.alias_source.message = 'Internal alias snapshot error at /app/private/nova.conf';
		devices.inventory.state = state; devices.inventory.errors = ['Internal usage query traceback at /srv/internal/provider.py', 'Internal usage query traceback at /srv/internal/provider.py'];
		mocks.get.mockImplementation(path => Promise.resolve(path.endsWith('/pci-devices') ? devices : snapshot()));
		render(FlavorAutomationPolicyPanel); await screen.findByText(t('profilesEmpty'));
		expect(screen.getByText(t(`pciAliasHelp.${state}`))).toBeTruthy();
		expect(screen.getAllByText(t(state === 'unavailable' ? 'pciInventoryHelp.unavailable' : 'pciInventoryHelp.partial'))).toHaveLength(1);
		expect(screen.queryByText(devices.alias_source.message)).toBeNull();
		expect(screen.queryByText(devices.inventory.errors[0])).toBeNull();
		expect(screen.getByRole('list', { name: t('pciInventory') }).textContent).toContain(`${t('pciAllocated')}: ${t('unknown')}`);
		expect(mocks.put).not.toHaveBeenCalled(); expect(mocks.post).not.toHaveBeenCalled();
	});
	it.each(['policy-first', 'pci-first'] as const)('starts policy and PCI reads together and supports %s completion', async order => {
		const policy = Promise.withResolvers<FlavorAutomationPolicy>(), devices = Promise.withResolvers<PciDevicesSnapshot>();
		mocks.get.mockImplementation(path => path.endsWith('/pci-devices') ? devices.promise : policy.promise);
		render(FlavorAutomationPolicyPanel); await waitFor(() => expect(mocks.get).toHaveBeenCalledTimes(2));
		if (order === 'policy-first') {
			policy.resolve(snapshot()); await screen.findByText('Down host');
			expect((screen.getByRole('button', { name: t('addProfile') }) as HTMLButtonElement).disabled).toBe(true);
			expect((screen.getByRole('button', { name: t('discoverHosts') }) as HTMLButtonElement).disabled).toBe(false);
			expect(screen.queryByText('RTX-3060-LHR')).toBeNull();
			devices.resolve(pciSnapshot());
		} else {
			devices.resolve(pciSnapshot()); await Promise.resolve();
			expect(screen.queryByText('Down host')).toBeNull();
			policy.resolve(snapshot());
		}
		await screen.findByText('RTX-3060-LHR');
		expect((screen.getByRole('button', { name: t('addProfile') }) as HTMLButtonElement).disabled).toBe(false);
		expect(mocks.put).not.toHaveBeenCalled(); expect(mocks.post).not.toHaveBeenCalled();
	});
	it('preserves existing advanced edits when slow PCI observations finish after policy display', async () => {
		const devices = Promise.withResolvers<PciDevicesSnapshot>();
		const policy = snapshot(); policy.gpu_profiles = [{ name: 'legacy', display_name: 'Legacy', enabled: false, resource_class: 'CUSTOM_PCI_10DE_2504', resource_requirements: { CUSTOM_PCI_10DE_2504: 1 }, extra_specs: { 'pci_passthrough:alias': 'RTX-3060-LHR:1', 'custom:operator': 'keep' }, alias_resource_classes: { 'RTX-3060-LHR': 'CUSTOM_PCI_10DE_2504' } }];
		mocks.get.mockImplementation(path => path.endsWith('/pci-devices') ? devices.promise : Promise.resolve(policy));
		render(FlavorAutomationPolicyPanel); await screen.findByLabelText(t('profileDisplayName'));
		await fireEvent.input(screen.getByLabelText(t('profileDisplayName')), { target: { value: 'Unsaved legacy edit' } });
		devices.resolve(pciSnapshot()); await screen.findByText('RTX-3060-LHR');
		expect((screen.getByLabelText(t('profileDisplayName')) as HTMLInputElement).value).toBe('Unsaved legacy edit');
		expect((screen.getByLabelText(t('profileSpecs')) as HTMLTextAreaElement).value).toContain('custom:operator');
	});
	it('discards independently pending policy and PCI results after a scope change', async () => {
		const policy = Promise.withResolvers<FlavorAutomationPolicy>(), devices = Promise.withResolvers<PciDevicesSnapshot>();
		mocks.get.mockImplementation(path => path.endsWith('/pci-devices') ? devices.promise : policy.promise);
		render(FlavorAutomationPolicyPanel); await waitFor(() => expect(mocks.get).toHaveBeenCalledTimes(2));
		mocks.get.mockImplementation(path => Promise.resolve(path.endsWith('/pci-devices') ? pciSnapshot() : snapshot()));
		auth.update(state => ({ ...state, projectId: 'other-project' }));
		expect(get(authReady)).toBe(false);
		await Promise.resolve(); expect(mocks.get).toHaveBeenCalledTimes(2);
		expect(screen.queryByText('Down host')).toBeNull();
		expect(acceptAuthVerification(getAuthVerificationEpoch(), {})).toBe(true);
		await screen.findByText('Down host');
		expect(mocks.get).toHaveBeenCalledWith(root + '/policy', 'token', 'other-project', { cache: 'no-store' });
		expect(mocks.get).toHaveBeenCalledWith(root + '/pci-devices', 'token', 'other-project', { cache: 'no-store' });
		const staleDevices = pciSnapshot(); staleDevices.aliases[0].name = 'Stale-GPU';
		policy.resolve({ ...snapshot(), revision: 999 }); devices.resolve(staleDevices);
		await Promise.all([policy.promise, devices.promise]); await Promise.resolve();
		expect(screen.queryByText('Stale-GPU')).toBeNull();
		expect(screen.queryByText(t('revision', { revision: 999 }))).toBeNull();
	});
	it('keeps discovery available during slow PCI loading and ignores the superseded PCI response', async () => {
		const pending = Promise.withResolvers<PciDevicesSnapshot>();
		const fresh = pciSnapshot(); fresh.aliases[0].name = 'Fresh-GPU';
		let pciReads = 0;
		mocks.get.mockImplementation(path => path.endsWith('/pci-devices') ? ++pciReads === 1 ? pending.promise : Promise.resolve(fresh) : Promise.resolve(snapshot()));
		mocks.post.mockResolvedValue({ ...snapshot(), revision: 8 });
		render(FlavorAutomationPolicyPanel); await screen.findByText('Down host');
		await fireEvent.click(screen.getByRole('button', { name: t('discoverHosts') }));
		await screen.findByText('Fresh-GPU');
		pending.resolve(pciSnapshot()); await pending.promise; await Promise.resolve();
		expect(screen.queryByText('RTX-3060-LHR')).toBeNull();
		expect(screen.getByText('Fresh-GPU')).toBeTruthy();
		expect(mocks.post).toHaveBeenCalledTimes(1);
	});
	it('unlocks a confirmed save before slow PCI refresh and preserves edits when that refresh completes', async () => {
		const pending = Promise.withResolvers<PciDevicesSnapshot>();
		let pciReads = 0;
		mocks.get.mockImplementation(path => path.endsWith('/pci-devices') ? ++pciReads === 1 ? Promise.resolve(pciSnapshot()) : pending.promise : Promise.resolve(snapshot()));
		mocks.put.mockImplementation((_path, body) => Promise.resolve({ ...snapshot(), revision: 8, gpu_profiles: body.gpu_profiles }));
		render(FlavorAutomationPolicyPanel); await screen.findByText(t('profilesEmpty')); await addTemplate();
		await fireEvent.click(screen.getByRole('button', { name: t('saveProfiles') }));
		await screen.findByText(t('saved'));
		await waitFor(() => expect((screen.getByRole('button', { name: t('refresh') }) as HTMLButtonElement).disabled).toBe(false));
		await fireEvent.input(screen.getByLabelText(t('profileDisplayName')), { target: { value: 'Edit during PCI refresh' } });
		expect((screen.getByRole('button', { name: t('saveProfiles') }) as HTMLButtonElement).disabled).toBe(false);
		pending.resolve(pciSnapshot()); await pending.promise; await Promise.resolve();
		expect((screen.getByLabelText(t('profileDisplayName')) as HTMLInputElement).value).toBe('Edit during PCI refresh');
		expect(mocks.put).toHaveBeenCalledTimes(1);
	});
	it('blocks a dirty guided profile when refreshed alias identity changes without rewriting the draft', async () => {
		const pending = Promise.withResolvers<PciDevicesSnapshot>();
		let pciReads = 0;
		mocks.get.mockImplementation(path => path.endsWith('/pci-devices') ? ++pciReads === 1 ? Promise.resolve(pciSnapshot()) : pending.promise : Promise.resolve(snapshot()));
		mocks.put.mockImplementation((_path, body) => Promise.resolve({ ...snapshot(), revision: 8, gpu_profiles: body.gpu_profiles }));
		render(FlavorAutomationPolicyPanel); await screen.findByText(t('profilesEmpty')); await addTemplate();
		await fireEvent.click(screen.getByRole('button', { name: t('saveProfiles') })); await screen.findByText(t('saved'));
		await waitFor(() => expect((screen.getByRole('button', { name: t('refresh') }) as HTMLButtonElement).disabled).toBe(false));
		await fireEvent.input(screen.getByLabelText(t('profileDisplayName')), { target: { value: 'Preserve my pending edit' } });
		const changed = pciSnapshot(); changed.aliases[0].product_id = '2684'; changed.aliases[0].resource_class = 'CUSTOM_PCI_10DE_2684';
		pending.resolve(changed);
		await waitFor(() => expect((screen.getByRole('button', { name: t('saveProfiles') }) as HTMLButtonElement).disabled).toBe(true));
		expect((screen.getByLabelText(t('profileDisplayName')) as HTMLInputElement).value).toBe('Preserve my pending edit');
		expect(screen.getByText(t('invalidProfile'))).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: t('saveProfiles') }));
		expect(mocks.put).toHaveBeenCalledTimes(1);
		expect(mocks.put.mock.calls[0][1].gpu_profiles[0].resource_class).toBe('CUSTOM_PCI_10DE_2504');
	});
});
