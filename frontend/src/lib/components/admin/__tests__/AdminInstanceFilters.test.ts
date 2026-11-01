import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';
import AdminInstanceFilters from '../instances/AdminInstanceFilters.svelte';

afterEach(() => { cleanup(); vi.useRealTimers(); });

describe('AdminInstanceFilters', () => {
	it('retains immediate select changes and debounced search cleanup', async () => {
		vi.useFakeTimers();
		const onChange = vi.fn();
		const view = render(AdminInstanceFilters, {
			availableHosts: ['compute-1'], hostFilter: '', statusFilter: '', nameSearch: '', onChange,
		});
		await fireEvent.change(screen.getByRole('combobox', { name: '모든 호스트' }), { target: { value: 'compute-1' } });
		await fireEvent.change(screen.getByRole('combobox', { name: '모든 상태' }), { target: { value: 'ACTIVE' } });
		expect(onChange).toHaveBeenCalledTimes(2);
		await fireEvent.input(screen.getByRole('searchbox'), { target: { value: 'instance' } });
		expect(onChange).toHaveBeenCalledTimes(2);
		await vi.advanceTimersByTimeAsync(300);
		expect(onChange).toHaveBeenCalledTimes(3);
		await fireEvent.input(screen.getByRole('searchbox'), { target: { value: 'pending' } });
		view.unmount();
		await vi.advanceTimersByTimeAsync(300);
		expect(onChange).toHaveBeenCalledTimes(3);
	});
});
