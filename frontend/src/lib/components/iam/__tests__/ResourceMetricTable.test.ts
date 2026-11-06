import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { afterEach, expect, it, vi } from 'vitest';
import type * as Reactivity from 'svelte/reactivity';
import type { WorkspaceMetric } from '$lib/api/workspaceIam';
import { t } from '$lib/i18n/ns/workspace-iam';
import { t as tc } from '$lib/i18n/ns/common';

const viewport = vi.hoisted(() => ({ desktop: true }));
vi.mock('svelte/reactivity', async importOriginal => {
	const original = await importOriginal<typeof Reactivity>();
	return { ...original, MediaQuery: class { get current() { return viewport.desktop; } } };
});
import ResourceMetricTable from '../ResourceMetricTable.svelte';

const metric: WorkspaceMetric = { service: 'nova', metric: 'instances', kind: 'count', unit: 'count', value: 7, status: 'ready' };
afterEach(() => { cleanup(); viewport.desktop = true; });

it.each([true, false])('distinguishes filtered zero matches from settled empty observations without claiming pending/error data is empty (desktop=%s)', async desktop => {
	viewport.desktop = desktop;
	const view = render(ResourceMetricTable, { metrics: [metric] });
	const search = screen.getByRole('searchbox', { name: tc('table.search') });
	await fireEvent.input(search, { target: { value: '^not-a-metric$' } });
	expect(screen.getByText(tc('table.noMatches'))).toBeTruthy();
	expect(screen.queryByText(t('noObservations'))).toBeNull();
	await view.rerender({ metrics: [], settled: false });
	expect(screen.queryByText(tc('table.noMatches'))).toBeNull();
	expect(screen.queryByText(t('noObservations'))).toBeNull();
	await view.rerender({ metrics: [], settled: true });
	expect(screen.getByText(t('noObservations'))).toBeTruthy();
	expect(screen.getByRole('searchbox', { name: tc('table.search') })).toBe(search);
});
