import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const media = vi.hoisted(() => {
	const events = new EventTarget();
	const query = { matches: true, media: '(min-width: 1024px)', onchange: null,
		addEventListener: events.addEventListener.bind(events), removeEventListener: events.removeEventListener.bind(events),
		dispatchEvent: events.dispatchEvent.bind(events), addListener: () => {}, removeListener: () => {} };
	vi.stubGlobal('matchMedia', () => query);
	return query;
});

import AdminVolumeDomainSummary from '../AdminVolumeDomainSummary.svelte';
import { initLocale } from '$lib/i18n/runtime.svelte';
import type { AdminVolumeStatusSummary } from '$lib/types/volume';

const summary: AdminVolumeStatusSummary = {
	total: 12, total_gb: 1200, attached_count: 4, attached_gb: 500, available_count: 8, available_gb: 700,
	statuses: [], filtered_total: 2, filtered_gb: 250,
	domains: [
		{ domain_id: 'native-domain', domain_name: 'Research', owner_status: 'known', project_ids: ['native-project'], volumes: 8, volume_gb: 800, attached_volumes: 4, attached_gb: 500, available_volumes: 4, available_gb: 300 },
		{ domain_id: null, domain_name: null, owner_status: 'unknown_owner', project_ids: [], volumes: 1, volume_gb: 100, attached_volumes: 0, attached_gb: 0, available_volumes: 1, available_gb: 100 },
		{ domain_id: null, domain_name: null, owner_status: 'deleted_project', project_ids: ['deleted-project-a'], volumes: 2, volume_gb: 200, attached_volumes: 0, attached_gb: 0, available_volumes: 2, available_gb: 200 },
		{ domain_id: 'gone-domain', domain_name: null, owner_status: 'deleted_domain', project_ids: ['orphan-project'], volumes: 1, volume_gb: 100, attached_volumes: 0, attached_gb: 0, available_volumes: 1, available_gb: 100 },
	],
};

beforeEach(() => { media.matches = true; initLocale('ko'); });
afterEach(() => { cleanup(); initLocale('ko'); });

describe('AdminVolumeDomainSummary', () => {
	it('keeps complete, attached, available and filtered totals distinct and drills down using only a verified domain UUID', async () => {
		const onDomain = vi.fn();
		render(AdminVolumeDomainSummary, { summary, loading: false, scoped: false, onDomain });
		expect(screen.getByTestId('admin-volume-complete-total').textContent).toBe('볼륨 12개 · 1,200 GiB');
		expect(screen.getByTestId('admin-volume-filtered-total').textContent).toContain('볼륨 2개 · 250 GiB');
		for (const label of ['소유자 알 수 없음', '삭제된 프로젝트', '삭제된 도메인']) expect(screen.getByText(label)).toBeTruthy();
		const buttons = screen.getAllByRole('button');
		expect(buttons).toHaveLength(1);
		expect(screen.getByText('deleted-project-a')).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: 'Research 볼륨 보기' }));
		expect(onDomain).toHaveBeenCalledExactlyOnceWith('native-domain');
	});

	it('keeps multiple deleted-project UUID groups separate instead of colliding on null domain', () => {
		const first = summary.domains[2];
		render(AdminVolumeDomainSummary, { summary: { ...summary, domains: [first, { ...first, project_ids: ['deleted-project-b'] }] }, loading: false, scoped: false, onDomain: vi.fn() });
		expect(screen.getAllByText('삭제된 프로젝트')).toHaveLength(2);
		expect(screen.getByText('deleted-project-a')).toBeTruthy();
		expect(screen.getByText('deleted-project-b')).toBeTruthy();
		expect(screen.queryByRole('button')).toBeNull();
	});

	it('retains every count, capacity and drilldown when switching to mobile and tablet cards', async () => {
		const onDomain = vi.fn();
		render(AdminVolumeDomainSummary, { summary, loading: false, scoped: true, onDomain });
		media.matches = false; media.dispatchEvent(new Event('change'));
		await waitFor(() => expect(screen.getAllByRole('article')).toHaveLength(4));
		expect(screen.getByText('선택 범위 전체 인벤토리')).toBeTruthy();
		const domainCard = within(screen.getAllByRole('article')[0]);
		expect(domainCard.getByText('볼륨 8개 · 800 GiB')).toBeTruthy();
		expect(domainCard.getByText('볼륨 4개 · 500 GiB')).toBeTruthy();
		expect(domainCard.getByText('볼륨 4개 · 300 GiB')).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: 'Research 볼륨 보기' }));
		expect(onDomain).toHaveBeenCalledExactlyOnceWith('native-domain');
		media.matches = true; media.dispatchEvent(new Event('change'));
		await waitFor(() => expect(screen.queryAllByRole('article')).toHaveLength(0));
		expect(screen.getAllByRole('button')).toHaveLength(1);
	});


	it('never substitutes zero capacity for pending or unavailable inventory', async () => {
		const props = { summary: null, loading: true, scoped: false, onDomain: vi.fn() };
		const view = render(AdminVolumeDomainSummary, props);
		expect(screen.getByTestId('admin-volume-complete-total').textContent).toBe('—');
		await view.rerender({ ...props, loading: false });
		expect(screen.getByTestId('admin-volume-complete-total').textContent).toBe('—');
		expect(screen.getByTestId('admin-volume-filtered-total').textContent).not.toContain('0 GiB');
	});
});
