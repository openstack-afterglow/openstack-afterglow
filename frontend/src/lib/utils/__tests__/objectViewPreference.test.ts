import { afterEach, describe, expect, it, vi } from 'vitest';
import { DEFAULT_OBJECT_VIEW, OBJECT_VIEW_STORAGE_KEY, isObjectView, readObjectView, writeObjectView } from '../objectViewPreference';

afterEach(() => {
	vi.unstubAllGlobals();
	try { localStorage.removeItem(OBJECT_VIEW_STORAGE_KEY); } catch { /* 무시 */ }
});

describe('objectViewPreference', () => {
	it('기본값은 grid 이고 저장한 값을 다시 읽는다', () => {
		expect(DEFAULT_OBJECT_VIEW).toBe('grid');
		expect(readObjectView()).toBe('grid');
		writeObjectView('list');
		expect(localStorage.getItem('objectBrowser.view')).toBe('list');
		expect(readObjectView()).toBe('list');
		writeObjectView('grid');
		expect(readObjectView()).toBe('grid');
	});

	it('알 수 없는 값은 기본값으로 대체한다', () => {
		localStorage.setItem(OBJECT_VIEW_STORAGE_KEY, 'canvas');
		expect(readObjectView()).toBe('grid');
		expect(isObjectView('list')).toBe(true);
		expect(isObjectView('canvas')).toBe(false);
		expect(isObjectView(null)).toBe(false);
	});

	it('localStorage 가 없거나 throw 해도 안전하다(SSR)', () => {
		vi.stubGlobal('localStorage', undefined);
		expect(readObjectView()).toBe('grid');
		expect(() => writeObjectView('list')).not.toThrow();
		vi.stubGlobal('localStorage', { getItem: () => { throw new Error('blocked'); }, setItem: () => { throw new Error('blocked'); } });
		expect(readObjectView()).toBe('grid');
		expect(() => writeObjectView('list')).not.toThrow();
	});
});
