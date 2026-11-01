import { fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { afterAll, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Flavor } from '$lib/types/flavor';
import { t as poolText } from '$lib/i18n/ns/compute-pools';

const media = vi.hoisted(() => {
	const events = new EventTarget();
	const query = {
		matches: true,
		media: '(min-width: 1024px)',
		onchange: null,
		addEventListener: events.addEventListener.bind(events),
		removeEventListener: events.removeEventListener.bind(events),
		dispatchEvent: events.dispatchEvent.bind(events),
		addListener: () => undefined,
		removeListener: () => undefined,
	};
	vi.stubGlobal('matchMedia', () => query);
	return query;
});

beforeEach(() => { media.matches = true; });
afterAll(() => { vi.unstubAllGlobals(); });

import AdminFlavorsTable from '../AdminFlavorsTable.svelte';

function flavor(overrides: Partial<Flavor>): Flavor {
	return {
		id: 'flavor-id',
		name: 'flavor-name',
		vcpus: 8,
		ram: 16384,
		disk: 0,
		is_public: false,
		description: null,
		extra_specs: {},
		is_gpu: true,
		gpu_count: 1,
		...overrides,
	};
}

function rowFor(name: string): HTMLElement {
	const row = screen.getByText(name).closest('tr');
	expect(row).not.toBeNull();
	return row as HTMLElement;
}

describe('AdminFlavorsTable native flavor management', () => {
	it.each([true, false])('renders duplicate CPU labels with native disambiguation and exact management in desktop=%s', async desktop => {
		media.matches = desktop;
		const onManage = vi.fn();
		const first = flavor({ id: 'native-a', name: 'm1.small', display_name: 'cpu.2c_4g', cpu_automation_managed: true, is_gpu: false, gpu_count: 0, extra_specs: {} });
		const second = flavor({ id: 'native-b', name: 'dedicated-small', display_name: 'cpu.2c_4g', is_gpu: false, gpu_count: 0, disk: 40 });
		render(AdminFlavorsTable, { flavors: [first, second], totalUnfiltered: 2, pageSize: 20, refreshing: false, onManage, onDelete: vi.fn() });
		await waitFor(() => expect(screen.getAllByText('cpu.2c_4g')).toHaveLength(2));
		for (const item of [first, second]) {
			const id = screen.getAllByText(item.id)[0];
			const container = id.closest(desktop ? 'tr' : 'article')! as HTMLElement;
			expect(container.textContent).toContain(item.name);
			await fireEvent.click(within(container).getByRole('button', { name: '관리' }));
			expect(onManage).toHaveBeenLastCalledWith(item);
			expect((within(container).getByRole('button', { name: '삭제' }) as HTMLButtonElement).disabled).toBe(item.id === 'native-a');
		}
	});
	it('retains explicit public/private identity and manages the exact flavor regardless of obsolete specs', async () => {
		const onManage = vi.fn();
		render(AdminFlavorsTable, {
			flavors: [
				flavor({
					id: 'quota-gpu',
					name: 'quota.gpu',
					extra_specs: { 'afterglow:access_mode': 'gpu_quota' },
				}),
				flavor({
					id: 'manual-gpu',
					name: 'manual.gpu',
					extra_specs: { 'afterglow:access_mode': 'manual' },
				}),
				flavor({
					id: 'public-gpu',
					name: 'public.gpu',
					is_public: true,
					extra_specs: { 'afterglow:access_mode': 'gpu_quota' },
				}),
				flavor({
					id: 'private-cpu',
					name: 'private.cpu',
					is_gpu: false,
					gpu_count: 0,
					extra_specs: { 'afterglow:access_mode': 'manual' },
				}),
			],
			totalUnfiltered: 4,
			pageSize: 20,
			refreshing: false,
			onManage,
			onDelete: vi.fn().mockResolvedValue(undefined),
		});

		const quotaRow = within(rowFor('quota.gpu'));
		expect(quotaRow.getByText('Private')).toBeTruthy();
		await fireEvent.click(quotaRow.getByRole('button', { name: '관리' }));
		expect(onManage.mock.calls[0][0].id).toBe('quota-gpu');
		expect(within(rowFor('public.gpu')).getByText('Public')).toBeTruthy();
		expect(within(rowFor('private.cpu')).getByText('Private')).toBeTruthy();
	});
});


describe('AdminFlavorsTable approved GPU projection', () => {
	it('renders approved counts and explicit unknown without preventing management', async () => {
		const onManage = vi.fn();
		render(AdminFlavorsTable, {
			flavors: [
				flavor({
					id: 'approved', name: 'approved.group', gpu_count: 1,
					extra_specs: { 'afterglow:managed_by': 'domain-compute-v1', 'pci_passthrough:alias': 'graphics:1,sound:1' },
					gpu_primary_aliases: [{ name: 'graphics', count: 1, resource_class: 'CUSTOM_GRAPHICS', profile_name: 'render-group' }],
				}),
				flavor({ id: 'unknown', name: 'unknown.group', is_gpu: null, gpu_count: null, gpu_primary_aliases: null,
					extra_specs: { 'afterglow:managed_by': 'domain-compute-v1', 'pci_passthrough:alias': 'graphics:1,sound:1' } }),
				flavor({ id: 'cpu', name: 'cpu.only', is_gpu: false, gpu_count: 0 }),
				flavor({ id: 'manual', name: 'manual.gpu', gpu_count: 2 }),
			],
			totalUnfiltered: 4, pageSize: 20, refreshing: false, onManage,
			onDelete: vi.fn().mockResolvedValue(undefined),
		});
		expect(within(rowFor('approved.group')).getByText('GPU ×1')).toBeTruthy();
		expect(within(rowFor('manual.gpu')).getByText('GPU ×2')).toBeTruthy();
		const unknown = within(rowFor('unknown.group'));
		expect(unknown.getByText(`GPU · ${poolText('unknown')}`)).toBeTruthy();
		expect(unknown.queryByText('GPU ×0')).toBeNull();
		expect(within(rowFor('cpu.only')).getByText('-')).toBeTruthy();
		await fireEvent.click(unknown.getByRole('button', { name: '관리' }));
		expect(onManage.mock.calls[0][0].id).toBe('unknown');
		media.matches = false;
		media.dispatchEvent(new Event('change'));
		await waitFor(() => expect(screen.queryByRole('table')).toBeNull());
		const approvedCard = screen.getByText('approved.group').closest('article') as HTMLElement;
		const unknownCard = screen.getByText('unknown.group').closest('article') as HTMLElement;
		expect(within(approvedCard).getByText('GPU ×1')).toBeTruthy();
		expect(within(unknownCard).getByText(`GPU · ${poolText('unknown')}`)).toBeTruthy();
		await fireEvent.click(within(unknownCard).getByRole('button', { name: '관리' }));
		expect(onManage.mock.calls.at(-1)?.[0].id).toBe('unknown');
	});
});
