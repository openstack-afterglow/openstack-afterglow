import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { afterEach, describe, expect, it } from 'vitest';
import { t } from '$lib/i18n/ns/common';
import AdminVolumeFilters from '../AdminVolumeFilters.svelte';

afterEach(cleanup);

describe('AdminVolumeFilters regex search', () => {
	it('shows invalid syntax without replacing the entered expression', async () => {
		render(AdminVolumeFilters, { nameSearch: '' });
		const search = screen.getByRole('searchbox') as HTMLInputElement;
		await fireEvent.input(search, { target: { value: '[' } });
		expect(search.value).toBe('[');
		expect(search.getAttribute('aria-invalid')).toBe('true');
		expect(screen.getByText(t('table.regexError'))).toBeTruthy();
		await fireEvent.input(search, { target: { value: '^(fast|archive)$' } });
		expect(search.value).toBe('^(fast|archive)$');
		expect(search.getAttribute('aria-invalid')).not.toBe('true');
		expect(screen.queryByText(t('table.regexError'))).toBeNull();
	});
});
