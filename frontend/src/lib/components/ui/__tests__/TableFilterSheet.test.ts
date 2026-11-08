import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { t } from '$lib/i18n/ns/common';

const viewport = vi.hoisted(() => {
	const state = { mobile: true };
	// Card mode below 1024px; only the 767.98px mobile query follows state.mobile.
	const matches = (media: string) => media.includes('max-width: 767.98px') && state.mobile;
	const queries = new Map<string, MediaQueryList>();
	vi.stubGlobal('matchMedia', (media: string) => {
		let query = queries.get(media);
		if (!query) {
			const events = new EventTarget();
			query = {
				media,
				get matches() { return matches(media); },
				onchange: null,
				addEventListener: events.addEventListener.bind(events),
				removeEventListener: events.removeEventListener.bind(events),
				dispatchEvent: events.dispatchEvent.bind(events),
				addListener: () => undefined,
				removeListener: () => undefined,
			} as MediaQueryList;
			queries.set(media, query);
		}
		return query;
	});
	return {
		async set(mobile: boolean) {
			state.mobile = mobile;
			for (const query of queries.values()) query.dispatchEvent(new Event('change'));
		},
		reset() { state.mobile = true; },
	};
});

import TableViewFixture from './TableViewFixture.svelte';

const visible = () => screen.getByTestId('visible-rows').textContent;
const compact = async () => fireEvent.click(screen.getByRole('button', { name: 'Switch layout' }));
const trigger = () => screen.getByRole('button', { name: new RegExp(`^${t('table.filters')}`) });
const sheet = () => screen.getByRole('dialog', { name: t('table.filtersTitle') });
const statusSection = () => within(within(sheet()).getByText(t('table.filterColumn', { column: 'Status' })).closest('details') as HTMLElement);

beforeEach(() => viewport.reset());

describe('mobile card-mode table filter sheet', () => {
	it('replaces per-column controls with one trigger and stages sort/filter until apply', async () => {
		render(TableViewFixture);
		await compact();
		expect(screen.queryByRole('button', { name: t('table.filterColumn', { column: 'Status' }) })).toBeNull();
		expect(screen.queryByRole('button', { name: t('table.sortColumn', { column: 'Name', direction: t('table.none') }) })).toBeNull();
		await fireEvent.click(trigger());
		const dialog = sheet();
		await fireEvent.change(within(dialog).getByRole('combobox', { name: t('table.sortBy') }), { target: { value: 'name' } });
		await fireEvent.click(within(dialog).getByRole('button', { name: t('table.descending') }));
		await fireEvent.click(within(dialog).getByRole('checkbox', { name: 'active' }));
		// Nothing changes before the explicit apply action.
		expect(visible()).toBe('host10,host2,host1,host0');
		await fireEvent.click(within(dialog).getByRole('button', { name: t('table.applyQuery') }));
		expect(screen.queryByRole('dialog', { name: t('table.filtersTitle') })).toBeNull();
		expect(visible()).toBe('host2,host1,host0');
		expect(trigger().getAttribute('aria-label')).toBe(t('table.filtersActive', { count: '1' }));
		expect(trigger().textContent).toContain('1');
	});

	it('discards drafts on cancel and clears every applied condition through reset plus apply', async () => {
		const onSortChange = vi.fn();
		render(TableViewFixture, { onSortChange });
		await compact();
		await fireEvent.click(trigger());
		await fireEvent.click(statusSection().getByRole('button', { name: t('table.selectNone') }));
		await fireEvent.click(within(sheet()).getByRole('button', { name: t('actions.cancel') }));
		expect(visible()).toBe('host10,host2,host1,host0');
		expect(trigger().getAttribute('aria-label')).toBe(t('table.filters'));

		await fireEvent.click(trigger());
		await fireEvent.change(within(sheet()).getByRole('combobox', { name: t('table.sortBy') }), { target: { value: 'name' } });
		await fireEvent.click(within(sheet()).getByRole('checkbox', { name: 'paused' }));
		await fireEvent.click(within(sheet()).getByRole('button', { name: t('table.applyQuery') }));
		expect(visible()).toBe('host0,host1,host10');
		expect(onSortChange).toHaveBeenLastCalledWith({ key: 'name', direction: 'asc' });

		await fireEvent.click(trigger());
		expect((within(sheet()).getByRole('checkbox', { name: 'paused' }) as HTMLInputElement).checked).toBe(false);
		await fireEvent.click(within(sheet()).getByRole('button', { name: t('table.resetView') }));
		expect(visible()).toBe('host0,host1,host10');
		await fireEvent.click(within(sheet()).getByRole('button', { name: t('table.applyQuery') }));
		expect(visible()).toBe('host10,host2,host1,host0');
		expect(onSortChange).toHaveBeenLastCalledWith(null);
		expect(trigger().getAttribute('aria-label')).toBe(t('table.filters'));
	});

	it('applies native single-value, free-value and range changes once, only when changed', async () => {
		const onNativeChange = vi.fn();
		const onRangeChange = vi.fn();
		render(TableViewFixture, { native: true, onNativeChange, onRangeChange });
		await compact();
		await fireEvent.click(trigger());
		const dialog = sheet();
		expect(within(dialog).getByText(t('table.nativeFilterScope'))).toBeTruthy();
		await fireEvent.click(within(dialog).getByRole('checkbox', { name: 'Paused' }));
		await fireEvent.click(within(dialog).getByRole('checkbox', { name: 'Active' }));
		await fireEvent.input(within(dialog).getByRole('textbox', { name: t('table.filterValue') }), { target: { value: 'provider-id' } });
		await fireEvent.input(within(dialog).getByRole('textbox', { name: t('table.minimum') }), { target: { value: '10' } });
		expect(onNativeChange).not.toHaveBeenCalled();
		expect(onRangeChange).not.toHaveBeenCalled();
		await fireEvent.click(within(dialog).getByRole('button', { name: t('table.applyQuery') }));
		expect(onNativeChange.mock.calls).toEqual([['name', ['provider-id']], ['status', ['active']]]);
		expect(onRangeChange.mock.calls).toEqual([['10', '']]);
		expect(trigger().getAttribute('aria-label')).toBe(t('table.filtersActive', { count: '3' }));

		await fireEvent.click(trigger());
		await fireEvent.click(within(sheet()).getByRole('button', { name: t('table.applyQuery') }));
		expect(onNativeChange).toHaveBeenCalledTimes(2);
		expect(onRangeChange).toHaveBeenCalledTimes(1);
	});

	it('closes on Escape without applying and keeps tablet card mode on per-column controls', async () => {
		render(TableViewFixture);
		await compact();
		await fireEvent.click(trigger());
		await fireEvent.click(statusSection().getByRole('button', { name: t('table.selectNone') }));
		await fireEvent.keyDown(document, { key: 'Escape' });
		await waitFor(() => expect(screen.queryByRole('dialog', { name: t('table.filtersTitle') })).toBeNull());
		expect(visible()).toBe('host10,host2,host1,host0');

		await viewport.set(false);
		await waitFor(() => expect(screen.getByRole('button', { name: t('table.filterColumn', { column: 'Status' }) })).toBeTruthy());
		expect(screen.queryByRole('button', { name: new RegExp(`^${t('table.filters')}`) })).toBeNull();
	});
});
