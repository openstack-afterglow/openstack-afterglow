import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { initLocale } from '$lib/i18n/runtime.svelte';
import { t } from '$lib/i18n/ns/file-storage';
import { t as commonT } from '$lib/i18n/ns/common';
import type { FileStorageWizardStore } from '$lib/stores/fileStorageWizardStore.svelte';
import Harness from './MetadataEditorHarness.svelte';

beforeEach(() => initLocale('ko'));
afterEach(cleanup);

describe('file storage metadata stays editable as a draft', () => {
	it('keeps a newly added blank row visible under active search, then applies an explicitly changed search', async () => {
		let store!: FileStorageWizardStore;
		render(Harness, { onStore: value => { store = value; } });
		const search = screen.getByRole('searchbox');
		await fireEvent.input(search, { target: { value: '^matching$' } });
		expect(screen.getAllByPlaceholderText(t('wizard.basic.metadataKeyPlaceholder'))).toHaveLength(1);
		await fireEvent.click(screen.getByRole('button', { name: t('wizard.actions.add') }));
		const keys = screen.getAllByPlaceholderText<HTMLInputElement>(t('wizard.basic.metadataKeyPlaceholder'));
		const values = screen.getAllByPlaceholderText<HTMLInputElement>(t('wizard.basic.metadataValuePlaceholder'));
		expect(keys).toHaveLength(2);
		expect(values).toHaveLength(2);
		await fireEvent.input(keys[1], { target: { value: 'new-key' } });
		await fireEvent.input(values[1], { target: { value: 'new-value' } });
		expect(store.metaEntries).toEqual([
			{ key: 'matching', value: 'one' }, { key: 'other', value: 'two' }, { key: 'new-key', value: 'new-value' },
		]);
		expect(screen.getAllByPlaceholderText(t('wizard.basic.metadataKeyPlaceholder'))[1]).toBe(keys[1]);
		await fireEvent.input(search, { target: { value: '^new-key$' } });
		expect(screen.getAllByPlaceholderText(t('wizard.basic.metadataKeyPlaceholder'))).toEqual([keys[1]]);
	});

	it('retains the same field through key changes and deletion of another row without rebinding another value', async () => {
		let store!: FileStorageWizardStore;
		render(Harness, { onStore: value => { store = value; } });
		const search = screen.getByRole('searchbox');
		await fireEvent.input(search, { target: { value: '^matching$' } });
		const key = screen.getAllByPlaceholderText<HTMLInputElement>(t('wizard.basic.metadataKeyPlaceholder'))[0];
		key.focus();
		for (const value of ['c', 'ch', 'changed']) {
			await fireEvent.input(key, { target: { value } });
			expect(screen.getAllByPlaceholderText(t('wizard.basic.metadataKeyPlaceholder'))[0]).toBe(key);
			expect(document.activeElement).toBe(key);
			expect(store.metaEntries[0]).toEqual({ key: value, value: 'one' });
			expect(store.metaEntries[1]).toEqual({ key: 'other', value: 'two' });
		}
		await fireEvent.input(search, { target: { value: '' } });
		const secondKey = screen.getAllByPlaceholderText(t('wizard.basic.metadataKeyPlaceholder'))[1];
		const secondValue = screen.getAllByPlaceholderText<HTMLInputElement>(t('wizard.basic.metadataValuePlaceholder'))[1];
		await fireEvent.click(screen.getAllByRole('button', { name: '✕' })[0]);
		expect(screen.getAllByPlaceholderText(t('wizard.basic.metadataKeyPlaceholder'))).toEqual([secondKey]);
		await fireEvent.input(secondValue, { target: { value: 'two-edited' } });
		expect(store.metaEntries).toEqual([{ key: 'other', value: 'two-edited' }]);
	});

	it('keeps the current key-sort order and focus while typing, then honors an explicit sort change', async () => {
		render(Harness, { onStore: () => {} });
		await fireEvent.click(screen.getByRole('button', { name: commonT('table.sortColumn', { column: commonT('table.key'), direction: commonT('table.none') }) }));
		const keys = screen.getAllByPlaceholderText<HTMLInputElement>(t('wizard.basic.metadataKeyPlaceholder'));
		expect(keys.map(input => input.value)).toEqual(['matching', 'other']);
		keys[0].focus();
		for (const value of ['z', 'zz', 'zzz']) {
			await fireEvent.input(keys[0], { target: { value } });
			expect(screen.getAllByPlaceholderText(t('wizard.basic.metadataKeyPlaceholder'))).toEqual(keys);
			expect(document.activeElement).toBe(keys[0]);
		}
		await fireEvent.click(screen.getByRole('button', { name: commonT('table.sortColumn', { column: commonT('table.key'), direction: commonT('table.ascending') }) }));
		await fireEvent.click(screen.getByRole('button', { name: commonT('table.sortColumn', { column: commonT('table.key'), direction: commonT('table.descending') }) }));
		await fireEvent.click(screen.getByRole('button', { name: commonT('table.sortColumn', { column: commonT('table.key'), direction: commonT('table.none') }) }));
		expect(screen.getAllByPlaceholderText<HTMLInputElement>(t('wizard.basic.metadataKeyPlaceholder')).map(input => input.value)).toEqual(['other', 'zzz']);
	});
});
