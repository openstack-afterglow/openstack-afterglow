import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/svelte';
import RecentInstancesCard from '../RecentInstancesCard.svelte';
import type { DashboardRecentInstance } from '$lib/types/compute';

afterEach(() => cleanup());

const instances: DashboardRecentInstance[] = ['first', 'second'].map((id) => ({
	id, name: id, status: 'ACTIVE', flavor_name: 'small', ip_addresses: [], created_at: '',
}));

describe('recent instances refresh', () => {
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
});
