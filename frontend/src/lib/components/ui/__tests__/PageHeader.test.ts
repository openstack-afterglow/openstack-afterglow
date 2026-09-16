import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import PageHeader from '../PageHeader.svelte';

const pageHeaderSource = readFileSync(resolve(__dirname, '../PageHeader.svelte'), 'utf8');

describe('PageHeader', () => {
	it('breadcrumb 텍스트 렌더링', () => {
		render(PageHeader, { breadcrumb: 'OVERVIEW', title: 'Test' });
		expect(screen.getAllByText('OVERVIEW').length).toBeGreaterThan(0);
	});

	it('title이 h1으로 렌더링', () => {
		render(PageHeader, { breadcrumb: 'NAV', title: '인스턴스 목록' });
		const h1 = screen.getByRole('heading', { level: 1 });
		expect(h1.textContent).toBe('인스턴스 목록');
	});

	it('subtitle이 있으면 렌더링', () => {
		render(PageHeader, { breadcrumb: 'NAV', title: 'T', subtitle: '설명 텍스트' });
		expect(screen.getByText('설명 텍스트')).toBeTruthy();
	});

	it('subtitle이 없으면 p 요소 없음', () => {
		const { container } = render(PageHeader, { breadcrumb: 'NAV', title: 'T' });
		expect(container.querySelector('p')).toBeNull();
	});

	it('keeps actions wrapping while the header becomes a desktop row', () => {
		expect(pageHeaderSource).toContain('flex-direction: column');
		expect(pageHeaderSource).toContain('flex-wrap: wrap');
		expect(pageHeaderSource).toContain('@media (min-width: 1024px)');
		expect(pageHeaderSource).toContain('flex-direction: row');
		expect(pageHeaderSource).toContain('max-width: 60%');
		expect(pageHeaderSource).not.toContain('flex-wrap: nowrap');
	});
});
