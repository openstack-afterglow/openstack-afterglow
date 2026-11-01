import { describe, it, expect, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/svelte';
import { flushSync } from 'svelte';
import AutoRefreshControlWrapper from './_AutoRefreshControlWrapper.svelte';

describe('AutoRefreshControl', () => {
	it('turns polling off without losing the saved interval', async () => {
		render(AutoRefreshControlWrapper, { active: true, intervalSeconds: 30 });
		await fireEvent.change(screen.getByRole('combobox'), { target: { value: 'off' } });
		flushSync();
		expect(screen.getByTestId('active-state').textContent).toBe('false');
		expect(screen.getByTestId('interval-state').textContent).toBe('30');
	});

	it('enables polling and updates the bound interval from a native select change', async () => {
		render(AutoRefreshControlWrapper, { active: false, intervalSeconds: 30, intervalOptions: [10, 30, 60] });
		await fireEvent.change(screen.getByRole('combobox'), { target: { value: '10' } });
		flushSync();
		expect(screen.getByTestId('active-state').textContent).toBe('true');
		expect(screen.getByTestId('interval-state').textContent).toBe('10');
	});

	it('keeps an active saved interval selectable when options change', () => {
		render(AutoRefreshControlWrapper, { active: true, intervalSeconds: 15, intervalOptions: [10, 30, 30] });
		const select = screen.getByRole('combobox') as HTMLSelectElement;
		expect(select.value).toBe('15');
		expect([...select.options].filter((option) => option.value === '30')).toHaveLength(1);
	});

	it('performs one explicit refresh independently of polling', async () => {
		const onManualRefresh = vi.fn();
		render(AutoRefreshControlWrapper, { active: false, onManualRefresh });
		await fireEvent.click(screen.getByRole('button'));
		expect(onManualRefresh).toHaveBeenCalledOnce();
		expect(screen.getByTestId('active-state').textContent).toBe('false');
	});

	it('prevents duplicate manual refresh while a refresh is pending', () => {
		render(AutoRefreshControlWrapper, { refreshing: true });
		expect((screen.getByRole('button') as HTMLButtonElement).disabled).toBe(true);
		expect((screen.getByRole('combobox') as HTMLSelectElement).disabled).toBe(false);
	});
});
