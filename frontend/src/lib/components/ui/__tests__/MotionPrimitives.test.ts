import { flushSync } from 'svelte';
import { render, screen } from '@testing-library/svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';
import AnimatedNumber from '../AnimatedNumber.svelte';
import ProgressTrack from '../ProgressTrack.svelte';

afterEach(() => {
	vi.unstubAllGlobals();
	vi.restoreAllMocks();
	delete (Element.prototype as Partial<Element> & { animate?: unknown }).animate;
});

describe('ProgressTrack', () => {
	it('clamps out-of-range values for assistive technology and the fill', () => {
		const { container, rerender } = render(ProgressTrack, { value: 140, label: '업로드' });
		const bar = screen.getByRole('progressbar', { name: '업로드' });
		expect(bar.getAttribute('aria-valuenow')).toBe('100');
		expect((container.querySelector('.progress-fill') as HTMLElement).style.clipPath).toBe('inset(0 0% 0 0)');
		expect(container.querySelector('.progress-fill')?.textContent).toContain('#');
		rerender({ value: -8, label: '업로드' });
		expect(bar.getAttribute('aria-valuenow')).toBe('0');
	});

	it('renders unknown amounts as indeterminate instead of a fake value', () => {
		const { container } = render(ProgressTrack, { value: null, label: '해시 계산', valueText: '준비 중' });
		const bar = screen.getByRole('progressbar', { name: '해시 계산' });
		expect(bar.hasAttribute('aria-valuenow')).toBe(false);
		expect(bar.getAttribute('aria-valuetext')).toBe('준비 중');
		expect(container.querySelector('.progress-fill')).toBeNull();
	});

	it('shows a decorative character signal for active unknown work without a numeric value', () => {
		const { container } = render(ProgressTrack, { value: null, label: '동기화', active: true, tone: 'danger' });
		const bar = screen.getByRole('progressbar', { name: '동기화' });
		expect(bar.hasAttribute('aria-valuenow')).toBe(false);
		expect(bar.getAttribute('data-tone')).toBe('danger');
		expect(container.querySelector('.progress-indeterminate')?.getAttribute('aria-hidden')).toBe('true');
		expect(bar.textContent).not.toMatch(/\d/);
	});

	it('renders a circular glyph track while preserving observed and unknown ARIA values', async () => {
		const view = render(ProgressTrack, { value: 42, shape: 'circular', label: '원형 진행' });
		const bar = screen.getByRole('progressbar', { name: '원형 진행' });
		expect(bar.getAttribute('aria-valuenow')).toBe('42');
		expect(bar.getAttribute('data-shape')).toBe('circular');
		expect(view.container.querySelector('pre')?.getAttribute('aria-hidden')).toBe('true');
		expect(view.container.querySelector('pre')?.textContent).toContain('42%');
		expect(view.container.querySelector('svg,canvas')).toBeNull();
		await view.rerender({ value: null, shape: 'circular', active: true, label: '원형 진행' });
		expect(bar.hasAttribute('aria-valuenow')).toBe(false);
		expect(view.container.querySelector('pre')?.textContent).not.toMatch(/[0-9%]/);
	});

	it('treats a non-finite value as indeterminate', () => {
		render(ProgressTrack, { value: Number.NaN, label: '빌드' });
		expect(screen.getByRole('progressbar', { name: '빌드' }).hasAttribute('aria-valuenow')).toBe(false);
	});
});


describe('AnimatedNumber', () => {
	it('renders the exact value once when counting cannot be seen', () => {
		const { container } = render(AnimatedNumber, { value: 12.5 });
		expect(container.textContent?.trim()).toBe('12.5');
		expect(container.querySelector('[aria-hidden="true"]')).toBeNull();
	});

	it('counts toward a new value and settles on its exact text', () => {
		const frames: FrameRequestCallback[] = [];
		vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({ matches: false }));
		vi.stubGlobal('requestAnimationFrame', vi.fn((callback: FrameRequestCallback) => frames.push(callback)));
		vi.stubGlobal('cancelAnimationFrame', vi.fn());
		(Element.prototype as Element & { animate: unknown }).animate = vi.fn();
		vi.spyOn(Element.prototype, 'getClientRects').mockReturnValue([{}] as unknown as DOMRectList);
		vi.spyOn(performance, 'now').mockReturnValue(0);

		const { container } = render(AnimatedNumber, { value: 40 });
		flushSync();
		// Mid-count the visible digits are hidden from assistive technology, which reads the target.
		expect(container.querySelector('[aria-hidden="true"]')?.textContent).toBe('0');
		expect(container.querySelector('.sr-only')?.textContent).toBe('40');

		frames.shift()?.(250);
		flushSync();
		const midway = Number(container.querySelector('[aria-hidden="true"]')?.textContent);
		expect(midway).toBeGreaterThan(0);
		expect(midway).toBeLessThan(40);

		frames.shift()?.(1000);
		flushSync();
		expect(container.textContent?.trim()).toBe('40');
		expect(container.querySelector('.sr-only')).toBeNull();
	});

	it('does not count for reduced-motion users', () => {
		vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({ matches: true }));
		(Element.prototype as Element & { animate: unknown }).animate = vi.fn();
		vi.spyOn(Element.prototype, 'getClientRects').mockReturnValue([{}] as unknown as DOMRectList);
		const { container } = render(AnimatedNumber, { value: 7 });
		flushSync();
		expect(container.textContent?.trim()).toBe('7');
	});
});
