import { afterEach, describe, expect, it, vi } from 'vitest';
import { clearManualPositions, layoutStorageKey, loadManualPositions, parseManualPositions, saveManualPositions } from '../layoutStorage';

function memoryStorage(): Storage & { store: Record<string, string> } {
	const store: Record<string, string> = {};
	return {
		store,
		getItem: (k: string) => store[k] ?? null,
		setItem: (k: string, v: string) => { store[k] = v; },
		removeItem: (k: string) => { delete store[k]; },
		clear: () => { for (const k of Object.keys(store)) delete store[k]; },
		key: (i: number) => Object.keys(store)[i] ?? null,
		get length() { return Object.keys(store).length; },
	};
}

afterEach(() => {
	vi.unstubAllGlobals();
});

describe('layoutStorageKey', () => {
	it('scope 와 프로젝트별로 키를 만들고 프로젝트가 없으면 all', () => {
		expect(layoutStorageKey('user', 'proj-1')).toBe('topologyCanvas.layout.user.proj-1');
		expect(layoutStorageKey('admin', null)).toBe('topologyCanvas.layout.admin.all');
		expect(layoutStorageKey('admin', '')).toBe('topologyCanvas.layout.admin.all');
	});
});

describe('load/save/clear', () => {
	it('저장한 위치를 그대로 읽고 빈 map 저장은 키를 지운다', () => {
		const s = memoryStorage();
		vi.stubGlobal('localStorage', s);
		const key = layoutStorageKey('user', 'p');
		saveManualPositions(key, { 'vm-1': { x: 10.5, y: -3 }, 'sw:net-a': { x: 0, y: 0 } });
		expect(loadManualPositions(key)).toEqual({ 'vm-1': { x: 10.5, y: -3 }, 'sw:net-a': { x: 0, y: 0 } });
		saveManualPositions(key, {});
		expect(key in s.store).toBe(false);
		saveManualPositions(key, { 'vm-2': { x: 1, y: 2 } });
		clearManualPositions(key);
		expect(loadManualPositions(key)).toEqual({});
	});

	it('깨진 JSON 과 형식이 어긋난 항목은 무시한다', () => {
		const s = memoryStorage();
		vi.stubGlobal('localStorage', s);
		s.store.k1 = '{not json';
		expect(loadManualPositions('k1')).toEqual({});
		s.store.k2 = JSON.stringify([1, 2]);
		expect(loadManualPositions('k2')).toEqual({});
		s.store.k3 = JSON.stringify({ ok: { x: 1, y: 2 }, bad1: { x: '1', y: 2 }, bad2: null, bad3: { x: 1 }, bad4: { x: Infinity, y: 0 } });
		expect(loadManualPositions('k3')).toEqual({ ok: { x: 1, y: 2 } });
		expect(parseManualPositions(null)).toEqual({});
		expect(parseManualPositions('null')).toEqual({});
	});

	it('localStorage 접근이 throw 해도 삼키고 기본값을 돌려준다', () => {
		vi.stubGlobal('localStorage', {
			getItem: () => { throw new Error('blocked'); },
			setItem: () => { throw new Error('quota'); },
			removeItem: () => { throw new Error('blocked'); },
		});
		expect(loadManualPositions('k')).toEqual({});
		expect(() => saveManualPositions('k', { a: { x: 1, y: 1 } })).not.toThrow();
		expect(() => clearManualPositions('k')).not.toThrow();
		vi.stubGlobal('localStorage', undefined);
		expect(loadManualPositions('k')).toEqual({});
		expect(() => saveManualPositions('k', { a: { x: 1, y: 1 } })).not.toThrow();
	});
});
