import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import { get } from 'svelte/store';

vi.mock('$app/environment', () => ({ browser: true }));

const storage: Record<string, string> = {};
vi.stubGlobal('localStorage', {
	getItem: (key: string) => storage[key] ?? null,
	setItem: (key: string, val: string) => {
		storage[key] = val;
	},
	removeItem: (key: string) => {
		delete storage[key];
	},
});

function makeMql(matches: boolean) {
	return {
		matches,
		addEventListener: vi.fn(),
		removeEventListener: vi.fn(),
	};
}

describe('theme store', () => {
	let mockMatchMedia: ReturnType<typeof vi.fn>;

	beforeEach(() => {
		Object.keys(storage).forEach((k) => delete storage[k]);

		mockMatchMedia = vi.fn().mockReturnValue(makeMql(false));
		Object.defineProperty(globalThis, 'matchMedia', {
			writable: true,
			configurable: true,
			value: mockMatchMedia,
		});

		vi.resetModules();
	});

	afterEach(() => {
		vi.restoreAllMocks();
	});

	it('localStorage에 값이 없으면 초기값은 "system"', async () => {
		const { theme } = await import('../theme');
		expect(get(theme)).toBe('system');
	});

	it('localStorage에 저장된 테마로 초기화', async () => {
		storage['afterglow_theme'] = 'dark';
		const { theme } = await import('../theme');
		expect(get(theme)).toBe('dark');
	});

	it('theme.set("dark") 후 localStorage에 저장', async () => {
		const { theme } = await import('../theme');
		theme.set('dark');
		expect(get(theme)).toBe('dark');
		expect(storage['afterglow_theme']).toBe('dark');
	});

	it('theme.set("light") 후 localStorage에 저장', async () => {
		const { theme } = await import('../theme');
		theme.set('light');
		expect(get(theme)).toBe('light');
		expect(storage['afterglow_theme']).toBe('light');
	});

	it('toggle() system → dark → light → system 순환', async () => {
		const { theme } = await import('../theme');
		expect(get(theme)).toBe('system');
		theme.toggle();
		expect(get(theme)).toBe('dark');
		theme.toggle();
		expect(get(theme)).toBe('light');
		theme.toggle();
		expect(get(theme)).toBe('system');
	});

	it('toggle() localStorage에 새 값 저장', async () => {
		const { theme } = await import('../theme');
		theme.toggle();
		expect(storage['afterglow_theme']).toBe('dark');
	});
});

describe('resolvedTheme', () => {
	beforeEach(() => {
		Object.keys(storage).forEach((k) => delete storage[k]);
		vi.resetModules();
	});

	it('theme="dark" → resolvedTheme="dark"', async () => {
		Object.defineProperty(globalThis, 'matchMedia', {
			writable: true,
			configurable: true,
			value: vi.fn().mockReturnValue(makeMql(false)),
		});
		const { theme, resolvedTheme } = await import('../theme');
		theme.set('dark');
		expect(get(resolvedTheme)).toBe('dark');
	});

	it('theme="light" → resolvedTheme="light"', async () => {
		Object.defineProperty(globalThis, 'matchMedia', {
			writable: true,
			configurable: true,
			value: vi.fn().mockReturnValue(makeMql(true)),
		});
		const { theme, resolvedTheme } = await import('../theme');
		theme.set('light');
		expect(get(resolvedTheme)).toBe('light');
	});

	it('theme="system" + systemPrefersDark=false → resolvedTheme="light"', async () => {
		Object.defineProperty(globalThis, 'matchMedia', {
			writable: true,
			configurable: true,
			value: vi.fn().mockReturnValue(makeMql(false)),
		});
		const { theme, resolvedTheme } = await import('../theme');
		theme.set('system');
		expect(get(resolvedTheme)).toBe('light');
	});

	it('theme="system" + systemPrefersDark=true → resolvedTheme="dark"', async () => {
		Object.defineProperty(globalThis, 'matchMedia', {
			writable: true,
			configurable: true,
			value: vi.fn().mockReturnValue(makeMql(true)),
		});
		const { theme, resolvedTheme } = await import('../theme');
		theme.set('system');
		expect(get(resolvedTheme)).toBe('dark');
	});

	it('matchMedia change 이벤트로 resolvedTheme 업데이트', async () => {
		let changeHandler: ((e: { matches: boolean }) => void) | null = null;
		const mql = {
			matches: false,
			addEventListener: vi.fn((event: string, handler: (e: { matches: boolean }) => void) => {
				if (event === 'change') changeHandler = handler;
			}),
			removeEventListener: vi.fn(),
		};
		Object.defineProperty(globalThis, 'matchMedia', {
			writable: true,
			configurable: true,
			value: vi.fn().mockReturnValue(mql),
		});

		const { theme, resolvedTheme } = await import('../theme');
		theme.set('system');
		expect(get(resolvedTheme)).toBe('light');

		// 시스템 다크모드 변경 이벤트 시뮬레이션
		(changeHandler as ((event: { matches: boolean }) => void) | null)?.({ matches: true });
		expect(get(resolvedTheme)).toBe('dark');
	});
});
