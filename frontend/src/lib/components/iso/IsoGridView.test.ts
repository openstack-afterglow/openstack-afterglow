import { cleanup, fireEvent, render, screen, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import IsoGridView from './IsoGridView.svelte';
import type { IsoScene } from './types';

const scene: IsoScene = {
	platforms: [{ id: 'network', label: 'LAN', tone: 'internal', style: 'slab', x: 0, y: 1, w: 2, h: 2 }],
	nodes: [
		{ id: 'router', kind: 'router', label: 'Edge router', x: 0, y: 0, tone: 'router', status: 'ok' },
		{ id: 'vm', kind: 'instance', label: 'GPU node', x: 1, y: 2, tone: 'internal', platformId: 'network' },
		{ id: 'outside', kind: 'instance', label: 'Outside', x: 2, y: 2, tone: 'internal', interactive: false },
	],
	edges: [{ id: 'route', from: 'router', to: 'network', kind: 'link', tone: 'router', inactive: true, directed: true }],
	legend: [{ label: 'Internal network', kind: 'platform', tone: 'internal' }],
};

let reduce = false;
let motionEvents: EventTarget;
let intersection: IntersectionObserverCallback;

beforeEach(() => {
	reduce = false;
	motionEvents = new EventTarget();
	vi.stubGlobal('matchMedia', () => ({
		get matches() { return reduce; },
		addEventListener: motionEvents.addEventListener.bind(motionEvents),
		removeEventListener: motionEvents.removeEventListener.bind(motionEvents),
	}));
	vi.stubGlobal('IntersectionObserver', class {
		constructor(callback: IntersectionObserverCallback) { intersection = callback; }
		observe() { this.emit(true); }
		disconnect() { /* No resources retained. */ }
		emit(isIntersecting: boolean) { intersection([{ isIntersecting } as IntersectionObserverEntry], this as unknown as IntersectionObserver); }
	});
	vi.spyOn(document, 'hidden', 'get').mockReturnValue(false);
	vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockReturnValue(900);
	vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockReturnValue(580);
});

afterEach(() => {
	cleanup();
	vi.restoreAllMocks();
	vi.unstubAllGlobals();
});

describe('IsoGridView', () => {
	it('exposes native selection buttons in reading order and clears with Escape', async () => {
		const onselect = vi.fn(), onclear = vi.fn();
		render(IsoGridView, { scene, label: 'Diagram', onselect, onclear });
		const canvas = screen.getByRole('group', { name: 'Diagram' });
		const targets = within(canvas).getAllByRole('button');
		expect(targets.map((button) => button.getAttribute('aria-label'))).toEqual(['Edge router, 정상', 'GPU node', 'LAN']);
		expect(targets.every((button) => button instanceof HTMLButtonElement && button.tabIndex === 0)).toBe(true);
		targets[0].focus();
		// jsdom does not synthesize the native Enter/Space click; browsers dispatch detail=0.
		await fireEvent.click(document.activeElement!, { detail: 0 });
		expect(onselect).toHaveBeenCalledWith('router');
		await fireEvent.keyDown(document.activeElement!, { key: 'Escape' });
		expect(onclear).toHaveBeenCalledOnce();
	});

	it('highlights slab membership and keeps unrelated resources subdued', async () => {
		const { container, rerender } = render(IsoGridView, { scene, label: 'Diagram', selectedId: 'network' });
		expect(container.querySelectorAll('g.block.dimmed')).toHaveLength(1);
		expect(container.querySelector('g.edge.active')).not.toBeNull();
		await rerender({ selectedId: 'vm' });
		expect(container.querySelector('g.active > polygon.surface')).not.toBeNull();
	});

	it('animates configured paths even when inactive, but pauses for motion preferences or offscreen', async () => {
		const { container } = render(IsoGridView, { scene, label: 'Diagram' });
		await tick();
		expect(container.querySelector('.edge.inactive .route.dashed')).not.toBeNull();
		expect(container.querySelectorAll('.packet')).toHaveLength(1);
		reduce = true;
		motionEvents.dispatchEvent(new Event('change'));
		await tick();
		expect(container.querySelector('.packet')).toBeNull();
		reduce = false;
		motionEvents.dispatchEvent(new Event('change'));
		intersection([{ isIntersecting: false } as IntersectionObserverEntry], {} as IntersectionObserver);
		await tick();
		expect(container.querySelector('.packet')).toBeNull();
		intersection([{ isIntersecting: true } as IntersectionObserverEntry], {} as IntersectionObserver);
		await tick();
		expect(container.querySelectorAll('.packet')).toHaveLength(1);
	});

	it('stops animation when hidden or manually paused; keeps the path visible', async () => {
		const { container } = render(IsoGridView, { scene, label: 'Diagram' });
		await tick();
		await fireEvent.click(screen.getByRole('button', { name: '경로 애니메이션 일시 정지' }));
		expect(container.querySelector('.packet')).toBeNull();
		expect(container.querySelector('.route')).not.toBeNull();
		await fireEvent.click(screen.getByRole('button', { name: '경로 애니메이션 재생' }));
		expect(container.querySelector('.packet')).not.toBeNull();
		vi.spyOn(document, 'hidden', 'get').mockReturnValue(true);
		document.dispatchEvent(new Event('visibilitychange'));
		await tick();
		expect(container.querySelector('.packet')).toBeNull();
	});

	it('keeps user zoom across scene refreshes and refits when the fit key changes', async () => {
		const { container, rerender } = render(IsoGridView, { scene, label: 'Diagram', fitKey: 'first' });
		await tick();
		const fit = container.querySelector('output')!.textContent;
		await fireEvent.click(screen.getByRole('button', { name: '확대' }));
		const zoom = container.querySelector('output')!.textContent;
		expect(zoom).not.toBe(fit);
		const nextScene = { ...scene, nodes: scene.nodes.map((node) => ({ ...node, x: node.x * 5 })) };
		await rerender({ scene: nextScene });
		expect(container.querySelector('output')!.textContent).toBe(zoom);
		await rerender({ fitKey: 'second' });
		expect(container.querySelector('output')!.textContent).not.toBe(zoom);
	});

	it('labels the legend and lists configured paths even when motion is reduced', () => {
		reduce = true;
		render(IsoGridView, { scene, label: 'Diagram' });
		const figure = screen.getByRole('figure', { name: 'Diagram' });
		expect(within(figure).getByText('움직이는 점은 설정된 경로를 나타냅니다. 실시간 트래픽이나 연결 가능 여부가 아닙니다.').closest('figcaption')).not.toBeNull();
		const edges = within(figure).getByRole('list', { name: '설정된 경로' });
		expect(edges.textContent).toContain('Edge router에서 LAN(으)로 이어지는 설정 경로 · 비활성');
	});

	it('renders a supplied empty state without hidden targets or controls', () => {
		render(IsoGridView, { scene: { nodes: [], edges: [], platforms: [] }, label: 'Diagram', emptyText: 'No network resources' });
		expect(screen.getByText('No network resources')).not.toBeNull();
		expect(screen.queryByRole('button')).toBeNull();
	});
});
