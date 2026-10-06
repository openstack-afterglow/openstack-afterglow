import { fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import GpuDefaultQuotaSection from '../GpuDefaultQuotaSection.svelte';
import GpuQuotaTable from '../GpuQuotaTable.svelte';

const rows = [
	{ gpu_type: 'a100', limit: 2, in_use: 1, available: 1 },
	{ gpu_type: 'h100', limit: 4, in_use: 1, available: 3 },
];

function rowFor(alias: string) {
	return within(screen.getByRole('row', { name: new RegExp(alias) }));
}

describe('GPU quota request activity', () => {
	it('tracks concurrent default writes independently until each callback settles', async () => {
		const first = Promise.withResolvers<void>();
		const second = Promise.withResolvers<void>();
		const onChange = vi.fn().mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
		render(GpuDefaultQuotaSection, {
			defaults: { a100: 2, h100: 4 }, allGpuTypes: ['a100', 'h100'],
			loading: false, error: '', success: '', onChange,
		});
		const inputs = screen.getAllByRole('spinbutton') as HTMLInputElement[];
		expect(screen.queryByRole('status')).toBeNull();
		expect(inputs.every((input) => !input.disabled)).toBe(true);
		await fireEvent.change(inputs[0], { target: { value: '3' } });
		expect(inputs[0].disabled).toBe(true);
		expect(inputs[1].disabled).toBe(false);
		expect(screen.getByRole('status').textContent?.trim()).toBeTruthy();
		await fireEvent.change(inputs[1], { target: { value: '5' } });
		expect(onChange.mock.calls).toEqual([['a100', 3], ['h100', 5]]);
		expect(inputs[0].disabled).toBe(true);
		expect(inputs[1].disabled).toBe(true);
		const statuses = screen.getAllByRole('status');
		expect(statuses).toHaveLength(2);
		for (const status of statuses) expect(status.textContent?.trim()).toBeTruthy();

		first.resolve();
		await waitFor(() => expect(inputs[0].disabled).toBe(false));
		expect(inputs[1].disabled).toBe(true);
		expect(screen.getAllByRole('status')).toHaveLength(1);
		second.resolve();
		await waitFor(() => expect(screen.queryByRole('status')).toBeNull());
		expect(inputs[1].disabled).toBe(false);
	});

	it('attributes a project write to its alias and leaves other aliases usable', async () => {
		const request = Promise.withResolvers<void>();
		const onSetLimit = vi.fn().mockReturnValue(request.promise);
		render(GpuQuotaTable, {
			rows, defaults: {}, loading: false, error: '', hasAnyAlias: true,
			onSetLimit, onClear: vi.fn(),
		});
		await fireEvent.change(rowFor('a100').getByRole('spinbutton'), { target: { value: '3' } });
		expect(onSetLimit).toHaveBeenCalledWith('a100', 3);
		expect(rowFor('a100').getByRole('status').textContent?.trim()).toBeTruthy();
		expect((rowFor('a100').getByRole('spinbutton') as HTMLInputElement).disabled).toBe(true);
		expect(rowFor('h100').queryByRole('status')).toBeNull();
		expect((rowFor('h100').getByRole('spinbutton') as HTMLInputElement).disabled).toBe(false);
		request.resolve();
		await waitFor(() => expect(screen.queryByRole('status')).toBeNull());
	});

	it('keeps project reset activity visible until the clear request settles', async () => {
		const request = Promise.withResolvers<void>();
		const onClear = vi.fn().mockReturnValue(request.promise);
		render(GpuQuotaTable, {
			rows, defaults: {}, loading: false, error: '', hasAnyAlias: true,
			onSetLimit: vi.fn(), onClear,
		});
		await fireEvent.click(rowFor('h100').getByRole('button', { name: '초기화' }));
		expect(onClear).toHaveBeenCalledWith('h100');
		expect(rowFor('h100').getByRole('status').textContent?.trim()).toBeTruthy();
		expect((rowFor('h100').getByRole('button', { name: '초기화' }) as HTMLButtonElement).disabled).toBe(true);
		expect(rowFor('a100').queryByRole('status')).toBeNull();
		request.resolve();
		await waitFor(() => expect(screen.queryByRole('status')).toBeNull());
		expect((rowFor('h100').getByRole('button', { name: '초기화' }) as HTMLButtonElement).disabled).toBe(false);
	});
});
