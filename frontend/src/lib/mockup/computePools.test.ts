import { beforeEach, describe, expect, it } from 'vitest';
import { mockComputePolicy } from './computePools';
import { resetMockupState } from './state';
import type { ComputePool } from '$lib/api/computePools';
import type { FlavorAutomationPolicy, FlavorAutomationStatus } from '$lib/api/flavorAutomation';
const path = '/api/v1/admin/domains/mock-domain/compute-pool';
const root = '/api/v1/admin/flavor-automation';
const query = () => new URLSearchParams();
const read = () => mockComputePolicy('GET', path, query(), undefined, 'admin') as ComputePool;
const policy = () => mockComputePolicy('GET', root + '/policy', query(), undefined, 'admin') as FlavorAutomationPolicy;
beforeEach(resetMockupState);
describe('synthetic stock-API policy tutorial parity', () => {
	it('starts unmanaged with honest Afterglow scope and no implicit GPU approval', () => {
		const pool = read(); expect(pool.state).toBe('unmanaged'); expect(pool.control_scope).toBe('afterglow'); expect(pool.policy_ready).toBe(true); expect(pool.usage.CPU).toBe(12);
		expect(pool.gpu_profiles).toEqual([]); expect(policy().gpu_profiles).toEqual([]);
		expect(pool.limits).toEqual({ CPU: 64, MEMORY_MB: 262144 });
		expect(policy().hosts.find(row => row.state === 'down')?.removed).toBe(false);
		expect(policy().hosts.find(row => row.state === 'missing')?.removed).toBe(false);
	});
	it('explicit false persists pause without changing native quotas', () => {
		read(); const paused = mockComputePolicy('PUT', path, query(), { revision: 0, enabled: false, limits: { CPU: 64, MEMORY_MB: 262144 } }, 'admin') as ComputePool;
		expect(paused.state).toBe('paused'); expect(read().state).toBe('paused'); expect(read().control_scope).toBe('afterglow');
	});
	it('enforces revision, exact project, cap ceiling and snapshot-returning deletion', () => {
		mockComputePolicy('PUT', path, query(), { revision: 0, enabled: true, limits: { CPU: 64 } }, 'admin');
		const target = read().projects[0].id;
		expect(() => mockComputePolicy('PUT', path + '/projects/foreign', query(), { revision: 1, limits: {} }, 'admin')).toThrow('Project not found');
		expect(() => mockComputePolicy('PUT', path + '/projects/' + target, query(), { revision: 1, limits: { CPU: 65 } }, 'admin')).toThrow('ceiling exceeds');
		const saved = mockComputePolicy('PUT', path + '/projects/' + target, query(), { revision: 1, limits: { CPU: 64 } }, 'admin') as ComputePool;
		expect(saved.project_limits[target]).toEqual({ CPU: 64 });
		expect(() => mockComputePolicy('DELETE', path + '/projects/' + target, new URLSearchParams('revision=1'), undefined, 'admin')).toThrow('revision');
		const removed = mockComputePolicy('DELETE', path + '/projects/' + target, new URLSearchParams('revision=2'), undefined, 'admin') as ComputePool;
		expect(removed.revision).toBe(3); expect(removed.project_limits[target]).toBeUndefined();
	});
	it('supports explicit synthetic activation without claiming real cloud writes', () => {
		const result = mockComputePolicy('PUT', root, query(), { revision: 0, enabled: true }, 'admin') as FlavorAutomationStatus;
		expect(result.enabled).toBe(true); expect(result.revision).toBe(1); expect(result.diagnostics[0].code).toBe('synthetic_fixture');
	});
	it('preserves removed hosts across discovery and does not enable native services on re-inclusion', () => {
		const initial = policy(), host = initial.hosts[0];
		mockComputePolicy('PUT', root + '/hosts/' + host.id, query(), { revision: 0, removed: true }, 'admin');
		mockComputePolicy('POST', root + '/discover', query(), {}, 'admin');
		expect(policy().hosts[0].removed).toBe(true); expect(policy().hosts[0].gpu).toEqual(host.gpu);
		expect(() => mockComputePolicy('PUT', root + '/hosts/' + host.id, query(), { revision: 0, removed: false }, 'admin')).toThrow('revision');
		mockComputePolicy('PUT', root + '/hosts/' + host.id, query(), { revision: 2, removed: false }, 'admin');
		expect(policy().hosts[0].removed).toBe(false); expect(policy().hosts[0].status).toBe('disabled');
	});
	it('projects only enabled templates into domain GPU allocation choices', () => {
		const profile = { name: '3060lhr', display_name: 'Synthetic 3060 LHR', enabled: false, resource_class: 'CUSTOM_PCI_10DE_2504', resource_requirements: { CUSTOM_PCI_10DE_2504: 1 }, extra_specs: { 'pci_passthrough:alias': '3060lhr:1' } };
		mockComputePolicy('PUT', root + '/policy', query(), { revision: 0, gpu_profiles: [profile] }, 'admin'); expect(read().gpu_profiles).toEqual([]);
		mockComputePolicy('PUT', root + '/policy', query(), { revision: 1, gpu_profiles: [{ ...profile, enabled: true }] }, 'admin');
		expect(read().gpu_profiles?.map(row => row.name)).toEqual(['3060lhr']);
		expect(() => mockComputePolicy('PUT', root + '/policy', query(), { revision: 1, gpu_profiles: [] }, 'admin')).toThrow('revision');
	});
	it('rejects unapproved GPU limits and companion budgets, then loses readiness when approval is revoked', () => {
		const gpu = 'CUSTOM_PCI_10DE_2504', companion = 'CUSTOM_PCI_10DE_228E';
		const profile = { name: '3060lhr', display_name: 'Synthetic 3060 LHR', enabled: false, resource_class: gpu, resource_requirements: { [gpu]: 1, [companion]: 1 }, extra_specs: { 'pci_passthrough:alias': '3060lhr:1,sound:1' }, alias_resource_classes: { '3060lhr': gpu, sound: companion } };
		mockComputePolicy('PUT', root + '/policy', query(), { revision: 0, gpu_profiles: [profile] }, 'admin');
		expect(() => mockComputePolicy('PUT', path, query(), { revision: 0, enabled: true, limits: { [gpu]: 2 } }, 'admin')).toThrow('compute_pool_gpu_alias_unverified');
		expect(read().revision).toBe(0);
		mockComputePolicy('PUT', root + '/policy', query(), { revision: 1, gpu_profiles: [{ ...profile, enabled: true }] }, 'admin');
		expect(() => mockComputePolicy('PUT', path, query(), { revision: 0, enabled: true, limits: { [companion]: 2 } }, 'admin')).toThrow('compute_pool_gpu_alias_unverified');
		mockComputePolicy('PUT', path, query(), { revision: 0, enabled: true, limits: { [gpu]: 2 } }, 'admin');
		expect(read().policy_ready).toBe(true);
		mockComputePolicy('PUT', root + '/policy', query(), { revision: 2, gpu_profiles: [{ ...profile, enabled: false }] }, 'admin');
		expect(read().policy_ready).toBe(false);
		expect(read().limits[gpu]).toBe(2);
	});
	it('rejects management without tutorial domain management authority', () => {
		expect(() => mockComputePolicy('GET', '/api/v1/iam/compute-pool', query(), undefined, 'on')).toThrow('no domain compute management');
	});
});
