import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import { tick } from 'svelte';
import { enterConsole, resetConsoleEntry } from '$lib/stores/consoleEntry';
import ConsoleEntryTransition from '../ConsoleEntryTransition.svelte';

describe('ConsoleEntryTransition', () => {
	afterEach(() => {
		resetConsoleEntry();
		delete document.documentElement.dataset.consoleEntry;
	});

	it('renders nothing while idle', () => {
		render(ConsoleEntryTransition);
		expect(screen.queryByTestId('console-entry')).toBeNull();
		expect(document.documentElement.dataset.consoleEntry).toBeUndefined();
	});

	it('states the actual handoff and marks the page for the panel exit', async () => {
		render(ConsoleEntryTransition);
		let finishNavigation!: () => void;
		const pending = enterConsole(() => new Promise<void>((resolve) => { finishNavigation = resolve; }), 'sso');
		await tick();

		const overlay = screen.getByTestId('console-entry');
		expect(overlay.dataset.phase).toBe('entering');
		expect(document.documentElement.dataset.consoleEntry).toBe('entering');
		const status = screen.getByRole('status');
		expect(status.textContent).toContain('콘솔로 들어가고 있어요');
		expect(status.textContent).toContain('SSO 인증 확인됨');
		expect(status.querySelector('li[data-state="active"]')?.textContent).toContain('작업 공간 열기');

		finishNavigation();
		await pending;
		await tick();
		expect(status.textContent).toContain('콘솔이 열렸어요');
		expect(status.querySelector('li[data-state="active"]')).toBeNull();
	});

	it('names the password path and leaves no root marker after the scene', async () => {
		vi.useFakeTimers();
		try {
			render(ConsoleEntryTransition);
			await enterConsole(async () => undefined, 'password');
			await tick();
			expect(screen.getByRole('status').textContent).toContain('로그인 확인됨');
			await vi.advanceTimersByTimeAsync(2000);
			await tick();
			expect(screen.queryByTestId('console-entry')).toBeNull();
			expect(document.documentElement.dataset.consoleEntry).toBeUndefined();
		} finally {
			vi.useRealTimers();
		}
	});
});
