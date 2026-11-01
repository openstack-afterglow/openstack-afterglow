import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, expect, it, vi } from 'vitest';
const mocks = vi.hoisted(() => ({ get: vi.fn().mockResolvedValue([]), put: vi.fn(), post: vi.fn(), delete: vi.fn() }));
vi.mock('$lib/api/client', () => ({ api: mocks, ApiError: class ApiError extends Error {} }));
import FlavorAccessTab from '../FlavorAccessTab.svelte';
import FlavorExtraSpecsTab from '../FlavorExtraSpecsTab.svelte';
const flavor = { id: 'managed-cpu-2', name: 'cpu.2c_4g', vcpus: 2, ram: 4096, disk: 0, is_public: false, description: null, is_gpu: false, gpu_count: 0, extra_specs: { 'afterglow:managed_by': 'domain-compute-v1', 'afterglow:access_mode': 'domain_quota', 'hw:cpu_policy': 'shared' } };
afterEach(() => { cleanup(); vi.clearAllMocks(); });
it('keeps managed hardware specs read-only while allowing only the usage annotation', async () => {
	const onChanged = vi.fn();
	mocks.put.mockResolvedValue({ flavor_id: flavor.id, usage_schedule_required: true, additional_requirement: true });
	render(FlavorExtraSpecsTab, { flavor, onChanged });
	expect(screen.getByText('hw:cpu_policy')).toBeTruthy();
	expect(screen.getByText('shared')).toBeTruthy();
	expect(screen.getByText('hw:cpu_policy').closest('button')).toBeNull();
	expect(screen.queryByRole('textbox')).toBeNull();
	expect(screen.queryByRole('combobox')).toBeNull();
	const buttons = screen.getAllByRole('button');
	expect(buttons).toHaveLength(1);
	expect((buttons[0] as HTMLButtonElement).disabled).toBe(true);
	await fireEvent.click(screen.getByRole('checkbox'));
	await fireEvent.click(buttons[0]);
	await waitFor(() => expect(onChanged).toHaveBeenCalledOnce());
	expect(mocks.put).toHaveBeenCalledTimes(1);
	expect(mocks.put.mock.calls[0].slice(0, 2)).toEqual([
		`/api/v1/admin/flavors/${flavor.id}/usage-schedule-requirement`, { required: true },
	]);
	expect(mocks.get).not.toHaveBeenCalled();
	expect(mocks.post).not.toHaveBeenCalled();
	expect(mocks.delete).not.toHaveBeenCalled();
});
it('keeps managed native access observable without manual ACL or visibility actions', async () => {
	render(FlavorAccessTab, { flavor });
	expect(screen.queryByRole('button')).toBeNull(); expect(screen.queryByRole('combobox')).toBeNull();
	expect(mocks.put).not.toHaveBeenCalled(); expect(mocks.post).not.toHaveBeenCalled(); expect(mocks.delete).not.toHaveBeenCalled();
});

it('protects adopted CPU hardware and ACL using the non-secret management projection while retaining the usage annotation action', async () => {
	const adopted = { ...flavor, id: 'native-manual', name: 'm1.small', display_name: 'cpu.2c_4g', cpu_automation_managed: true, extra_specs: { 'hw:cpu_policy': 'dedicated' } };
	const onChanged = vi.fn();
	mocks.put.mockResolvedValue({ flavor_id: adopted.id, usage_schedule_required: true, additional_requirement: true });
	const specs = render(FlavorExtraSpecsTab, { flavor: adopted, onChanged });
	expect(screen.queryByText('afterglow:cpu_control_token')).toBeNull();
	expect(screen.getByText('dedicated')).toBeTruthy();
	expect(screen.queryByRole('textbox')).toBeNull();
	expect(screen.queryByRole('combobox')).toBeNull();
	await fireEvent.click(screen.getByRole('checkbox'));
	await fireEvent.click(screen.getByRole('button'));
	await waitFor(() => expect(onChanged).toHaveBeenCalledOnce());
	expect(mocks.put.mock.calls[0].slice(0, 2)).toEqual([`/api/v1/admin/flavors/${adopted.id}/usage-schedule-requirement`, { required: true }]);
	specs.unmount();
	render(FlavorAccessTab, { flavor: adopted });
	expect(screen.queryByRole('button')).toBeNull();
	expect(screen.queryByRole('combobox')).toBeNull();
	expect(mocks.post).not.toHaveBeenCalled();
	expect(mocks.delete).not.toHaveBeenCalled();
});
