import { fireEvent, render, screen } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import SelectFlavor from '../SelectFlavor.svelte';
import type { FlavorCapacityInfo, FlavorOption } from '$lib/types/flavor';

function capacity(status: FlavorCapacityInfo['status'], overrides: Partial<FlavorCapacityInfo> = {}): FlavorCapacityInfo {
	const available = status === 'available';
	return {
		status,
		checked_at: '2026-10-01T00:00:00+00:00',
		candidate_hosts: available ? 2 : 0,
		cpu_resource_class: 'VCPU',
		remaining_vcpus: available ? 12 : null,
		remaining_ram_mb: available ? 32768 : null,
		...overrides,
	};
}

function flavorWith(
	id: string,
	name: string,
	options: { capacity?: FlavorCapacityInfo | null; selectable?: boolean; blockers?: { code: string; resource?: string; required?: number; remaining?: number }[]; gpus?: Record<string, number> } = {},
): FlavorOption {
	const blockers = options.blockers ?? [];
	const capacityInfo = options.capacity === undefined ? capacity('available') : options.capacity;
	return {
		id,
		name,
		vcpus: 2,
		ram: 4096,
		disk: 20,
		is_public: true,
		extra_specs: options.gpus ? { 'pci_passthrough:alias': Object.entries(options.gpus).map(([alias, count]) => `${alias}:${count}`).join(',') } : {},
		eligibility: {
			selectable: options.selectable ?? blockers.length === 0,
			requirements: { instances: 1, cores: 2, ram_mb: 4096, gpus: options.gpus ?? {} },
			remaining: { instances: 5, cores: 8, ram_mb: 16384, gpus: options.gpus ? Object.fromEntries(Object.keys(options.gpus).map(alias => [alias, 1])) : {} },
			blockers,
			capacity: capacityInfo,
		},
	};
}

const quota = {
	instances: { limit: 10, in_use: 2 },
	cores: { limit: 16, in_use: 4 },
	ram: { limit: 32768, in_use: 4096 },
	gigabytes: { limit: 500, in_use: 100 },
};

function renderFlavors(props: Partial<{ adminMode: boolean; flavors: FlavorOption[]; selectedId: string | null; selectedName: string | null; refreshing: boolean; refreshError: string | null; backgroundRefreshing: boolean; backgroundRefreshError: string | null }> = {}) {
	const onSelect = vi.fn();
	const onRefresh = vi.fn().mockResolvedValue(true);
	const result = render(SelectFlavor, {
		adminMode: props.adminMode,
		flavors: props.flavors ?? [],
		selectedId: props.selectedId ?? null,
		selectedName: props.selectedName ?? null,
		onSelect,
		onRefresh,
		quota,
		refreshing: props.refreshing ?? false,
		refreshError: props.refreshError ?? null,
		backgroundRefreshing: props.backgroundRefreshing ?? false,
		backgroundRefreshError: props.backgroundRefreshError ?? null,
	});
	return { ...result, onSelect, onRefresh };
}

