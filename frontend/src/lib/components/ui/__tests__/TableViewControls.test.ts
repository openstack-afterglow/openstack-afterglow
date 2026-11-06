import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { t } from '$lib/i18n/ns/common';
import TableViewFixture from './TableViewFixture.svelte';
import TableViewModalFixture from './TableViewModalFixture.svelte';
import { tick } from 'svelte';

const filterLabel = () => t('table.filterColumn', { column: 'Status' });
const visible = () => screen.getByTestId('visible-rows').textContent;

async function openStatus() {
	const trigger = screen.getByRole('button', { name: filterLabel() });
	await fireEvent.click(trigger);
	return { trigger, dialog: screen.getByRole('dialog', { name: filterLabel() }) };
}

describe('shared table controls', () => {
	it('cycles heading aria-sort and shares exact state with compact controls', async () => {
		render(TableViewFixture);
		const heading = screen.getByRole('columnheader', { name: /Name/ });
		const sort = within(heading).getByRole('button', { name: t('table.sortColumn', { column: 'Name', direction: t('table.none') }) });
		expect(heading.getAttribute('aria-sort')).toBe('none');
		await fireEvent.click(sort);
		expect(heading.getAttribute('aria-sort')).toBe('ascending');
		expect(visible()).toBe('host0,host1,host2,host10');
		await fireEvent.click(screen.getByRole('button', { name: 'Switch layout' }));
		await fireEvent.click(screen.getByRole('button', { name: t('table.sortColumn', { column: 'Name', direction: t('table.ascending') }) }));
		expect(visible()).toBe('host10,host2,host1,host0');
		await fireEvent.click(screen.getByRole('button', { name: 'Switch layout' }));
		expect(screen.getByRole('columnheader', { name: /Name/ }).getAttribute('aria-sort')).toBe('descending');
	});

	it('uses full labels as click targets, supports select none/all/reset, and retains absent selected facets', async () => {
		render(TableViewFixture);
		const { dialog, trigger } = await openStatus();
		await fireEvent.click(within(dialog).getByRole('button', { name: t('table.selectNone') }));
		expect(visible()).toBe('');
		expect(screen.getByRole('button', { name: filterLabel(), description: t('selection.count', { count: 0 }) })).toBe(trigger);
		expect(trigger.textContent).toContain('0');
		const pausedLabel = within(dialog).getByText('paused').closest('label');
		if (!pausedLabel) throw new Error('value text must label its checkbox');
		await fireEvent.click(pausedLabel);
		expect((within(dialog).getByRole('checkbox', { name: 'paused' }) as HTMLInputElement).checked).toBe(true);
		expect(visible()).toBe('host2');
		expect(screen.getByRole('button', { name: filterLabel(), description: t('selection.count', { count: 1 }) })).toBe(trigger);
		await fireEvent.keyDown(dialog, { key: 'Escape' });
		await fireEvent.click(screen.getByRole('button', { name: 'Refresh' }));
		expect(visible()).toBe('');
		const reopened = await openStatus();
		expect((within(reopened.dialog).getByRole('checkbox', { name: 'paused' }) as HTMLInputElement).checked).toBe(true);
		expect(within(reopened.dialog).getByText('paused').parentElement?.textContent).toBe('paused0');
		await fireEvent.click(within(reopened.dialog).getByRole('button', { name: t('table.selectAll') }));
		expect(visible()).toBe('host99');
		await fireEvent.click(within(reopened.dialog).getByRole('button', { name: t('table.resetFilter') }));
		expect(trigger.querySelector('.filter-count')).toBeNull();
		expect(screen.queryByRole('button', { name: filterLabel(), description: t('selection.count', { count: 1 }) })).toBeNull();
	});

	it('searches facet values as regex and keeps missing distinct from an empty string', async () => {
		render(TableViewFixture);
		const { dialog } = await openStatus();
		expect(within(dialog).getByRole('checkbox', { name: t('table.missing') })).toBeTruthy();
		expect(within(dialog).getByRole('checkbox', { name: t('table.emptyValue') })).toBeTruthy();
		const search = within(dialog).getByRole('searchbox', { name: t('table.searchValues') });
		await fireEvent.input(search, { target: { value: '^(active|paused)$' } });
		expect(within(dialog).getAllByRole('checkbox')).toHaveLength(2);
		await fireEvent.input(search, { target: { value: '[' } });
		expect(within(dialog).queryAllByRole('checkbox')).toHaveLength(0);
		expect(within(dialog).getByRole('alert').textContent).toBe(t('table.regexError'));
	});

	it('portals outside table clipping, opens above a low heading, and restores keyboard focus', async () => {
		const { container } = render(TableViewFixture);
		const trigger = screen.getByRole('button', { name: filterLabel() });
		const top = window.innerHeight - 50;
		trigger.getBoundingClientRect = () => ({ top, bottom: top + 36, left: 100, right: 136, width: 36, height: 36, x: 100, y: top, toJSON: () => ({}) }) as DOMRect;
		await fireEvent.click(trigger);
		const dialog = screen.getByRole('dialog', { name: filterLabel() });
		expect(container.contains(dialog)).toBe(false);
		expect(document.body.contains(dialog)).toBe(true);
		expect(Number.parseFloat(dialog.style.bottom)).toBe(window.innerHeight - top + 4);
		expect(dialog.style.top).toBe('');
		expect(Number.parseFloat(dialog.style.maxHeight)).toBeLessThan(top);
		const search = within(dialog).getByRole('searchbox');
		expect(document.activeElement).toBe(search);
		await fireEvent.keyDown(search, { key: 'ArrowDown' });
		expect(document.activeElement).not.toBe(search);
		await fireEvent.keyDown(document.activeElement ?? search, { key: 'Escape' });
		expect(screen.queryByRole('dialog')).toBeNull();
		expect(document.activeElement).toBe(trigger);
		await fireEvent.click(trigger);
		await fireEvent.pointerDown(screen.getByRole('button', { name: 'Outside' }));
		expect(screen.queryByRole('dialog')).toBeNull();
	});

	it('exposes explicit ascending, descending and default actions without losing the filter menu', async () => {
		render(TableViewFixture);
		const { dialog } = await openStatus();
		await fireEvent.click(within(dialog).getByRole('button', { name: t('table.descending') }));
		expect(screen.getByRole('columnheader', { name: /Status/ }).getAttribute('aria-sort')).toBe('descending');
		await fireEvent.click(within(dialog).getByRole('button', { name: t('table.none') }));
		expect(screen.getByRole('columnheader', { name: /Status/ }).getAttribute('aria-sort')).toBe('none');
		expect(visible()).toBe('host10,host2,host1,host0');
	});

	it('shows invalid top-level regex feedback while retaining empty-result controls', async () => {
		render(TableViewFixture);
		await fireEvent.input(screen.getByRole('searchbox', { name: 'Search' }), { target: { value: '[' } });
		expect(visible()).toBe('');
		expect(screen.getByRole('alert').textContent).toBe(t('table.regexError'));
		expect(screen.getByRole('button', { name: filterLabel() })).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: 'Refresh' }));
		expect((screen.getByRole('searchbox', { name: 'Search' }) as HTMLInputElement).value).toBe('[');
		expect(visible()).toBe('');
	});

	it('selects only one native value, clears with select all, and never hides a stale loaded provider row locally', async () => {
		const onNativeChange = vi.fn();
		render(TableViewFixture, { native: true, onNativeChange });
		const { dialog } = await openStatus();
		expect(within(dialog).getByText(t('table.nativeFilterScope'))).toBeTruthy();
		expect(within(dialog).queryByRole('button', { name: t('table.selectNone') })).toBeNull();
		await fireEvent.click(within(dialog).getByRole('checkbox', { name: 'Paused' }));
		expect(onNativeChange).toHaveBeenLastCalledWith('status', ['paused']);
		expect(visible()).toBe('host10,host2,host1,host0');
		await fireEvent.click(within(dialog).getByRole('checkbox', { name: 'Active' }));
		expect(onNativeChange).toHaveBeenLastCalledWith('status', ['active']);
		expect((within(dialog).getByRole('checkbox', { name: 'Paused' }) as HTMLInputElement).checked).toBe(false);
		await fireEvent.click(within(dialog).getByRole('button', { name: t('table.selectAll') }));
		expect(onNativeChange).toHaveBeenLastCalledWith('status', null);
	});

	it('applies arbitrary provider values explicitly and keeps option regex search independent', async () => {
		const onNativeChange = vi.fn();
		const onSortChange = vi.fn();
		render(TableViewFixture, { native: true, onNativeChange, onSortChange });
		const name = t('table.filterColumn', { column: 'Name' });
		await fireEvent.click(screen.getByRole('button', { name }));
		const dialog = screen.getByRole('dialog', { name });
		const nativeValue = within(dialog).getByRole('textbox', { name: t('table.filterValue') });
		await fireEvent.input(nativeValue, { target: { value: 'arbitrary-provider-id' } });
		expect(onNativeChange).not.toHaveBeenCalled();
		await fireEvent.click(within(dialog).getByRole('button', { name: t('table.apply') }));
		expect(onNativeChange).toHaveBeenCalledTimes(1);
		expect(onNativeChange).toHaveBeenLastCalledWith('name', ['arbitrary-provider-id']);
		await fireEvent.input(within(dialog).getByRole('searchbox'), { target: { value: '[' } });
		expect(onNativeChange).toHaveBeenCalledTimes(1);
		expect(visible()).toBe('host10,host2,host1,host0');
		await fireEvent.click(within(dialog).getByRole('button', { name: t('table.descending') }));
		expect(onSortChange).toHaveBeenCalledTimes(1);
		expect(onSortChange).toHaveBeenLastCalledWith({ key: 'name', direction: 'desc' });
	});

	it('applies a native range once, preserves drafts, and offers compact reset for a range-only condition', async () => {
		const onRangeChange = vi.fn();
		render(TableViewFixture, { native: true, onRangeChange });
		const name = t('table.filterColumn', { column: 'Size' });
		await fireEvent.click(screen.getByRole('button', { name }));
		let dialog = screen.getByRole('dialog', { name });
		await fireEvent.input(within(dialog).getByRole('textbox', { name: t('table.minimum') }), { target: { value: '10' } });
		await fireEvent.input(within(dialog).getByRole('textbox', { name: t('table.maximum') }), { target: { value: '99' } });
		expect(onRangeChange).not.toHaveBeenCalled();
		await fireEvent.click(within(dialog).getByRole('button', { name: t('table.apply') }));
		expect(onRangeChange).toHaveBeenCalledTimes(1);
		expect(onRangeChange).toHaveBeenLastCalledWith('10', '99');
		await fireEvent.keyDown(dialog, { key: 'Escape' });
		await fireEvent.click(screen.getByRole('button', { name }));
		dialog = screen.getByRole('dialog', { name });
		expect((within(dialog).getByRole('textbox', { name: t('table.minimum') }) as HTMLInputElement).value).toBe('10');
		expect((within(dialog).getByRole('textbox', { name: t('table.maximum') }) as HTMLInputElement).value).toBe('99');
		await fireEvent.keyDown(dialog, { key: 'Escape' });
		await fireEvent.click(screen.getByRole('button', { name: 'Switch layout' }));
		await fireEvent.click(screen.getByRole('button', { name: t('table.resetView') }));
		expect(onRangeChange).toHaveBeenCalledTimes(2);
		expect(onRangeChange).toHaveBeenLastCalledWith('', '');
		expect(screen.queryByRole('button', { name: t('table.resetView') })).toBeNull();
	});

	it('keeps equal numeric range endpoints and cleared bounds as strings for native query adapters', async () => {
		const onRangeChange = vi.fn();
		render(TableViewFixture, { native: true, onRangeChange });
		const name = t('table.filterColumn', { column: 'Size' });
		await fireEvent.click(screen.getByRole('button', { name }));
		const dialog = screen.getByRole('dialog', { name });
		const minimum = within(dialog).getByRole('textbox', { name: t('table.minimum') });
		const maximum = within(dialog).getByRole('textbox', { name: t('table.maximum') });
		const apply = within(dialog).getByRole('button', { name: t('table.apply') });
		await fireEvent.input(minimum, { target: { value: '10' } });
		await fireEvent.input(maximum, { target: { value: '10' } });
		await fireEvent.click(apply);
		expect(onRangeChange).toHaveBeenLastCalledWith('10', '10');
		await fireEvent.input(maximum, { target: { value: '' } });
		await fireEvent.click(apply);
		expect(onRangeChange).toHaveBeenLastCalledWith('10', '');
		await fireEvent.input(minimum, { target: { value: '' } });
		await fireEvent.click(apply);
		expect(onRangeChange).toHaveBeenLastCalledWith('', '');
		expect(onRangeChange).toHaveBeenCalledTimes(3);
	});

	it('synchronizes range drafts after an explicit scalar choice or reset without undoing that native choice', async () => {
		const onRangeChange = vi.fn();
		const onNativeChange = vi.fn();
		render(TableViewFixture, { native: true, combinedRange: true, onRangeChange, onNativeChange });
		const name = t('table.filterColumn', { column: 'Size' });
		await fireEvent.click(screen.getByRole('button', { name }));
		const dialog = screen.getByRole('dialog', { name });
		await fireEvent.click(within(dialog).getByRole('checkbox', { name: '10 GiB' }));
		expect(onNativeChange).toHaveBeenLastCalledWith('size', ['10']);
		expect((within(dialog).getByRole('textbox', { name: t('table.minimum') }) as HTMLInputElement).value).toBe('10');
		expect((within(dialog).getByRole('textbox', { name: t('table.maximum') }) as HTMLInputElement).value).toBe('10');
		await fireEvent.click(within(dialog).getByRole('button', { name: t('table.apply') }));
		expect(onRangeChange).not.toHaveBeenCalled();
		await fireEvent.click(within(dialog).getAllByRole('button', { name: t('table.resetFilter') }).at(-1) as HTMLElement);
		expect(onNativeChange).toHaveBeenLastCalledWith('size', null);
		expect((within(dialog).getByRole('textbox', { name: t('table.minimum') }) as HTMLInputElement).value).toBe('');
		expect((within(dialog).getByRole('textbox', { name: t('table.maximum') }) as HTMLInputElement).value).toBe('');
	});

	it('owns nested modal focus so Tab stays in the portal and Escape closes only the filter first', async () => {
		render(TableViewModalFixture);
		const opener = screen.getByRole('button', { name: 'Open table dialog' });
		opener.focus();
		await fireEvent.click(opener);
		const parent = screen.getByRole('dialog', { name: 'Table dialog' });
		const trigger = within(parent).getByRole('button', { name: filterLabel() });
		await fireEvent.click(trigger);
		const filter = screen.getByRole('dialog', { name: filterLabel() });
		const search = within(filter).getByRole('searchbox');
		await waitFor(() => expect(document.activeElement).toBe(search));
		const last = within(filter).getAllByRole('checkbox').at(-1) as HTMLElement;
		last.focus();
		await fireEvent.keyDown(last, { key: 'Tab' });
		expect(filter.contains(document.activeElement)).toBe(true);
		await fireEvent.keyDown(document, { key: 'Escape' });
		expect(screen.queryByRole('dialog', { name: filterLabel() })).toBeNull();
		expect(screen.getByRole('dialog', { name: 'Table dialog' })).toBe(parent);
		await waitFor(() => expect(document.activeElement).toBe(trigger));
		await fireEvent.keyDown(document, { key: 'Escape' });
		expect(screen.queryByRole('dialog', { name: 'Table dialog' })).toBeNull();
		await waitFor(() => expect(document.activeElement).toBe(opener));
	});

	it('dismisses the portal when scrolling moves its heading outside either vertical viewport edge', async () => {
		render(TableViewFixture);
		const trigger = screen.getByRole('button', { name: filterLabel() });
		let top = 100;
		trigger.getBoundingClientRect = () => ({ top, bottom: top + 36, left: 100, right: 136, width: 36, height: 36, x: 100, y: top, toJSON: () => ({}) }) as DOMRect;
		await fireEvent.click(trigger);
		expect(screen.getByRole('dialog', { name: filterLabel() })).toBeTruthy();
		trigger.focus();
		top = -50;
		await fireEvent.scroll(window);
		expect(screen.queryByRole('dialog', { name: filterLabel() })).toBeNull();
		top = 100;
		await fireEvent.click(trigger);
		expect(screen.getByRole('dialog', { name: filterLabel() })).toBeTruthy();
		trigger.focus();
		top = window.innerHeight + 10;
		await fireEvent.scroll(window);
		expect(screen.queryByRole('dialog', { name: filterLabel() })).toBeNull();
	});

	it('dismisses a hidden ancestor portal even with a visible nested provider, without resetting the table condition', async () => {
		const { rerender } = render(TableViewModalFixture, { visible: true });
		await fireEvent.click(screen.getByRole('button', { name: 'Open table dialog' }));
		const { dialog } = await openStatus();
		await fireEvent.click(within(dialog).getByRole('button', { name: t('table.selectNone') }));
		expect(visible()).toBe('');
		await rerender({ visible: false });
		expect(screen.queryByRole('dialog', { name: filterLabel() })).toBeNull();
		expect(screen.getByRole('dialog', { name: 'Table dialog' })).toBeTruthy();
		await rerender({ visible: true });
		const reopened = await openStatus();
		expect(within(reopened.dialog).getAllByRole('checkbox').every((checkbox) => !(checkbox as HTMLInputElement).checked)).toBe(true);
		expect(visible()).toBe('');
	});

	it('keeps a focused value-search and its draft open when the soft keyboard shrinks the visual viewport', async () => {
		const originalViewport = Object.getOwnPropertyDescriptor(window, 'visualViewport');
		const viewport = Object.assign(new EventTarget(), {
			height: window.innerHeight, width: window.innerWidth, offsetTop: 0, offsetLeft: 0,
		});
		Object.defineProperty(window, 'visualViewport', { configurable: true, value: viewport });
		const result = render(TableViewFixture);
		try {
			const trigger = screen.getByRole('button', { name: filterLabel() });
			const top = window.innerHeight - 80;
			trigger.getBoundingClientRect = () => ({ top, bottom: top + 36, left: 100, right: 136, width: 36, height: 36, x: 100, y: top, toJSON: () => ({}) }) as DOMRect;
			await fireEvent.click(trigger);
			const dialog = screen.getByRole('dialog', { name: filterLabel() });
			const search = within(dialog).getByRole('searchbox');
			await fireEvent.input(search, { target: { value: '^paused$' } });
			search.focus();
			viewport.height = Math.floor(window.innerHeight / 2);
			viewport.dispatchEvent(new Event('resize'));
			await tick();
			expect(screen.getByRole('dialog', { name: filterLabel() })).toBe(dialog);
			expect((search as HTMLInputElement).value).toBe('^paused$');
			expect(document.activeElement).toBe(search);
			expect(window.innerHeight - Number.parseFloat(dialog.style.bottom)).toBeLessThanOrEqual(viewport.height);
			expect(within(dialog).getAllByRole('checkbox')).toHaveLength(1);
		} finally {
			await result.unmount();
			if (originalViewport) Object.defineProperty(window, 'visualViewport', originalViewport);
			else Reflect.deleteProperty(window, 'visualViewport');
		}
	});
});
