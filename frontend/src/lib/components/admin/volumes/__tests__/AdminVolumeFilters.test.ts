import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { writable } from 'svelte/store';

vi.mock('$lib/stores/projectNames', () => ({ projectNames: writable(new Map<string, string>()) }));

import AdminVolumeFilters from '../AdminVolumeFilters.svelte';

afterEach(() => { cleanup(); vi.useRealTimers(); });

describe('AdminVolumeFilters status options', () => {
	it('renders only the positive-count options supplied by the status summary', () => {
		render(AdminVolumeFilters, {
			props: {
				statusFilter: '',
				nameSearch: '',
				statusOptions: ['available', 'in-use'],
				onChange: vi.fn(),
			},
		});

		expect(screen.getByRole('option', { name: '모든 상태' })).toBeTruthy();
		const values = screen.getAllByRole('option').map(option => (option as HTMLOptionElement).value);
		expect(values).toContain('available');
		expect(values).toContain('in-use');
		expect(values).not.toContain('error');
	});

	it('invalidates immediately, debounces text/type/capacity together and cancels pending work on unmount', async () => {
		vi.useFakeTimers();
		const onChange = vi.fn();
		const onInvalidate = vi.fn();
		const view = render(AdminVolumeFilters, { statusFilter: '', nameSearch: '', volumeType: '', minSize: '', maxSize: '', statusOptions: ['available'], onChange, onInvalidate });
		for (const [label, value] of [['이름 또는 ID', 'vol-id'], ['볼륨 유형', 'fast'], ['최소 용량 (GiB)', '10'], ['최대 용량 (GiB)', '100']]) {
			await fireEvent.input(screen.getByLabelText(label), { target: { value } });
		}
		expect(onInvalidate).toHaveBeenCalledTimes(4);
		expect(onChange).not.toHaveBeenCalled();
		await vi.advanceTimersByTimeAsync(300);
		expect(onChange).toHaveBeenCalledOnce();
		await fireEvent.input(screen.getByLabelText('이름 또는 ID'), { target: { value: 'pending' } });
		view.unmount();
		await vi.advanceTimersByTimeAsync(300);
		expect(onChange).toHaveBeenCalledOnce();
	});

	it('applies status immediately and cancels a pending search timer', async () => {
		vi.useFakeTimers();
		const onChange = vi.fn();
		const onInvalidate = vi.fn();
		render(AdminVolumeFilters, { statusFilter: '', nameSearch: '', statusOptions: ['available'], onChange, onInvalidate });
		await fireEvent.input(screen.getByLabelText('이름 또는 ID'), { target: { value: 'needle' } });
		await fireEvent.change(screen.getByLabelText('상태'), { target: { value: 'available' } });
		expect(onInvalidate).toHaveBeenCalledTimes(2);
		expect(onChange).toHaveBeenCalledOnce();
		await vi.advanceTimersByTimeAsync(300);
		expect(onChange).toHaveBeenCalledOnce();
	});

	it('defaults to newest first and immediately applies each sort while cancelling pending search work', async () => {
		vi.useFakeTimers();
		const onChange = vi.fn();
		const onInvalidate = vi.fn();
		const view = render(AdminVolumeFilters, { statusFilter: '', nameSearch: '', statusOptions: ['available'], onChange, onInvalidate });
		const sort = view.container.querySelector<HTMLSelectElement>('#admin-volume-sort')!;
		expect(sort.value).toBe('created_desc');
		expect(Array.from(sort.options, option => option.value)).toEqual(['created_desc', 'created_asc', 'name_asc', 'name_desc']);
		await fireEvent.input(screen.getByLabelText('이름 또는 ID'), { target: { value: 'pending' } });
		for (const value of ['created_asc', 'name_asc', 'name_desc', 'created_desc']) {
			await fireEvent.change(sort, { target: { value } });
			expect(sort.value).toBe(value);
		}
		expect(onInvalidate).toHaveBeenCalledTimes(5);
		expect(onChange).toHaveBeenCalledTimes(4);
		await vi.advanceTimersByTimeAsync(300);
		expect(onChange).toHaveBeenCalledTimes(4);
	});
});