describe('SelectFlavor', () => {
	beforeEach(() => {
		localStorage.clear();
	});

	afterEach(() => {
		vi.useRealTimers();
	});

	it('places quota first and exposes each narrow-panel flavor name without a wide table', () => {
		const { container, onSelect } = renderFlavors({
			flavors: [flavorWith('cpu-1', 'cpu.1c_1g'), flavorWith('gpu-1', 'gpu.1c_8g', { gpus: { RTX3090: 1 } })],
		});

		const quotaPanel = screen.getByText('프로젝트 잔여 쿼터').closest('.order-1');
		expect(quotaPanel).not.toBeNull();
		const mobileCards = container.querySelector('[class~="@2xl/panel:hidden"]');
		expect(mobileCards?.textContent).toContain('cpu.1c_1g');
		expect(mobileCards?.textContent).toContain('gpu.1c_8g');
		expect(container.querySelector('[class~="@2xl/panel:block"]')).not.toBeNull();

		screen.getByRole('button', { name: 'cpu.1c_1g 플레이버 선택' }).click();
		expect(onSelect).toHaveBeenCalledWith('cpu-1', 'cpu.1c_1g');
	});

	it('distinguishes quota, same-host capacity, and unchecked blocks and disables each', async () => {
		const { onSelect } = renderFlavors({
			flavors: [
				flavorWith('ok', 'cpu.2c_4g'),
				flavorWith('quota', 'gpu.quota', { gpus: { RTX3090: 2 }, blockers: [{ code: 'gpu_insufficient', resource: 'RTX3090', required: 2, remaining: 1 }] }),
				flavorWith('host', 'gpu.host', { gpus: { RTX3090: 1 }, capacity: capacity('insufficient'), blockers: [{ code: 'host_capacity_insufficient' }] }),
				flavorWith('cpu-host', 'cpu.16c_64g', { capacity: capacity('insufficient'), blockers: [{ code: 'host_capacity_insufficient' }] }),
				flavorWith('unknown', 'gpu.unknown', { capacity: capacity('unavailable'), blockers: [{ code: 'host_capacity_unavailable' }] }),
				flavorWith('missing', 'gpu.missing', { capacity: null, selectable: false }),
				{ id: 'legacy', name: 'legacy.no_eligibility', vcpus: 1, ram: 1024, disk: 10, is_public: true },
			],
		});

		expect(screen.getByText('생성 가능 (1)')).toBeTruthy();
		await fireEvent.click(screen.getByText('생성 불가 (6)'));

		expect(screen.getAllByText('RTX3090 1개 부족').length).toBeGreaterThanOrEqual(1);
		// A same-host shortage names GPU only for a flavor that asks the host for GPU devices.
		expect(screen.getByRole('button', { name: 'gpu.host 플레이버 선택' }).textContent).toContain('한 호스트에 CPU·RAM·GPU 여유 없음');
		const cpuShortage = screen.getByRole('button', { name: 'cpu.16c_64g 플레이버 선택' }).textContent;
		expect(cpuShortage).toContain('한 호스트에 CPU·RAM 여유 없음');
		expect(cpuShortage).not.toContain('GPU');
		expect(screen.getAllByText('호스트 용량 확인 불가').length).toBeGreaterThanOrEqual(1);
		expect(screen.getAllByText('쿼터 또는 호스트 용량 확인 불가').length).toBeGreaterThanOrEqual(2);

		for (const name of ['gpu.quota', 'gpu.host', 'cpu.16c_64g', 'gpu.unknown', 'gpu.missing', 'legacy.no_eligibility']) {
			const button = screen.getByRole('button', { name: `${name} 플레이버 선택` });
			expect(button.hasAttribute('disabled')).toBe(true);
			await fireEvent.click(button);
		}
		expect(onSelect).not.toHaveBeenCalled();
	});

	it('locks selection during a manual refresh and after its failure', async () => {
		const flavors = [flavorWith('ok', 'cpu.2c_4g')];
		const pending = renderFlavors({ flavors, refreshing: true });
		const button = screen.getByRole('button', { name: 'cpu.2c_4g 플레이버 선택' });
		expect(button.hasAttribute('disabled')).toBe(true);
		await fireEvent.click(button);
		expect(pending.onSelect).not.toHaveBeenCalled();
		pending.unmount();

		const failed = renderFlavors({ flavors, refreshError: '데이터 로드 실패 (503)' });
		expect(screen.getByRole('alert').textContent).toContain('503');
		expect(screen.getByRole('button', { name: 'cpu.2c_4g 플레이버 선택' }).hasAttribute('disabled')).toBe(true);
		await fireEvent.click(screen.getByRole('button', { name: '다시 확인' }));
		expect(failed.onRefresh).toHaveBeenCalledWith('manual');
	});

	it('keeps selection usable during and after a failed periodic refresh', async () => {
		const flavors = [flavorWith('ok', 'cpu.2c_4g')];
		const pending = renderFlavors({ flavors, backgroundRefreshing: true });
		expect(screen.getByRole('status').textContent).not.toContain('선택과 진행을 보류');
		const button = screen.getByRole('button', { name: 'cpu.2c_4g 플레이버 선택' });
		expect(button.hasAttribute('disabled')).toBe(false);
		await fireEvent.click(button);
		expect(pending.onSelect).toHaveBeenCalledWith('ok', 'cpu.2c_4g');
		pending.unmount();

		const failed = renderFlavors({ flavors, backgroundRefreshError: '데이터 로드 실패 (503)' });
		expect(screen.getByText('최근 자동 확인 실패 · 생성 직전에 다시 확인합니다')).toBeTruthy();
		expect(screen.queryByRole('alert')).toBeNull();
		const usableButton = screen.getByRole('button', { name: 'cpu.2c_4g 플레이버 선택' });
		expect(usableButton.hasAttribute('disabled')).toBe(false);
		await fireEvent.click(usableButton);
		expect(failed.onSelect).toHaveBeenCalledWith('ok', 'cpu.2c_4g');
	});

	it.each([
		['unverified capacity (consumer)', capacity('unavailable'), false],
		['missing capacity (consumer)', null, false],
		['unverified capacity (administrator)', capacity('unavailable'), true],
		['missing capacity (administrator)', null, true],
	] as const)('never admits creation from %s without a blocker code', async (_label, capacityInfo, adminMode) => {
		const { onSelect } = renderFlavors({
			adminMode,
			flavors: [flavorWith('cpu', 'cpu.16c_128g', { capacity: capacityInfo })],
			selectedId: 'cpu',
			selectedName: 'cpu.16c_128g',
		});
		expect(screen.getByText('생성 가능 (0)')).toBeTruthy();
		expect(screen.getByText('선택한 플레이버로 지금 생성할 수 없습니다')).toBeTruthy();
		await fireEvent.click(screen.getByText('생성 불가 (1)'));
		const button = screen.getByRole('button', { name: 'cpu.16c_128g 플레이버 선택' });
		expect(button.hasAttribute('disabled')).toBe(true);
		await fireEvent.click(button);
		expect(onSelect).not.toHaveBeenCalled();
	});

	it.each([
		['gpu.host', { RTX3090: 1 }, '한 호스트에 CPU·RAM·GPU 여유 없음'],
		['cpu.16c_64g', undefined, '한 호스트에 CPU·RAM 여유 없음'],
	] as const)('keeps a newly blocked %s selection recognizable instead of choosing another flavor', (name, gpus, label) => {
		const { onSelect } = renderFlavors({
			flavors: [
				flavorWith('ok', 'cpu.2c_4g'),
				flavorWith('host', name, { gpus, capacity: capacity('insufficient'), blockers: [{ code: 'host_capacity_insufficient' }] }),
			],
			selectedId: 'host',
			selectedName: name,
		});
		const notice = screen.getByText('선택한 플레이버로 지금 생성할 수 없습니다').closest('[role="status"]');
		expect(notice?.textContent).toContain(name);
		expect(notice?.textContent).toContain(`${label}.`);
		expect(notice?.textContent?.includes('GPU')).toBe(gpus !== undefined);
		expect(onSelect).not.toHaveBeenCalled();
	});

	it('hides host limits and scheduler diagnostics from consumer choices and selection without changing admission', async () => {
		const { container, onSelect } = renderFlavors({
			flavors: [flavorWith('ded', 'cpu.dedicated', {
				capacity: capacity('available', { cpu_resource_class: 'PCPU', remaining_vcpus: 6, remaining_ram_mb: 24576, numa_unverified: true }),
			})],
			selectedId: 'ded',
		});

		// Includes the selected panel and both responsive list variants, even their hidden DOM.
		expect(container.textContent).not.toMatch(/VM당 최대|PCPU 6|RAM 24 GB|호스트 2대|NUMA|근접성|Nova|No valid host/);
		expect(screen.getByText('프로젝트 잔여 쿼터')).toBeTruthy();
		expect(screen.getByText('현재 대상 프로젝트 잔여 쿼터')).toBeTruthy();
		expect(screen.getByText('생성 가능 (1)')).toBeTruthy();
		const button = screen.getByRole('button', { name: 'cpu.dedicated 플레이버 선택' });
		expect(button.textContent).toContain('4 GB');
		expect(button.hasAttribute('disabled')).toBe(false);
		await fireEvent.click(button);
		expect(onSelect).toHaveBeenCalledWith('ded', 'cpu.dedicated');
	});

	it('shows the paired same-host CPU/RAM snapshot in administrator mode', () => {
		renderFlavors({
			adminMode: true,
			flavors: [flavorWith('ded', 'cpu.dedicated', { capacity: capacity('available', { cpu_resource_class: 'PCPU', remaining_vcpus: 6, remaining_ram_mb: 24576 }) })],
			selectedId: 'ded',
		});
		expect(screen.getByText(/PCPU 6 · RAM 24 GB/, { selector: 'dd' })).toBeTruthy();
		expect(screen.getByText('한 호스트 기준 VM당 최대 (스냅샷)')).toBeTruthy();
		expect(screen.getAllByText('한 호스트 기준 VM당 최대 PCPU 6 · RAM 24 GB').length).toBeGreaterThanOrEqual(1);
		expect(screen.getByText('조건을 만족하는 호스트 2대 중 한 호스트에서 함께 확인한 값')).toBeTruthy();
	});

	it('keeps a host-total fit selectable while disclosing the unverified NUMA cell in administrator mode', async () => {
		const { onSelect } = renderFlavors({
			adminMode: true,
			flavors: [
				flavorWith('numa', 'gpu.3090ti_8c_64g', {
					capacity: capacity('available', { numa_unverified: true, remaining_vcpus: 36, remaining_ram_mb: 87125 }),
				}),
			],
			selectedId: 'numa',
		});

		expect(screen.getByText('생성 가능 (1)')).toBeTruthy();
		expect(screen.getAllByText('호스트 합계 기준 · NUMA 셀·GPU 근접성 미확인 · Nova 최종 확인').length).toBeGreaterThanOrEqual(1);
		expect(screen.getByText(/단일 NUMA 셀 여유와 GPU의 NUMA 근접성은 확인하지 않았습니다/)).toBeTruthy();
		expect(screen.getByText(/No valid host로 거부될 수 있습니다/)).toBeTruthy();
		const button = screen.getByRole('button', { name: 'gpu.3090ti_8c_64g 플레이버 선택' });
		expect(button.hasAttribute('disabled')).toBe(false);
		await fireEvent.click(button);
		expect(onSelect).toHaveBeenCalledWith('numa', 'gpu.3090ti_8c_64g');
	});

	it('runs periodic refresh only while mounted', async () => {
		vi.useFakeTimers();
		const { onRefresh, unmount } = renderFlavors({ flavors: [flavorWith('ok', 'cpu.2c_4g')] });
		expect(onRefresh).not.toHaveBeenCalled();
		await vi.advanceTimersByTimeAsync(15_000);
		expect(onRefresh).toHaveBeenCalledWith('periodic');
		const callsBeforeUnmount = onRefresh.mock.calls.length;
		unmount();
		await vi.advanceTimersByTimeAsync(60_000);
		expect(onRefresh).toHaveBeenCalledTimes(callsBeforeUnmount);
	});
});
