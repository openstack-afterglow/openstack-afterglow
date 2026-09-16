import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/svelte';
import LoadingSkeleton from '../LoadingSkeleton.svelte';

describe('LoadingSkeleton', () => {
	it('기본 variant(table)는 table 요소를 렌더링', () => {
		const { container } = render(LoadingSkeleton);
		expect(container.querySelector('table')).not.toBeNull();
	});

	it('rows prop만큼 tbody tr을 생성 (table variant)', () => {
		const { container } = render(LoadingSkeleton, { rows: 3 });
		const rows = container.querySelectorAll('tbody tr');
		expect(rows).toHaveLength(3);
	});

	it('variant=card는 table 없이 카드 구조 렌더링', () => {
		const { container } = render(LoadingSkeleton, { variant: 'card', rows: 2 });
		expect(container.querySelector('table')).toBeNull();
		const cards = container.firstElementChild?.children ?? [];
		expect(cards).toHaveLength(2);
	});

	it('variant=list는 list 아이템 렌더링', () => {
		const { container } = render(LoadingSkeleton, { variant: 'list', rows: 4 });
		expect(container.querySelector('table')).toBeNull();
		const items = container.querySelectorAll('.space-y-3 > div');
		expect(items).toHaveLength(4);
	});

	it('variant=detail는 detail 구조 렌더링', () => {
		const { container } = render(LoadingSkeleton, { variant: 'detail', rows: 3 });
		expect(container.querySelector('table')).toBeNull();
		const fields = container.querySelectorAll('.grid.grid-cols-2 > div');
		expect(fields).toHaveLength(3);
	});

	it('animate-pulse 클래스가 포함됨', () => {
		const { container } = render(LoadingSkeleton);
		const pulseEls = container.querySelectorAll('.animate-pulse');
		expect(pulseEls.length).toBeGreaterThan(0);
	});
});
