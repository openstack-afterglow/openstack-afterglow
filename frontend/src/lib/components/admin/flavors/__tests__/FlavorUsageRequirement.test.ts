import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { auth } from '$lib/stores/auth';
import { api } from '$lib/api/client';
import { t } from '$lib/i18n/ns/admin-compute';
import { t as usage } from '$lib/i18n/ns/usage-schedule';
import { requiresUsageSchedule } from '$lib/utils/instanceUsage';
import FlavorExtraSpecsTab from '../FlavorExtraSpecsTab.svelte';

vi.mock('$lib/api/client', () => ({ api: { get: vi.fn(), post: vi.fn(), put: vi.fn() }, ApiError: class extends Error {} }));

const flavor = { id: 'small-flavor', name: 'small', vcpus: 2, ram: 2048, disk: 20, is_public: true,
	description: null, extra_specs: {}, is_gpu: false, gpu_count: 0 };
const managed = { ...flavor, description: 'afterglow:domain-compute-v1:claim',
	extra_specs: { 'afterglow:managed_by': 'domain-compute-v1', 'hw:cpu_policy': 'shared' } };
interface UsageRequirementResult {
	flavor_id: string;
	usage_schedule_required: boolean;
	additional_requirement: boolean;
}
const result = (id = flavor.id, required = true, baseline = false) => ({ flavor_id: id,
	usage_schedule_required: required || baseline, additional_requirement: required });
const checkbox = () => screen.getByRole('checkbox', { name: usage('flavorLabel') }) as HTMLInputElement;
const save = () => screen.getByRole('button', { name: t('flavors.specs.save') }) as HTMLButtonElement;

beforeEach(() => {
	vi.clearAllMocks();
	vi.mocked(api.get).mockResolvedValue({ devices: [] });
	vi.mocked(api.put).mockResolvedValue(result());
	auth.update(value => ({ ...value, token: 'operator', projectId: 'operator-project', isSystemAdmin: true }));
});

describe('additive usage flavor designation', () => {
	it.each([flavor, managed])('changes native annotation through dedicated endpoint for $description', async (target) => {
		const onChanged = vi.fn();
		const { container } = render(FlavorExtraSpecsTab, { flavor: target, onChanged });
		expect(checkbox().checked).toBe(false);
		await fireEvent.click(checkbox());
		await fireEvent.click(save());
		await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1));
		expect(api.put).toHaveBeenCalledWith('/api/v1/admin/flavors/small-flavor/usage-schedule-requirement',
			{ required: true }, 'operator', 'operator-project');
		expect(api.post).not.toHaveBeenCalled();
		expect(checkbox().checked).toBe(true);
		expect(save().disabled).toBe(true);
		if (target === managed) {
			expect(container.querySelector('select')).toBeNull();
			expect(screen.getByText('hw:cpu_policy')).toBeTruthy();
		}
		expect(requiresUsageSchedule({ ...target, extra_specs: { ...target.extra_specs, 'afterglow:usage_schedule_required': 'true' } })).toBe(true);
	});

	it.each([{ vcpus: 12 }, { ram: 65536 }, { is_gpu: true }])('removes only additional flag, never baseline $vcpus $ram $is_gpu', async (baseline) => {
		const target = { ...managed, ...baseline, usage_schedule_required: true,
			extra_specs: { ...managed.extra_specs, 'afterglow:usage_schedule_required': 'true' } };
		vi.mocked(api.put).mockResolvedValue(result(target.id, false, true));
		const onChanged = vi.fn();
		render(FlavorExtraSpecsTab, { flavor: target, onChanged });
		expect(screen.getByText(usage('required'))).toBeTruthy();
		await fireEvent.click(checkbox());
		await fireEvent.click(save());
		await waitFor(() => expect(onChanged).toHaveBeenCalledOnce());
		expect(api.put).toHaveBeenCalledWith(expect.any(String), { required: false }, 'operator', 'operator-project');
		expect(checkbox().checked).toBe(false);
		expect(screen.getByText(usage('required'))).toBeTruthy();
	});

	it('removes a small flavor designation despite its previous computed requirement', async () => {
		const target = { ...managed, usage_schedule_required: true,
			extra_specs: { ...managed.extra_specs, 'afterglow:usage_schedule_required': 'true' } };
		vi.mocked(api.put).mockResolvedValue(result(target.id, false, false));
		const onChanged = vi.fn();
		render(FlavorExtraSpecsTab, { flavor: target, onChanged });
		expect(screen.queryByText(usage('required'))).toBeNull();
		await fireEvent.click(checkbox());
		await fireEvent.click(save());
		await waitFor(() => expect(onChanged).toHaveBeenCalledOnce());
		expect(checkbox().checked).toBe(false);
		expect(screen.queryByText(usage('saveFailed'))).toBeNull();
		expect(screen.queryByText(usage('required'))).toBeNull();
		expect(save().disabled).toBe(true);
	});

	it('shows failed or foreign readback without claiming a successful change', async () => {
		vi.mocked(api.put).mockResolvedValue(result('foreign'));
		const onChanged = vi.fn();
		render(FlavorExtraSpecsTab, { flavor: managed, onChanged });
		await fireEvent.click(checkbox());
		await fireEvent.click(save());
		await waitFor(() => expect(screen.getByText(usage('saveFailed'))).toBeTruthy());
		expect(onChanged).not.toHaveBeenCalled();
		expect(save().disabled).toBe(false);
	});

	it('rejects late A→B→A responses without changing the new target state', async () => {
		const { promise, resolve } = Promise.withResolvers<UsageRequirementResult>();
		vi.mocked(api.put).mockReturnValueOnce(promise);
		const onChanged = vi.fn();
		const view = render(FlavorExtraSpecsTab, { flavor: managed, onChanged });
		await fireEvent.click(checkbox());
		await fireEvent.click(save());
		await view.rerender({ flavor: { ...managed, id: 'other' }, onChanged });
		await view.rerender({ flavor: managed, onChanged });
		resolve(result());
		await waitFor(() => expect(checkbox().checked).toBe(false));
		expect(onChanged).not.toHaveBeenCalled();
		expect(save().disabled).toBe(true);
	});

	it('clears pending scope and ignores old credentials on project switch', async () => {
		const { promise, reject } = Promise.withResolvers<UsageRequirementResult>();
		vi.mocked(api.put).mockReturnValueOnce(promise);
		const onChanged = vi.fn();
		render(FlavorExtraSpecsTab, { flavor: managed, onChanged });
		await fireEvent.click(checkbox());
		await fireEvent.click(save());
		auth.update(value => ({ ...value, token: 'other-token', projectId: 'other-project' }));
		await waitFor(() => expect(checkbox().checked).toBe(false));
		reject(new Error('old request failed'));
		await waitFor(() => expect(save().disabled).toBe(true));
		expect(screen.queryByText(usage('saveFailed'))).toBeNull();
		expect(onChanged).not.toHaveBeenCalled();
	});
});
