import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { afterEach, describe, expect, it } from 'vitest';
import { t } from '$lib/i18n/ns/common';
import AdminInstanceFilters from '../instances/AdminInstanceFilters.svelte';

afterEach(cleanup);

describe('AdminInstanceFilters regex feedback', () => {
	it('preserves the entered expression and clears invalid-syntax feedback when repaired', async () => {
		render(AdminInstanceFilters, { nameSearch: '' });
		const search = screen.getByRole('searchbox') as HTMLInputElement;
		await fireEvent.input(search, { target: { value: '[' } });
		expect(search.value).toBe('[');
		expect(search.getAttribute('aria-invalid')).toBe('true');
		expect(screen.getByText(t('table.regexError'))).toBeTruthy();
		await fireEvent.input(search, { target: { value: '^(vm-one|vm-two)$' } });
		expect(search.value).toBe('^(vm-one|vm-two)$');
		expect(search.getAttribute('aria-invalid')).not.toBe('true');
		expect(screen.queryByText(t('table.regexError'))).toBeNull();
	});
});
