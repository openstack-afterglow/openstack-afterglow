import { fireEvent, screen, within } from '@testing-library/svelte';
import { t } from '$lib/i18n/ns/common';

export function columnHeader(column: string): HTMLElement {
	const name = t('table.filterColumn', { column });
	const header = screen.getAllByRole('columnheader').find((node) => within(node).queryByRole('button', { name }));
	if (!header) throw new Error(`Missing column: ${column}`);
	return header;
}

export async function sortColumn(column: string): Promise<void> {
	await fireEvent.click(within(columnHeader(column)).getAllByRole('button')[0]);
}

export async function setColumnValues(column: string, values: string[]): Promise<void> {
	const name = t('table.filterColumn', { column });
	await fireEvent.click(within(columnHeader(column)).getByRole('button', { name }));
	const dialog = within(screen.getByRole('dialog', { name }));
	await fireEvent.click(dialog.getByRole('button', { name: t('table.selectNone') }));
	for (const value of values) await fireEvent.click(dialog.getByRole('checkbox', { name: value }));
	await fireEvent.click(dialog.getByRole('button', { name: t('actions.close') }));
}

export async function clearColumn(column: string): Promise<void> {
	const name = t('table.filterColumn', { column });
	await fireEvent.click(within(columnHeader(column)).getByRole('button', { name }));
	const dialog = within(screen.getByRole('dialog', { name }));
	await fireEvent.click(dialog.getByRole('button', { name: t('table.resetFilter') }));
	await fireEvent.click(dialog.getByRole('button', { name: t('actions.close') }));
}
