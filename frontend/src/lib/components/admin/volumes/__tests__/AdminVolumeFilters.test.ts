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
		expect(screen.getByRole('option', { name: 'available' })).toBeTruthy();
		expect(screen.getByRole('option', { name: 'in-use' })).toBeTruthy();
		expect(screen.queryByRole('option', { name: 'error' })).toBeNull();
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
});
