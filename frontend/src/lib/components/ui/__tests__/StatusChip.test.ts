import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/svelte';
import StatusChip from '../StatusChip.svelte';
import { settledSignal } from '$lib/design/characterFormats.js';

describe('StatusChip', () => {
	it('preserves arbitrary authority scope identifiers without calling them unknown states', () => {
		const view = render(StatusChip, { status: 'models:read' });
		expect(view.getByText('models:read')).toBeTruthy();
	});

	it('does not turn available backup or snapshot resources into attachable volumes', () => {
		const view = render(StatusChip, { status: 'available' });
		expect(view.container.querySelector('.chip-success')).toBeTruthy();
	});
	it('retains unknown native status codes without presenting them as healthy', () => {
		const { container } = render(StatusChip, { status: 'FUTURE_NATIVE_STATE' });
		expect(container.querySelector('[title="FUTURE_NATIVE_STATE"]')?.textContent).toContain('FUTURE_NATIVE_STATE');
		expect(container.querySelector('.chip-neutral')).toBeTruthy();
	});

	it('distinguishes attachable storage from attached storage', () => {
		const available = render(StatusChip, { status: 'available', kind: 'volume' });
		expect(available.container.querySelector('.chip-neutral')).toBeTruthy();
		available.unmount();
		const attached = render(StatusChip, { status: 'in-use', kind: 'volume' });
		expect(attached.container.querySelector('.chip-info')).toBeTruthy();
	});

	it.each([null, undefined, ''])('announces unavailable status %s rather than an empty decorative dash', (status) => {
		const { container } = render(StatusChip, { status });
		expect(container.textContent?.trim()).not.toBe('');
		expect(container.querySelector('.chip-neutral')).toBeTruthy();
	});

	it('maps ACTIVE to success tone', () => {
		const { container } = render(StatusChip, { status: 'ACTIVE' });
		expect(container.querySelector('.chip-success')).toBeTruthy();
	});


	it('maps ERROR to danger tone', () => {
		const { container } = render(StatusChip, { status: 'ERROR' });
		expect(container.querySelector('.chip-danger')).toBeTruthy();
	});

	it('maps unknown statuses to neutral tone', () => {
		const { container } = render(StatusChip, { status: 'mystery' });
		expect(container.querySelector('.chip-neutral')).toBeTruthy();
	});

	it('shows a rotating glyph only while a resource is transitioning, never a settled outcome mark', () => {
		const settledMarks = (['success', 'failed', 'blocked', 'canceled'] as const).map(settledSignal);
		const building = render(StatusChip, { status: 'BUILD' });
		const glyph = building.container.querySelector('[data-art]')!;
		expect(glyph.getAttribute('aria-hidden')).toBe('true');
		expect(settledMarks).not.toContain(glyph.getAttribute('data-art'));
		building.unmount();
		expect(render(StatusChip, { status: 'ACTIVE' }).container.querySelector('[data-art]')?.getAttribute('data-art')).toBe(settledSignal('success'));
		expect(render(StatusChip, { status: 'ERROR' }).container.querySelector('[data-art]')?.getAttribute('data-art')).toBe(settledSignal('failed'));
	});

	it.each(['observed', 'FUTURE_NATIVE_STATE', null, 'SHUTOFF', 'manage'])('does not mark %s as a finished outcome', (status) => {
		const outcomes = (['success', 'failed', 'blocked', 'canceled'] as const).map(settledSignal);
		const art = render(StatusChip, { status }).container.querySelector('[data-art]')?.getAttribute('data-art');
		expect(outcomes).not.toContain(art);
	});

	it('marks an explicitly canceled job as canceled', () => {
		expect(render(StatusChip, { status: 'canceled' }).container.querySelector('[data-art]')?.getAttribute('data-art')).toBe(settledSignal('canceled'));
	});

	it('keeps the shared character clock idle while every chip is settled', () => {
		vi.useFakeTimers();
		vi.stubGlobal('matchMedia', () => ({ matches: false, addEventListener() {}, removeEventListener() {} }));
		try {
			const settled = render(StatusChip, { status: 'ACTIVE' });
			expect(vi.getTimerCount()).toBe(0);
			const building = render(StatusChip, { status: 'BUILD' });
			expect(vi.getTimerCount()).toBe(1);
			building.unmount();
			expect(vi.getTimerCount()).toBe(0);
			settled.unmount();
		} finally {
			vi.useRealTimers();
			vi.unstubAllGlobals();
		}
	});
});
