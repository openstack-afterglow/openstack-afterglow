import { render } from '@testing-library/svelte';
import { tick } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import RowMotionList from './__tests__/RowMotionList.svelte';
import { ROW_MOTION_BATCH_LIMIT, rowChanged, rowEnter, rowExit, rowSignature } from './rowMotion';

const original = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'animate');

beforeEach(() => {
	vi.useFakeTimers();
});

afterEach(() => {
	vi.useRealTimers();
	vi.unstubAllGlobals();
	if (original) Object.defineProperty(HTMLElement.prototype, 'animate', original);
	else Reflect.deleteProperty(HTMLElement.prototype, 'animate');
});

function stubAnimations() {
	const animate = vi.fn(() => ({ cancel: vi.fn(), finish: vi.fn(), onfinish: null, currentTime: 0, finished: Promise.resolve() }));
	Object.defineProperty(HTMLElement.prototype, 'animate', { configurable: true, writable: true, value: animate });
	vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({ matches: false }));
	return animate;
}

const named = (id: string, size = 10) => ({ id, name: `name-${id}`, size });
const a = named('a');
const b = named('b', 20);
const c = named('c', 30);

/** Every Web Animation started; tests using it replace whole pages so no change flash is expected. */
function transitionCalls(animate: ReturnType<typeof stubAnimations>) {
	return animate.mock.calls.length;
}

async function settle() {
	await tick();
	// Runs the helper's batch-reset timer deterministically.
	vi.runOnlyPendingTimers();
}

describe('keyed row refresh', () => {
	it('keeps unchanged rows and flashes only the row whose data changed', async () => {
		const animate = stubAnimations();
		const view = render(RowMotionList, { rows: [a, b, c] });
		const before = new Map([...view.container.querySelectorAll('tr')].map(row => [row.dataset.id, row]));
		// A refresh returns new objects for every row; only b differs by value.
		await view.rerender({ rows: [{ ...a }, { ...b, size: 21 }, { ...c }] });
		const after = [...view.container.querySelectorAll('tr')];
		expect(after.map(row => row.dataset.id)).toEqual(['a', 'b', 'c']);
		for (const row of after) expect(row).toBe(before.get(row.dataset.id));
		const flashed = animate.mock.contexts.filter(context => context instanceof HTMLTableRowElement);
		expect(flashed).toEqual([before.get('b')]);
		expect(before.get('b')!.textContent).toContain('21');
	});

	it('does not flash when a refresh returns equal data', async () => {
		const animate = stubAnimations();
		const view = render(RowMotionList, { rows: [a, b] });
		await view.rerender({ rows: [{ ...a }, { ...b }] });
		expect(animate).not.toHaveBeenCalled();
	});

	it('adds a new row without recreating existing rows and fades it in', async () => {
		const animate = stubAnimations();
		const view = render(RowMotionList, { rows: [a, b] });
		const first = view.container.querySelector('tr[data-id="a"]');
		await view.rerender({ rows: [a, b, c] });
		await settle();
		expect(view.container.querySelector('tr[data-id="a"]')).toBe(first);
		expect(view.container.querySelectorAll('tr')).toHaveLength(3);
		expect(animate.mock.contexts.some(context => context instanceof HTMLTableRowElement && context.dataset.id === 'c')).toBe(true);
	});

	it('removes a row and plays one exit for it only', async () => {
		const animate = stubAnimations();
		const view = render(RowMotionList, { rows: [a, b, c] });
		const gone = view.container.querySelector('tr[data-id="b"]');
		await view.rerender({ rows: [a, c] });
		await settle();
		expect(animate.mock.contexts.filter(context => context === gone)).toHaveLength(1);
	});

	it('plays no row motion when a page turn replaces every row', async () => {
		const animate = stubAnimations();
		const page = (prefix: string) => Array.from({ length: ROW_MOTION_BATCH_LIMIT + 4 }, (_, index) => named(`${prefix}${index}`));
		const view = render(RowMotionList, { rows: page('x') });
		await view.rerender({ rows: page('y') });
		await settle();
		expect(transitionCalls(animate)).toBe(0);
		// Outgoing rows are gone at once instead of lingering beside the incoming page.
		expect(view.container.querySelectorAll('tr')).toHaveLength(ROW_MOTION_BATCH_LIMIT + 4);
		expect([...view.container.querySelectorAll('tr')].every(row => row.dataset.id?.startsWith('y'))).toBe(true);
	});
});

describe('row motion helpers', () => {
	it('are instant without Web Animations or under reduced motion', () => {
		const node = document.createElement('tr');
		Object.defineProperty(node, 'animate', { value: undefined, configurable: true });
		expect(rowEnter(node)().duration).toBe(0);
		expect(rowExit(node)().duration).toBe(0);
		vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({ matches: true }));
		Object.defineProperty(node, 'animate', { value: vi.fn(), configurable: true });
		expect(rowEnter(node)().duration).toBe(0);
	});

	it('animate when Web Animations are available', async () => {
		await settle();
		const node = document.createElement('tr');
		Object.defineProperty(node, 'animate', { value: vi.fn(), configurable: true });
		vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({ matches: false }));
		expect(rowEnter(node)().duration).toBeGreaterThan(0);
		expect(rowExit(node)().duration).toBeGreaterThan(0);
	});

	it('compares rows by value', () => {
		expect(rowSignature({ id: 'a', size: 1 })).toBe(rowSignature({ id: 'a', size: 1 }));
		expect(rowSignature({ id: 'a', size: 1 })).not.toBe(rowSignature({ id: 'a', size: 2 }));
		const node = document.createElement('tr');
		const animate = vi.fn();
		Object.defineProperty(node, 'animate', { value: animate, configurable: true });
		vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({ matches: false }));
		const action = rowChanged(node, { id: 'a', size: 1 });
		action.update({ id: 'a', size: 1 });
		expect(animate).not.toHaveBeenCalled();
		action.update({ id: 'a', size: 2 });
		expect(animate).toHaveBeenCalledTimes(1);
	});
});
