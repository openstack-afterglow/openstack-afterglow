import { fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import SelectFlavor from '../SelectFlavor.svelte';
import type { FlavorCapacityInfo, FlavorOption } from '$lib/types/flavor';
import { t as tp } from '$lib/i18n/ns/compute-pools';
import { t } from '$lib/i18n/ns/vm-wizard';
import { t as tc } from '$lib/i18n/ns/common';
import { consumerFlavorLabel } from '$lib/utils/flavorDisplay';

const selectionName = (flavor: FlavorOption) => t('flavor.selectLabel', { name: consumerFlavorLabel(flavor) });

const media = vi.hoisted(() => {
	const events = new EventTarget();
	const query = {
		matches: true, media: '(min-width: 1024px)', onchange: null,
		addEventListener: events.addEventListener.bind(events), removeEventListener: events.removeEventListener.bind(events),
		dispatchEvent: events.dispatchEvent.bind(events), addListener: () => undefined, removeListener: () => undefined,
	};
	vi.stubGlobal('matchMedia', () => query);
	return query;
});

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

function gpuFlavor(id: string, model: string): FlavorOption {
	return {
		...flavorWith(id, `gpu.${id}`),
		extra_specs: { 'afterglow:managed_by': 'domain-compute-v1', 'afterglow:access_mode': 'gpu_quota', 'pci_passthrough:alias': `graphics-${model}:1,sound-${model}:1` },
		gpu_primary_aliases: [{ name: `graphics-${model}`, count: 1, resource_class: `CUSTOM_PCI_${model}`, profile_name: model }],
	};
}

const quota = {
	instances: { limit: 10, in_use: 2 },
	cores: { limit: 16, in_use: 4 },
	ram: { limit: 32768, in_use: 4096 },
	gigabytes: { limit: 500, in_use: 100 },
};

function renderFlavors(props: Partial<{ adminMode: boolean; flavors: FlavorOption[]; selectedId: string | null; selectedName: string | null; quota: Omit<typeof quota, 'cores' | 'ram'> & { cores?: typeof quota.cores | null; ram?: typeof quota.ram | null }; bootVolumeSizeGb: number; refreshing: boolean; refreshError: string | null; backgroundRefreshing: boolean; backgroundRefreshError: string | null }> = {}) {
	const onSelect = vi.fn();
	const onRefresh = vi.fn().mockResolvedValue(true);
	const result = render(SelectFlavor, {
		adminMode: props.adminMode,
		flavors: props.flavors ?? [],
		selectedId: props.selectedId ?? null,
		selectedName: props.selectedName ?? null,
		onSelect,
		onRefresh,
		quota: props.quota ?? quota,
		bootVolumeSizeGb: props.bootVolumeSizeGb,
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
		media.matches = true;
	});

	afterEach(() => {
		vi.useRealTimers();
	});
	it.each([true, false])('shows 4 vCPU and 12 GiB without exposing native names or UUIDs in desktop=%s', async desktop => {
		media.matches = desktop;
		const flavor = { ...flavorWith('6142dc21-753b-4b23-8382-c52dce4c630e', 'cpu.4c_12g'), display_name: 'cpu.4c_12g', vcpus: 4, ram: 12288 };
		const { container, onSelect } = renderFlavors({ flavors: [flavor] });
		const choice = await screen.findByRole('button', { name: t('flavor.selectLabel', { name: '4 vCPU · 12 GiB RAM' }) });
		expect(container.innerHTML).not.toContain(flavor.name);
		expect(container.innerHTML).not.toContain(flavor.id);
		await fireEvent.input(screen.getByRole('searchbox'), { target: { value: '12 GiB' } });
		await fireEvent.click(choice);
		expect(onSelect).toHaveBeenCalledWith(flavor.id, flavor.name);
	});

	it.each([
		[1, 4096, 'cpu.1c_4g'],
		[2, 16384, 'c1.large'],
		[4, 65536, 'manual.high-ram'],
		[2, 16384, 'cpu.2c_16g'],
		[2, 8192, 'mem.2c_8g'],
		[2, 8192, 'r1.large'],
	] as const)('classifies %s vCPUs and %s MiB as memory regardless of legacy name %s', async (vcpus, ram, name) => {
		const memory = { ...flavorWith('memory', name), vcpus, ram };
		const { onSelect } = renderFlavors({ flavors: [memory] });
		expect(screen.getByRole('button', { name: t('flavor.category.cpu', { count: 0 }) })).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: t('flavor.category.memory', { count: 1 }) }));
		await fireEvent.click(screen.getByRole('button', { name: selectionName(memory) }));
		expect(onSelect).toHaveBeenCalledWith(memory.id, memory.name);
	});

	it.each([
		['cpu.2c_4g', null, 4096, 'cpu'],
		['c1.small', null, 4096, 'cpu'],
		['mem.2c_4g', null, 4096, 'cpu'],
		['m1.small', 'cpu.2c_4g', 4096, 'cpu'],
		['m1.small', 'mem.2c_4g', 4096, 'cpu'],
		['cpu.just-below', null, 8191, 'cpu'],
		['r1.misleading', null, 4096, 'general'],
		['manual.just-below', null, 8191, 'general'],
		['manual.small', null, 4096, 'general'],
	] as const)('keeps low-ratio %s (display %s, RAM %s MiB) in %s', async (name, display_name, ram, category) => {
		renderFlavors({ flavors: [{ ...flavorWith('low-ratio', name), display_name, ram }] });
		expect(screen.getByRole('button', { name: t('flavor.category.memory', { count: 0 }) })).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: t(`flavor.category.${category}`, { count: 1 }) }));
		expect(screen.getByRole('button', { name: selectionName({ ...flavorWith('low-ratio', name), display_name, ram }) })).toBeTruthy();
	});

	it.each([
		[0, 8192], [-1, 8192], [NaN, 8192], [Infinity, 8192],
		[2, 0], [2, -1], [2, NaN], [2, Infinity],
		[undefined, 8192], [2, undefined], ['2', 8192], [2, '8192'],
	])('does not infer memory from malformed hardware vCPUs=%s RAM=%s or a memory prefix', async (vcpus, ram) => {
		const malformed = { ...flavorWith('malformed', 'mem.unverified'), vcpus, ram } as FlavorOption;
		renderFlavors({ flavors: [malformed] });
		await fireEvent.click(screen.getByRole('button', { name: t('flavor.category.memory', { count: 0 }) }));
		expect(screen.queryByRole('button', { name: /플레이버 선택$/ })).toBeNull();
	});

	it('keeps named, PCI-attached and explicitly identified high-RAM GPUs exclusively in GPU', async () => {
		const flavors = [
			{ ...flavorWith('gpu-name', 'gpu.high-ram'), ram: 32768 },
			{ ...flavorWith('gpu-pci', 'cpu.with-gpu', { gpus: { graphics: 1 } }), ram: 32768 },
			{ ...flavorWith('gpu-flag', 'manual.with-gpu'), ram: 32768, is_gpu: true },
			{ ...flavorWith('gpu-count', 'manual.counted-accelerator'), ram: 32768, gpu_count: 1 },
			{ ...flavorWith('gpu-alias', 'manual.approved-accelerator'), ram: 32768, gpu_primary_aliases: [{ name: 'graphics', count: 1, resource_class: 'CUSTOM_PCI_RENDER', profile_name: 'render' }] },
		];
		renderFlavors({ flavors });
		await fireEvent.click(screen.getByRole('button', { name: t('flavor.category.memory', { count: 0 }) }));
		expect(screen.queryByRole('button', { name: /플레이버 선택$/ })).toBeNull();
		await fireEvent.click(screen.getByRole('button', { name: t('flavor.category.gpu', { count: 5 }) }));
		expect(screen.getAllByRole('button', { name: /플레이버 선택$/ })).toHaveLength(flavors.length);
	});

	it.each([true, false])('preserves memory counts, search, pagination and native selection while excluding blocked rows in desktop=%s', async desktop => {
		media.matches = desktop;
		const memory = Array.from({ length: 13 }, (_, index) => ({
			...flavorWith(`memory-${index}`, `cpu.batch-${String(index).padStart(2, '0')}`), ram: 8192,
		}));
		const projected = { ...memory[12], display_name: 'mem.2c_32g', ram: 32768 };
		memory[12] = projected;
		const blocked = [
			{ ...flavorWith('quota', 'mem.blocked-quota', { blockers: [{ code: 'ram_insufficient' }] }), ram: 32768 },
			{ ...flavorWith('host', 'cpu.blocked-host', { capacity: capacity('insufficient') }), ram: 32768 },
			{ ...flavorWith('unknown', 'manual.blocked-unknown', { capacity: capacity('unavailable') }), ram: 32768 },
			{ ...flavorWith('unchecked', 'r1.blocked-unchecked'), ram: 32768, eligibility: null },
		];
		const { onSelect } = renderFlavors({ flavors: [...memory, ...blocked, flavorWith('cpu', 'cpu.2c_4g'), gpuFlavor('gpu', 'render')], selectedId: projected.id });
		expect(screen.getByRole('button', { name: t('flavor.category.all', { count: 15 }) })).toBeTruthy();
		expect(screen.getByRole('button', { name: t('flavor.category.cpu', { count: 1 }) })).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: 'render' }));
		await fireEvent.click(screen.getByRole('button', { name: t('flavor.category.memory', { count: 13 }) }));
		expect(screen.getByRole('button', { name: t('flavor.gpuFilter.all') }).getAttribute('aria-pressed')).toBe('true');
		expect(screen.getAllByRole('button', { name: /플레이버 선택$/ })).toHaveLength(10);
		await fireEvent.click(screen.getByRole('button', { name: tc('pagination.next') }));
		expect(screen.getByText('2 / 2')).toBeTruthy();
		expect(screen.getAllByRole('button', { name: /플레이버 선택$/ })).toHaveLength(3);
		const choice = screen.getByRole('button', { name: selectionName(projected) });
		expect(choice.getAttribute('aria-pressed')).toBe('true');
		await fireEvent.click(choice);
		expect(onSelect).toHaveBeenCalledWith(projected.id, projected.name);
		for (const term of [projected.name, projected.display_name]) {
			await fireEvent.input(screen.getByRole('searchbox'), { target: { value: term } });
			expect(screen.getByText('1 / 1')).toBeTruthy();
			expect(screen.getAllByRole('button', { name: /플레이버 선택$/ })).toHaveLength(1);
			expect(screen.getByRole('button', { name: selectionName(projected) }).getAttribute('aria-pressed')).toBe('true');
		}
		await fireEvent.input(screen.getByRole('searchbox'), { target: { value: 'blocked' } });
		expect(screen.queryByRole('button', { name: /플레이버 선택$/ })).toBeNull();
		expect(screen.getByRole('button', { name: t('flavor.category.memory', { count: 13 }) }).getAttribute('aria-pressed')).toBe('true');
	});

	it.each([true, false])('displays server CPU labels without replacing native identity in desktop=%s', async desktop => {
		media.matches = desktop;
		const projected = { ...flavorWith('legacy-id', 'm1.small'), display_name: 'cpu.2c_1.5g', ram: 1536 };
		const gpu = flavorWith('gpu-id', 'gpu.render', { gpus: { graphics: 1 } });
		const unknown = { ...flavorWith('unknown-id', 'manual.accelerator'), display_name: null, extra_specs: { 'resources:CUSTOM_ACCELERATOR': '1' } };
		const { onSelect } = renderFlavors({ flavors: [projected, gpu, unknown] });
		const choice = await screen.findByRole('button', { name: selectionName(projected) });
		expect(screen.getByRole('button', { name: selectionName(gpu) })).toBeTruthy();
		expect(screen.getAllByRole('button', { name: /플레이버 선택$/ })).toHaveLength(3);
		for (const flavor of [projected, gpu, unknown]) {
			expect(screen.queryByTitle(flavor.name)).toBeNull();
			expect(screen.queryByText(flavor.id)).toBeNull();
		}
		await fireEvent.click(choice);
		expect(onSelect).toHaveBeenCalledWith('legacy-id', 'm1.small');
		expect(projected.name).toBe('m1.small');
		const search = screen.getByRole('searchbox');
		for (const term of ['cpu.2c_1.5g', 'm1.small']) {
			await fireEvent.input(search, { target: { value: term } });
			expect(screen.getByRole('button', { name: selectionName(projected) })).toBeTruthy();
			expect(screen.queryByRole('button', { name: selectionName(gpu) })).toBeNull();
		}
	});

	it.each([true, false])('keeps duplicate CPU labels independently selectable in desktop=%s', async desktop => {
		media.matches = desktop;
		const first = { ...flavorWith('cpu-a', 'm1.small'), display_name: 'cpu.2c_4g' };
		const second = { ...flavorWith('cpu-b', 'private-dedicated'), display_name: 'cpu.2c_4g', disk: 80, extra_specs: { 'hw:cpu_policy': 'dedicated' } };
		const { onSelect } = renderFlavors({ flavors: [first, second], selectedId: first.id });
		const choices = await screen.findAllByRole('button', { name: selectionName(first) });
		expect(choices).toHaveLength(2);
		for (const [index, flavor] of [first, second].entries()) {
			const choice = choices[index];
			expect(choice.getAttribute('aria-pressed')).toBe(String(flavor.id === first.id));
			await fireEvent.click(choice);
			expect(onSelect).toHaveBeenLastCalledWith(flavor.id, flavor.name);
			expect(screen.queryByText(flavor.name)).toBeNull();
			expect(screen.queryByText(flavor.id)).toBeNull();
		}
	});

	it('shows one compact flavor choice per resource and preserves selection across layouts', async () => {
		const { onSelect } = renderFlavors({
			flavors: [flavorWith('cpu-1', 'cpu.1c_1g'), flavorWith('gpu-1', 'gpu.1c_8g', { gpus: { RTX3090: 1 } })], selectedId: 'cpu-1',
		});
		expect(screen.getByText(t('flavor.quota.title'))).toBeTruthy();
		expect(screen.queryByRole('article')).toBeNull();
		media.matches = false;
		media.dispatchEvent(new Event('change'));
		await waitFor(() => expect(screen.getAllByRole('article')).toHaveLength(2));
		const cpu = screen.getByRole('heading', { name: '2 vCPU · 4 GiB RAM' }).closest('article')!;
		expect(within(cpu).getByText('2')).toBeTruthy();
		expect(within(cpu).getByText('4 GB')).toBeTruthy();
		const select = screen.getByRole('button', { name: t('flavor.selectLabel', { name: '2 vCPU · 4 GiB RAM' }) });
		expect(select.getAttribute('aria-pressed')).toBe('true');
		await fireEvent.click(select);
		expect(onSelect).toHaveBeenCalledWith('cpu-1', 'cpu.1c_1g');
		media.matches = true;
		media.dispatchEvent(new Event('change'));
		await waitFor(() => expect(screen.queryByRole('article')).toBeNull());
		expect(screen.getAllByRole('button', { name: t('flavor.selectLabel', { name: '2 vCPU · 4 GiB RAM' }) })).toHaveLength(1);
		expect(screen.getByRole('button', { name: t('flavor.selectLabel', { name: '2 vCPU · 4 GiB RAM' }) }).getAttribute('aria-pressed')).toBe('true');
	});

	it('shows the approved group count without treating its companion as another GPU', () => {
		const managed: FlavorOption = {
			...flavorWith('managed', 'gpu.renderx2_2c_4g'),
			extra_specs: { 'afterglow:managed_by': 'domain-compute-v1', 'afterglow:access_mode': 'gpu_quota', 'pci_passthrough:alias': 'graphics:2,sound:2' },
			gpu_primary_aliases: [{ name: 'graphics', count: 2, resource_class: 'CUSTOM_PCI_ABCD_0001', profile_name: 'render' }],
		};
		managed.eligibility!.remaining.gpus = { CUSTOM_PCI_ABCD_0001: 4 };
		managed.eligibility!.requirements.gpus = { CUSTOM_PCI_ABCD_0001: 2 };
		const unknown: FlavorOption = { ...managed, id: 'unknown', name: 'gpu.unknownx1_2c_4g', gpu_primary_aliases: null };
		const { container } = renderFlavors({ flavors: [managed, unknown] });
		expect(container.textContent).toContain('render × 2');
		expect(container.textContent).not.toContain('sound ×');
		expect(container.textContent).toContain(tp('unknown'));
		expect(container.textContent).not.toContain('CUSTOM_PCI_ABCD_0001');
	});

	it('separates existing and selected resource allocations', () => {
		const { container } = renderFlavors({ flavors: [flavorWith('cpu', 'cpu.2c_4g')], selectedId: 'cpu' });
		const tracks = [...container.querySelectorAll<HTMLElement>('.quota-track')];
		expect(tracks).toHaveLength(4);
		const values = ['2 → 3 / 10', '4 → 6 / 16', '4GB → 8GB / 32GB', '100GB → 120GB / 500GB'];
		tracks.forEach((track, index) => {
			expect(track.parentElement?.textContent?.replace(/\s+/g, ' ').trim()).toContain(values[index]);
		});
	});

	it('uses the configured root volume size instead of the flavor disk', () => {
		const { container } = renderFlavors({ flavors: [flavorWith('cpu', 'cpu.2c_4g')], selectedId: 'cpu', bootVolumeSizeGb: 80 });
		const disk = container.querySelectorAll<HTMLElement>('.quota-track')[3];
		expect(disk.parentElement?.textContent?.replace(/\s+/g, ' ').trim()).toContain('100GB → 180GB / 500GB');
	});

	it('does not allocate a new root disk when booting from an existing volume', () => {
		const { container } = renderFlavors({ flavors: [flavorWith('cpu', 'cpu.2c_4g')], selectedId: 'cpu', bootVolumeSizeGb: 0 });
		const disk = container.querySelectorAll<HTMLElement>('.quota-track')[3];
		expect(disk.parentElement?.textContent?.replace(/\s+/g, ' ').trim()).toContain('100GB / 500GB');
		expect(disk.parentElement?.textContent).not.toContain('→');
	});


	it('does not clamp the displayed over-limit quota values', () => {
		const overQuota = {
			instances: { limit: 1, in_use: 2 },
			cores: { limit: 1, in_use: 4 },
			ram: { limit: 1024, in_use: 4096 },
			gigabytes: { limit: 50, in_use: 100 },
		};
		const { container } = renderFlavors({ flavors: [flavorWith('cpu', 'cpu.2c_4g')], selectedId: 'cpu', quota: overQuota });
		const tracks = [...container.querySelectorAll<HTMLElement>('.quota-track')];
		const values = ['2 → 3 / 1', '4 → 6 / 1', '4GB → 8GB / 1GB', '100GB → 120GB / 50GB'];
		tracks.forEach((track, index) => {
			expect(track.parentElement?.textContent?.replace(/\s+/g, ' ').trim()).toContain(values[index]);
		});
	});


	it('offers only exact approved primary GPU types, excluding companions and blocked models', async () => {
		const exact = gpuFlavor('exact', 'RTX3090');
		const prefixed = gpuFlavor('prefixed', 'RTX3090Ti');
		const blocked = gpuFlavor('blocked-model', 'A100');
		blocked.eligibility!.blockers = [{ code: 'gpu_insufficient', required: 1, remaining: 0 }];
		const unknown = { ...gpuFlavor('name-is-not-a-type', 'unapproved'), name: 'gpu.A6000x1_2c_4g', gpu_primary_aliases: null };
		renderFlavors({ flavors: [exact, prefixed, blocked, unknown, flavorWith('cpu', 'cpu.small')] });
		const filters = screen.getByRole('group', { name: t('flavor.gpuFilter.title') });
		expect(within(filters).getAllByRole('button').map(button => button.textContent)).toEqual([t('flavor.gpuFilter.all'), 'RTX3090', 'RTX3090Ti']);
		await fireEvent.click(within(filters).getByRole('button', { name: 'RTX3090' }));
		expect(within(filters).getByRole('button', { name: 'RTX3090' }).getAttribute('aria-pressed')).toBe('true');
		expect(screen.getByRole('button', { name: selectionName(exact) })).toBeTruthy();
		expect(screen.queryByRole('button', { name: selectionName(prefixed) })).toBeNull();
		expect(screen.queryByRole('button', { name: selectionName(unknown) })).toBeNull();
		await fireEvent.click(screen.getByRole('button', { name: t('flavor.category.cpu', { count: 1 }) }));
		expect(within(filters).getByRole('button', { name: t('flavor.gpuFilter.all') }).getAttribute('aria-pressed')).toBe('true');
		expect(screen.getByRole('button', { name: selectionName(flavorWith('cpu', 'cpu.small')) })).toBeTruthy();
		await fireEvent.click(within(filters).getByRole('button', { name: 'RTX3090Ti' }));
		expect(screen.getByRole('button', { name: selectionName(prefixed) })).toBeTruthy();
		expect(screen.getByRole('button', { name: t('flavor.category.gpu', { count: 3 }) }).getAttribute('aria-pressed')).toBe('true');
	});

	it('composes GPU type, category, search and pagination while preserving filters and selection on refresh and clamping shrink', async () => {
		const matching = Array.from({ length: 13 }, (_, index) => gpuFlavor(`batch-${String(index).padStart(2, '0')}`, 'render'));
		const other = gpuFlavor('batch-other', 'render-pro');
		const blocked = gpuFlavor('batch-blocked', 'render');
		blocked.eligibility!.capacity = capacity('insufficient');
		const { rerender, onSelect } = renderFlavors({ flavors: [...matching, other, blocked, flavorWith('cpu', 'cpu.batch')], selectedId: matching[0].id });
		await fireEvent.click(screen.getByRole('button', { name: t('flavor.category.gpu', { count: 14 }) }));
		await fireEvent.click(within(screen.getByRole('group', { name: t('flavor.gpuFilter.title') })).getByRole('button', { name: 'render' }));
		await fireEvent.click(screen.getByRole('button', { name: tc('pagination.next') }));
		expect(screen.getByText('2 / 2')).toBeTruthy();
		expect(screen.getAllByRole('button', { name: /플레이버 선택$/ })).toHaveLength(3);
		await fireEvent.input(screen.getByRole('searchbox'), { target: { value: 'batch-' } });
		expect(screen.getByText('1 / 2')).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: tc('pagination.next') }));
		await rerender({ flavors: [...matching, other, blocked], backgroundRefreshing: true });
		expect(screen.getByText('2 / 2')).toBeTruthy();
		expect(screen.getByRole('searchbox').getAttribute('value') ?? (screen.getByRole('searchbox') as HTMLInputElement).value).toBe('batch-');
		expect(screen.queryByRole('button', { name: selectionName(other) })).toBeNull();
		await rerender({ flavors: matching.slice(0, 3), backgroundRefreshing: false });
		expect(screen.getByText('1 / 1')).toBeTruthy();
		expect(screen.getAllByRole('button', { name: /플레이버 선택$/ })).toHaveLength(3);
		expect(screen.getAllByRole('button', { name: selectionName(matching[0]) })[0].getAttribute('aria-pressed')).toBe('true');
		expect(screen.getByRole('button', { name: 'render' }).getAttribute('aria-pressed')).toBe('true');
		expect(onSelect).not.toHaveBeenCalled();
		await fireEvent.input(screen.getByRole('searchbox'), { target: { value: 'absent' } });
		await fireEvent.click(screen.getByRole('button', { name: t('flavor.filter.reset') }));
		expect((screen.getByRole('searchbox') as HTMLInputElement).value).toBe('');
		expect(screen.getByRole('button', { name: t('flavor.category.all', { count: 3 }) }).getAttribute('aria-pressed')).toBe('true');
		expect(screen.getByRole('button', { name: t('flavor.gpuFilter.all') }).getAttribute('aria-pressed')).toBe('true');
	});

	it('keeps the applied GPU type visible when refresh removes its last creatable flavor and allows clearing it', async () => {
		const render = gpuFlavor('render', 'render');
		const other = gpuFlavor('other', 'render-pro');
		const { rerender, onSelect } = renderFlavors({ flavors: [render, other], selectedId: render.id });
		await fireEvent.click(screen.getByRole('button', { name: 'render' }));
		await rerender({ flavors: [other], backgroundRefreshing: true });
		const filters = screen.getByRole('group', { name: t('flavor.gpuFilter.title') });
		expect(within(filters).getByRole('button', { name: 'render' }).getAttribute('aria-pressed')).toBe('true');
		expect(within(filters).getByRole('button', { name: t('flavor.gpuFilter.all') }).getAttribute('aria-pressed')).toBe('false');
		expect(screen.getByText(t('flavor.filter.reason'))).toBeTruthy();
		expect(screen.queryByRole('button', { name: /플레이버 선택$/ })).toBeNull();
		await fireEvent.click(within(filters).getByRole('button', { name: t('flavor.gpuFilter.all') }));
		expect(screen.getByRole('button', { name: selectionName(other) })).toBeTruthy();
		expect(within(filters).queryByRole('button', { name: 'render' })).toBeNull();
		expect(onSelect).not.toHaveBeenCalled();
	});

	it.each(['empty', 'quota', 'host'] as const)('uses a neutral available-empty state for a successfully observed %s catalog', state => {
		const flavors = state === 'empty' ? [] : [flavorWith('blocked', 'cpu.hidden', state === 'quota' ? { blockers: [{ code: 'cores_insufficient', required: 2, remaining: 0 }] } : { capacity: capacity('insufficient') })];
		renderFlavors({ flavors });
		expect(screen.getByText(t('flavor.available.emptyTitle'))).toBeTruthy();
		expect(screen.getByText(t('flavor.available.emptyBody'))).toBeTruthy();
		expect(screen.queryByRole('button', { name: /플레이버 선택$/ })).toBeNull();
		expect(screen.queryByText(t('flavor.catalog.title'))).toBeNull();
	});

	it('does not mask a failed lookup with a neutral empty-catalog notice', () => {
		renderFlavors({ refreshError: 'native lookup failed (503)' });
		expect(screen.getByRole('alert').textContent).toContain('native lookup failed (503)');
		expect(screen.queryByText(t('flavor.available.emptyTitle'))).toBeNull();
	});

	it('shows actual usage and selected deltas for every unlimited quota without a percentage meter', async () => {
		const unlimited = {
			instances: { limit: -1, in_use: 7 }, cores: { limit: -1, in_use: 19 },
			ram: { limit: -1, in_use: 1536 }, gigabytes: { limit: -1, in_use: 123 },
		};
		const selected = { ...flavorWith('exact', 'cpu.exact'), ram: 1536 };
		const { container, rerender } = renderFlavors({ flavors: [selected], quota: unlimited, bootVolumeSizeGb: 80 });
		expect(screen.getByRole('group', { name: 'RAM' }).textContent).toContain('1.5GB');
		expect(screen.getByRole('group', { name: 'RAM' }).textContent).not.toContain('→');
		await rerender({ selectedId: selected.id });
		for (const [label, values] of [[t('flavor.quota.vm'), '7 → 8 / ∞'], ['vCPU', '19 → 21 / ∞'], ['RAM', '1.5GB → 3GB / ∞'], [t('flavor.quota.disk'), '123GB → 203GB / ∞']]) {
			expect(screen.getByRole('group', { name: label }).textContent?.replace(/\s+/g, ' ')).toContain(values);
		}
		expect(container.querySelectorAll('.quota-track')).toHaveLength(0);
	});

	it.each([
		['CPU missing', undefined, quota.ram, 'vCPU', 'RAM'],
		['RAM missing', quota.cores, undefined, 'RAM', 'vCPU'],
		['CPU unavailable', null, quota.ram, 'vCPU', 'RAM'],
		['RAM unavailable', quota.cores, null, 'RAM', 'vCPU'],
	] as const)('renders %s independently as unknown, without hiding the other native quota', (_label, cores, ram, missing, present) => {
		const { container } = renderFlavors({ flavors: [flavorWith('selected', 'cpu.selected')], selectedId: 'selected', quota: { ...quota, cores, ram } });
		const unknown = screen.getByRole('group', { name: missing });
		expect(within(unknown).getByText(tp('unknown'))).toBeTruthy();
		expect(unknown.textContent).not.toMatch(/∞|→|\/|0GB/);
		expect(screen.getByRole('group', { name: present }).textContent).toContain('→');
		expect(container.querySelectorAll('.quota-track')).toHaveLength(3);
	});

	it('renders both missing native compute observations as unknown even with retained domain eligibility', () => {
		const selected = flavorWith('domain', 'cpu.domain');
		selected.eligibility!.quota_scope = 'domain';
		const { container } = renderFlavors({ flavors: [selected], selectedId: selected.id, quota: { ...quota, cores: null, ram: null } });
		for (const label of ['vCPU', 'RAM']) {
			const cell = screen.getByRole('group', { name: label });
			expect(within(cell).getByText(tp('unknown'))).toBeTruthy();
			expect(cell.textContent).not.toMatch(/∞|→|0GB/);
		}
		expect(container.querySelectorAll('.quota-track')).toHaveLength(2);
	});

	it('keeps fractional native RAM usage, post-create usage and finite limit exact', () => {
		const selected = { ...flavorWith('fractional', 'cpu.fractional'), ram: 1536 };
		renderFlavors({ flavors: [selected], selectedId: selected.id, quota: { ...quota, ram: { limit: 5632, in_use: 1280 } } });
		expect(screen.getByRole('group', { name: 'RAM' }).textContent?.replace(/\s+/g, ' ')).toContain('1.25GB → 2.75GB / 5.5GB');
	});

	it.each([true, false])('hides quota, host, unavailable and missing eligibility from inventory in desktop=%s', async desktop => {
		media.matches = desktop;
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

		expect(screen.getByRole('button', { name: selectionName(flavorWith('ok', 'cpu.2c_4g')) })).toBeTruthy();
		expect(screen.getByRole('button', { name: t('flavor.category.all', { count: 1 }) })).toBeTruthy();
		expect(screen.getByRole('button', { name: t('flavor.category.gpu', { count: 0 }) })).toBeTruthy();
		expect(screen.queryByRole('group', { name: t('flavor.gpuFilter.title') })).toBeNull();
		for (const name of ['gpu.quota', 'gpu.host', 'cpu.16c_64g', 'gpu.unknown', 'gpu.missing', 'legacy.no_eligibility']) {
			expect(screen.queryByRole('button', { name: `${name} 플레이버 선택` })).toBeNull();
		}
		await fireEvent.input(screen.getByRole('searchbox'), { target: { value: 'quota' } });
		expect(screen.queryByRole('button', { name: /플레이버 선택$/ })).toBeNull();
		expect(screen.getByText(t('flavor.filter.reason'))).toBeTruthy();
		expect(onSelect).not.toHaveBeenCalled();
	});

	it('keeps one actionable policy summary rather than exposing an unverified inventory', () => {
		const unavailable = capacity('unavailable', { reason: 'default_compute_zone_unavailable' });
		const { onSelect } = renderFlavors({ flavors: [
			flavorWith('cpu', 'cpu.2c_4g', { capacity: unavailable, blockers: [{ code: 'host_capacity_unavailable' }] }),
			flavorWith('gpu', 'gpu.4c_8g', { capacity: unavailable, blockers: [{ code: 'host_capacity_unavailable' }] }),
		] });
		expect(screen.getByText(t('flavor.availability.selectable', { count: 0 }))).toBeTruthy();
		expect(screen.getByText(t('flavor.policy.title'))).toBeTruthy();
		expect(screen.getAllByText(t('flavor.policy.help'))).toHaveLength(1);
		expect(screen.queryByRole('button', { name: /플레이버 선택$/ })).toBeNull();
		expect(screen.queryByText(t('flavor.available.emptyTitle'))).toBeNull();
		expect(onSelect).not.toHaveBeenCalled();
	});

	it('shows shared AZ remediation without per-flavor shortage details', () => {
		const unavailable = capacity('unavailable', { reason: 'default_compute_zone_unavailable' });
		const { onSelect } = renderFlavors({ flavors: [
			flavorWith('cpu', 'cpu.quota-and-zone', { capacity: unavailable, blockers: [
				{ code: 'cores_insufficient', required: 2, remaining: 0 }, { code: 'host_capacity_unavailable' },
			] }),
			flavorWith('memory', 'mem.quota-and-zone', { capacity: unavailable, blockers: [
				{ code: 'ram_insufficient', required: 4096, remaining: 0 }, { code: 'host_capacity_unavailable' },
			] }),
		] });
		expect(screen.getAllByText(t('flavor.policy.title'))).toHaveLength(1);
		expect(screen.getAllByText(t('flavor.policy.help'))).toHaveLength(1);
		for (const name of ['cpu.quota-and-zone', 'mem.quota-and-zone']) {
			expect(screen.queryByRole('button', { name: `${name} 플레이버 선택` })).toBeNull();
		}
		expect(screen.queryByText(/필요.*잔여|부족/)).toBeNull();
		expect(onSelect).not.toHaveBeenCalled();
	});

	it('preserves exact RAM and never invents bandwidth from the CPU count', async () => {
		const flavor = { ...flavorWith('exact', 'cpu.2c_1.5g'), ram: 1536 };
		const { onSelect } = renderFlavors({ flavors: [flavor] });
		const choice = screen.getByRole('button', { name: selectionName(flavor) });
		expect(choice.textContent).toContain('1.5 GB');
		expect(choice.textContent).not.toMatch(/\d Gbps/);
		expect(choice.hasAttribute('disabled')).toBe(false);
		media.matches = false; media.dispatchEvent(new Event('change'));
		await waitFor(() => expect(screen.getAllByRole('article')).toHaveLength(1));
		const card = screen.getByRole('heading', { name: consumerFlavorLabel(flavor) }).closest('article')!;
		expect(within(card).getByText('1.5 GB')).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: selectionName(flavor) }));
		expect(onSelect).toHaveBeenCalledWith('exact', 'cpu.2c_1.5g');
	});

	it('shows Nova outbound peak in its native KiB/s unit', () => {
		const flavor = { ...flavorWith('shaped', 'cpu.2c_4g'), extra_specs: { 'quota:vif_outbound_peak': '65536' } };
		renderFlavors({ flavors: [flavor] });
		const choice = screen.getByRole('button', { name: selectionName(flavor) });
		expect(choice.textContent).toContain('65536 KiB/s');
		expect(choice.textContent).not.toContain('65536 Gbps');
	});

	it('locks selection during a manual refresh and after its failure', async () => {
		const flavors = [flavorWith('ok', 'cpu.2c_4g')];
		const pending = renderFlavors({ flavors, refreshing: true });
		const button = screen.getByRole('button', { name: selectionName(flavors[0]) });
		expect(button.hasAttribute('disabled')).toBe(true);
		await fireEvent.click(button);
		expect(pending.onSelect).not.toHaveBeenCalled();
		pending.unmount();

		const failed = renderFlavors({ flavors, refreshError: '데이터 로드 실패 (503)' });
		expect(screen.getByRole('alert').textContent).toContain('503');
		expect(screen.getByRole('button', { name: selectionName(flavors[0]) }).hasAttribute('disabled')).toBe(true);
		await fireEvent.click(screen.getByRole('button', { name: '다시 확인' }));
		expect(failed.onRefresh).toHaveBeenCalledWith('manual');
	});

	it('keeps selection usable during and after a failed periodic refresh', async () => {
		const flavors = [flavorWith('ok', 'cpu.2c_4g')];
		const pending = renderFlavors({ flavors, backgroundRefreshing: true });
		const button = screen.getByRole('button', { name: selectionName(flavors[0]) });
		expect(button.hasAttribute('disabled')).toBe(false);
		await fireEvent.click(button);
		expect(pending.onSelect).toHaveBeenCalledWith('ok', 'cpu.2c_4g');
		pending.unmount();

		const failed = renderFlavors({ flavors, backgroundRefreshError: '데이터 로드 실패 (503)' });
		expect(screen.getByText('최근 자동 확인 실패 · 생성 직전에 다시 확인합니다')).toBeTruthy();
		expect(screen.queryByRole('alert')).toBeNull();
		const usableButton = screen.getByRole('button', { name: selectionName(flavors[0]) });
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
		expect(screen.queryByRole('button', { name: 'cpu.16c_128g 플레이버 선택' })).toBeNull();
		expect(onSelect).not.toHaveBeenCalled();
	});

	it.each(['quota', 'host', 'missing'] as const)('keeps a selected flavor recognizable after becoming %s without choosing a replacement', async reason => {
		const original = flavorWith('selected', 'cpu.selected');
		const { rerender, onSelect } = renderFlavors({ flavors: [original, flavorWith('other', 'cpu.other')], selectedId: original.id });
		const blocked = reason === 'quota'
			? flavorWith(original.id, original.name, { blockers: [{ code: 'cores_insufficient', required: 2, remaining: 0 }] })
			: flavorWith(original.id, original.name, { capacity: capacity('insufficient') });
		await rerender({ flavors: reason === 'missing' ? [flavorWith('other', 'cpu.other')] : [blocked, flavorWith('other', 'cpu.other')], selectedName: original.name });
		expect(screen.getByText(t('flavor.selected.unavailableBody', { name: reason === 'missing' ? t('flavor.selected.fallbackName') : consumerFlavorLabel(original) }))).toBeTruthy();
		expect(screen.getAllByRole('button', { name: selectionName(original) })).toHaveLength(1);
		expect(screen.getByRole('button', { name: selectionName(original) }).getAttribute('aria-pressed')).toBe('false');
		expect(screen.queryByText(/필요.*잔여|여유 없음|CPU.*부족/)).toBeNull();
		expect(onSelect).not.toHaveBeenCalled();
	});

	it('hides host limits and scheduler diagnostics from consumer choices and selection without changing admission', async () => {
		const { container, onSelect } = renderFlavors({
			flavors: [flavorWith('ded', 'cpu.dedicated', {
				capacity: capacity('available', { cpu_resource_class: 'PCPU', remaining_vcpus: 6, remaining_ram_mb: 24576, numa_unverified: true }),
			})],
			selectedId: 'ded',
		});

		// Includes the selected panel and the currently mounted responsive list variant.
		expect(container.textContent).not.toMatch(/VM당 최대|PCPU 6|RAM 24 GB|호스트 2대|NUMA|근접성|Nova|No valid host/);
		expect(screen.getByText(t('flavor.quota.title'))).toBeTruthy();
		expect(screen.queryByText('현재 대상 프로젝트 잔여 쿼터')).toBeNull();
		expect(screen.getByText('생성 가능 (1)')).toBeTruthy();
		const button = screen.getByRole('button', { name: selectionName(flavorWith('ded', 'cpu.dedicated')) });
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
		const button = screen.getByRole('button', { name: selectionName(flavorWith('numa', 'gpu.3090ti_8c_64g')) });
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

it.each(['domain', 'paused', 'unavailable'] as const)('shows native CPU and RAM quota independently of %s pool eligibility', scope => {
	const flavor = flavorWith('pool', 'cpu.pool', { blockers: scope === 'domain' ? [] : [{ code: scope === 'paused' ? 'domain_pool_paused' : 'domain_pool_unavailable' }] });
	flavor.eligibility!.quota_scope = scope === 'domain' ? 'domain' : 'project';
	const { container } = renderFlavors({ flavors: [flavor], selectedId: flavor.id });
	expect(screen.getByText(t('flavor.quota.title'))).toBeTruthy();
	expect(screen.queryByText(tp('projectAncillary'))).toBeNull();
	expect(screen.getByRole('group', { name: 'vCPU' }).textContent?.replace(/\s+/g, ' ')).toContain('4 → 6 / 16');
	expect(screen.getByRole('group', { name: 'RAM' }).textContent?.replace(/\s+/g, ' ')).toContain('4GB → 8GB / 32GB');
	expect(container.querySelectorAll('.quota-track')).toHaveLength(4);
});
