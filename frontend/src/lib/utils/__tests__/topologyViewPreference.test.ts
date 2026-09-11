import { afterEach, describe, expect, it, vi } from 'vitest';
import { DEFAULT_TOPOLOGY_VIEW, TOPOLOGY_VIEW_STORAGE_KEY, isTopologyView, readTopologyView, writeTopologyView } from '../topologyViewPreference';

afterEach(() => {
	vi.unstubAllGlobals();
	try { localStorage.removeItem(TOPOLOGY_VIEW_STORAGE_KEY); } catch { /* 무시 */ }
});

describe('topologyViewPreference', () => {
	it('기본값은 canvas 이고 저장한 값을 다시 읽는다', () => {
		expect(DEFAULT_TOPOLOGY_VIEW).toBe('canvas');
		expect(readTopologyView()).toBe('canvas');
		writeTopologyView('lane');
		expect(localStorage.getItem('topology.view')).toBe('lane');
		expect(readTopologyView()).toBe('lane');
		writeTopologyView('canvas');
		expect(readTopologyView()).toBe('canvas');
	});

	it('알 수 없는 값은 기본값으로 대체한다', () => {
		localStorage.setItem(TOPOLOGY_VIEW_STORAGE_KEY, 'grid');
		expect(readTopologyView()).toBe('canvas');
		expect(isTopologyView('lane')).toBe(true);
		expect(isTopologyView('grid')).toBe(false);
		expect(isTopologyView(null)).toBe(false);
	});

	it('localStorage 가 없거나 throw 해도 안전하다(SSR)', () => {
		vi.stubGlobal('localStorage', undefined);
		expect(readTopologyView()).toBe('canvas');
		expect(() => writeTopologyView('lane')).not.toThrow();
		vi.stubGlobal('localStorage', { getItem: () => { throw new Error('blocked'); }, setItem: () => { throw new Error('blocked'); } });
		expect(readTopologyView()).toBe('canvas');
		expect(() => writeTopologyView('lane')).not.toThrow();
	});
});
