import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/svelte';
import RecentInstancesCard from '../RecentInstancesCard.svelte';
import type { DashboardRecentInstance } from '$lib/types/compute';
import { t as tp } from '$lib/i18n/ns/compute-pools';

afterEach(() => cleanup());

const instances: DashboardRecentInstance[] = ['first', 'second'].map((id) => ({
	id, name: id, status: 'ACTIVE', flavor_name: 'small', ip_addresses: [], created_at: '',
}));

describe('recent instances refresh', () => {
	it('shows verified specifications or the original historical flavor name', () => {
		render(RecentInstancesCard, { instances: [
			{ ...instances[0], flavor_name: 'm1.small', flavor_display_name: 'cpu.2c_1.5g' },
			{ ...instances[1], flavor_name: 'gpu.render', flavor_display_name: null },
			{ ...instances[0], id: 'missing', name: 'missing', flavor_name: null },
		], pending: false, error: null });
		expect(screen.getByText('2 vCPU · 1.5 GiB RAM')).toBeTruthy();
		expect(screen.getByText('gpu.render')).toBeTruthy();
		expect(screen.getByText(tp('unknown'))).toBeTruthy();
		expect(screen.queryByText('m1.small')).toBeNull();
		expect(screen.getByRole('link', { name: 'first' }).getAttribute('href')).toBe('/dashboard/instances/first');
	});
	it('keeps existing resource rows mounted while polling and reordering', async () => {
		const rendered = render(RecentInstancesCard, { instances, pending: false, error: null });
		const first = screen.getByText('first');
		const second = screen.getByText('second');
		await rendered.rerender({ instances: [...instances], pending: true, error: null });
		expect(screen.getByText('first')).toBe(first);
		expect(screen.getByText('second')).toBe(second);
		await rendered.rerender({ instances: [...instances].reverse(), pending: false, error: null });
		expect(screen.getByText('first')).toBe(first);
		expect(screen.getByText('second')).toBe(second);
		expect(screen.queryByText('인스턴스가 없습니다')).toBeNull();
	});
	it('retains verified empty content during polling and reports a failed refresh separately', async () => {
		const rendered = render(RecentInstancesCard, { instances: [], pending: false, error: null, loaded: true });
		const empty = screen.getByText('인스턴스가 없습니다');
		await rendered.rerender({ instances: [], pending: true, error: null, loaded: true });
		expect(screen.getByText('인스턴스가 없습니다')).toBe(empty);
		expect(screen.queryByRole('status')).toBeNull();
		await rendered.rerender({ instances: [], pending: false, error: 'failed', loaded: true });
		expect(screen.getByText('인스턴스가 없습니다')).toBe(empty);
		expect(screen.getByText('최근 인스턴스를 불러오지 못했습니다')).toBeTruthy();
	});

	it('never converts an initial failed read into a successful empty list', () => {
		render(RecentInstancesCard, { instances: [], pending: false, error: 'failed' });
		expect(screen.getByText('최근 인스턴스를 불러오지 못했습니다')).toBeTruthy();
		expect(screen.queryByText('인스턴스가 없습니다')).toBeNull();
	});

});
