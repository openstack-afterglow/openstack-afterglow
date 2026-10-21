import { cleanup, render, screen, within } from '@testing-library/svelte';
import { afterEach, expect, it, vi } from 'vitest';
import type * as Reactivity from 'svelte/reactivity';
import { RESOURCE_CATEGORIES } from '$lib/types/userDashboard';
import type { ProjectResourceInventory } from '$lib/types/userDashboard';
import { t } from '$lib/i18n/ns/dashboard-home';

const viewport = vi.hoisted(() => ({ desktop: false }));
vi.mock('svelte/reactivity', async (importOriginal) => {
	const original = await importOriginal<typeof Reactivity>();
	return { ...original, MediaQuery: class { get current() { return viewport.desktop; } } };
});
import ProjectUsageTable from './ProjectUsageTable.svelte';

afterEach(() => { cleanup(); viewport.desktop = false; });

function project(): ProjectResourceInventory {
	// Object.fromEntries loses the key union; every registry category is constructed here.
	const resources = Object.fromEntries(RESOURCE_CATEGORIES.map(category => [category, { state: 'ready', count: 0, items: [] }])) as unknown as ProjectResourceInventory['resources'];
	return {
		project_id: 'project-a', project_name: 'Project A',
		resources,
		usage: { vcpus: 4, ram_mb: null, storage_gb: 0 }
	};
}

it('prioritizes nonzero and unknown counts while retaining all resource and usage values in disclosure', () => {
	const row = project();
	row.resources.instances = { state: 'ready', count: 2, items: [] };
	row.resources.volumes = { state: 'failed', count: null, items: [], error: 'unavailable' };
	row.resources.secrets = { state: 'ready', count: 8, items: [] };
	const { container } = render(ProjectUsageTable, { projects: [row] });
	expect(screen.queryByRole('table')).toBeNull();
	expect(screen.getByRole('heading', { name: 'Project A' })).toBeTruthy();
	const card = container.querySelector('article')!;
	const details = card.querySelector('details')!;
	expect(details.open).toBe(false);
	for (const category of RESOURCE_CATEGORIES) expect(within(details).getByText(t(`myResources.category.${category}`))).toBeTruthy();
	expect(within(details).getByText(t('myResources.usage.ram_mb'))).toBeTruthy();
	expect(within(details).getAllByText(t('myResources.unknown')).length).toBeGreaterThan(0);
	const primary = card.querySelector('dl')!;
	expect(within(primary).getByText(t('myResources.category.instances'))).toBeTruthy();
	expect(within(primary).getByText(t('myResources.category.volumes'))).toBeTruthy();
	expect(within(primary).getByText(t('myResources.category.secrets'))).toBeTruthy();
	expect(within(primary).queryByText(t('myResources.category.networks'))).toBeNull();
});

it('retains the complete desktop table instead of mounting duplicate cards', () => {
	viewport.desktop = true;
	const { container } = render(ProjectUsageTable, { projects: [project()] });
	expect(screen.getByRole('table')).toBeTruthy();
	expect(screen.getByRole('columnheader', { name: t('myResources.category.secrets') })).toBeTruthy();
	expect(container.querySelector('article')).toBeNull();
});
