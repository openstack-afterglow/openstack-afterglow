import { render } from '@testing-library/svelte';
import { describe, expect, it } from 'vitest';
import Donut from '../Donut.svelte';

describe('draw charts', () => {
	it.each([[-10, 1], [25, 0.75], [120, 0]])('clamps donut fill extent for %s', (value, offset) => {
		const { container } = render(Donut, { value });
		expect(container.querySelector('.donut-fill')?.getAttribute('stroke-dashoffset')).toBe(String(offset));
	});

	it('keeps the donut empty when its maximum is zero', () => {
		const { container } = render(Donut, { value: 50, max: 0 });
		expect(container.querySelector('.donut-fill')?.getAttribute('stroke-dashoffset')).toBe('1');
	});
});
