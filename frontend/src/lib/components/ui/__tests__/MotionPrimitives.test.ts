import { flushSync } from 'svelte';
import { render, screen } from '@testing-library/svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';
import ActivityIndicator from '../ActivityIndicator.svelte';
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
		expect((container.querySelector('.progress-fill') as HTMLElement).style.transform).toBe('scaleX(1)');
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

	it('treats a non-finite value as indeterminate', () => {
		render(ProgressTrack, { value: Number.NaN, label: '빌드' });
		expect(screen.getByRole('progressbar', { name: '빌드' }).hasAttribute('aria-valuenow')).toBe(false);
	});
});

describe('ActivityIndicator', () => {
	it('announces its visible label as a status', () => {
		render(ActivityIndicator, { variant: 'orbit', label: '응답을 생성하는 중' });
		expect(screen.getByRole('status').textContent).toContain('응답을 생성하는 중');
	});

	it('stays silent and decorative when adjacent text names the activity', () => {
		const { container } = render(ActivityIndicator, { variant: 'spinner' });
		expect(screen.queryByRole('status')).toBeNull();
		expect(container.querySelector('.glyph')?.getAttribute('aria-hidden')).toBe('true');
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
