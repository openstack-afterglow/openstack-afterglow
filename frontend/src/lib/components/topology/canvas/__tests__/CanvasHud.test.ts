import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, waitFor } from '@testing-library/svelte';
import CanvasHud, { type HudLabelItem } from '../CanvasHud.svelte';
import type { Rect } from '../types';

const labels: HudLabelItem[] = [
	{ netId: 'public', name: 'public_provider', cidrText: '203.0.113.0/24', kindLabel: '외부', isolated: false, statusText: null, adminPills: ['MTU 1500'], color: 'var(--color-topology-external)', sx: 40, sy: 100, avail: 160, active: false, dim: false },
	{ netId: 'shared', name: 'drover-ci-net-long-network-name', cidrText: '2001:db8:1234:5678::/64', kindLabel: '공유', isolated: false, statusText: null, adminPills: [], color: 'var(--color-topology-shared)', sx: 40, sy: 100, avail: 160, active: false, dim: false },
];

function renderedRects(container: HTMLElement, w: number, h: number): Rect[] {
	return [...container.querySelectorAll<HTMLElement>('[data-zone-label]')].map((el) => ({ x: parseFloat(el.style.getPropertyValue('--sx')), y: parseFloat(el.style.getPropertyValue('--sy')), w, h }));
}
function expectNoOverlap(rects: readonly Rect[]) {
	for (let i = 0; i < rects.length; i++) for (const b of rects.slice(i + 1)) {
		const a = rects[i];
		expect(a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h).toBe(false);
	}
}

afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

describe('CanvasHud measured collision layout', () => {
	it('uses actual chip dimensions, protects name/address cards and keeps selectors and CIDR text', async () => {
		vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(() => ({ x: 0, y: 0, width: 280, height: 44, top: 0, left: 0, right: 280, bottom: 44, toJSON() {} }));
		const onselectnet = vi.fn();
		const card = { x: 20, y: 80, w: 310, h: 100 };
		const { container } = render(CanvasHud, { props: { labels, badges: [], badgesHidden: false, obstacles: [card], viewportWidth: 768, viewportHeight: 500, onselectnet } });
		await waitFor(() => expectNoOverlap([...renderedRects(container, 280, 44), card]));
		expect(container.querySelectorAll('[data-zone-label]')).toHaveLength(2);
		for (const label of labels) {
			const button = container.querySelector<HTMLButtonElement>(`[data-zone-label="${label.netId}"]`)!;
			expect(button.textContent).toContain(label.name);
			expect(button.textContent).toContain(label.cidrText);
			expect(button.title).toContain(label.cidrText);
			await fireEvent.click(button);
			expect(onselectnet).toHaveBeenLastCalledWith(label.netId);
		}
		expect(container.querySelector('.hud-leaders path')).not.toBeNull();
	});

	it('re-measures wrapped/font-changed text through ResizeObserver and disconnects on unmount', async () => {
		let height = 24;
		let callback: ResizeObserverCallback = () => {};
		const disconnect = vi.fn();
		vi.stubGlobal('ResizeObserver', class {
			constructor(cb: ResizeObserverCallback) { callback = cb; }
			observe() {}
			unobserve() {}
			disconnect = disconnect;
		});
		vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(() => ({ x: 0, y: 0, width: 280, height, top: 0, left: 0, right: 280, bottom: height, toJSON() {} }));
		const { container, unmount, rerender } = render(CanvasHud, { props: { labels, badges: [], badgesHidden: false, viewportWidth: 320, viewportHeight: 600, onselectnet: vi.fn() } });
		await waitFor(() => expectNoOverlap(renderedRects(container, 280, 24)));
		height = 76;
		callback([...container.querySelectorAll('[data-zone-label]')].map((target) => ({ target } as ResizeObserverEntry)), {} as ResizeObserver);
		await waitFor(() => expectNoOverlap(renderedRects(container, 280, height)));
		await rerender({ labels: labels.slice(0, 1), badges: [], badgesHidden: false, viewportWidth: 390, viewportHeight: 600, onselectnet: vi.fn() });
		expect(container.querySelectorAll('[data-zone-label]')).toHaveLength(1);
		unmount();
		expect(disconnect).toHaveBeenCalledOnce();
	});
});
