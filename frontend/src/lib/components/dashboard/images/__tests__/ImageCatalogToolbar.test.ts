import { fireEvent, render, screen } from '@testing-library/svelte';
import { describe, expect, it } from 'vitest';
import ImageCatalogToolbar from '../ImageCatalogToolbar.svelte';
import { createImageCatalog } from '$lib/stores/imageCatalog.svelte';
import type { ImageInfo } from '$lib/types/compute';
import { t } from '$lib/i18n/ns/images-keys';
import { t as tc } from '$lib/i18n/ns/common';

const images: ImageInfo[] = [
	{ id: 'ubuntu', name: 'ubuntu:24.04', repository: 'ubuntu', tag: '24.04', status: 'active' },
	{ id: 'debian', name: 'debian:12', repository: 'debian', tag: '12', status: 'active' },
];

describe('ImageCatalogToolbar', () => {
	it('binds anchored regex to catalog state and exposes invalid syntax without literal fallback', async () => {
		const catalog = createImageCatalog(() => images);
		render(ImageCatalogToolbar, { catalog });
		const input = screen.getByRole('searchbox', { name: t('catalogToolbar.searchLabel') });
		await fireEvent.input(input, { target: { value: '^ubuntu$' } });
		expect(catalog.filteredImages.map(image => image.id)).toEqual(['ubuntu']);
		await fireEvent.input(input, { target: { value: '[' } });
		expect(catalog.view.error).toBe(true);
		expect(catalog.filteredImages).toEqual([]);
		expect(screen.getByText(tc('table.regexError'))).toBeTruthy();
	});

	it('explicit reset clears query, exact-value filters and sort', async () => {
		const catalog = createImageCatalog(() => images);
		catalog.searchQuery = '^ubuntu$';
		catalog.view.setFilter('tag', ['24.04']);
		catalog.view.toggleSort('repository');
		render(ImageCatalogToolbar, { catalog });
		await fireEvent.click(screen.getByRole('button', { name: t('catalogToolbar.clearFilters') }));
		expect(catalog.searchQuery).toBe('');
		expect(catalog.view.filters).toEqual({});
		expect(catalog.view.sort).toBeNull();
		expect(catalog.filteredImages).toHaveLength(2);
	});
});
