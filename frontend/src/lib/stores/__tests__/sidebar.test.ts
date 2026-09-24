// @vitest-environment node
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { get } from 'svelte/store';

describe('sidebarOpen store', () => {
	beforeEach(() => {
		vi.resetModules();
	});

	it('초기 상태는 false (닫힘)', async () => {
		const { sidebarOpen } = await import('../sidebar');
		expect(get(sidebarOpen)).toBe(false);
	});

	it('open() 호출 시 true', async () => {
		const { sidebarOpen } = await import('../sidebar');
		sidebarOpen.open();
		expect(get(sidebarOpen)).toBe(true);
	});

	it('close() 호출 시 false', async () => {
		const { sidebarOpen } = await import('../sidebar');
		sidebarOpen.open();
		sidebarOpen.close();
		expect(get(sidebarOpen)).toBe(false);
	});

	it('toggle() 닫힘 → 열림', async () => {
		const { sidebarOpen } = await import('../sidebar');
		expect(get(sidebarOpen)).toBe(false);
		sidebarOpen.toggle();
		expect(get(sidebarOpen)).toBe(true);
	});

	it('toggle() 열림 → 닫힘', async () => {
		const { sidebarOpen } = await import('../sidebar');
		sidebarOpen.open();
		sidebarOpen.toggle();
		expect(get(sidebarOpen)).toBe(false);
	});

	it('subscribe로 상태 변화 감지', async () => {
		const { sidebarOpen } = await import('../sidebar');
		const states: boolean[] = [];
		const unsub = sidebarOpen.subscribe((v) => states.push(v));
		sidebarOpen.open();
		sidebarOpen.close();
		unsub();
		expect(states).toEqual([false, true, false]);
	});
});
