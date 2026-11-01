import { cleanup, fireEvent, render, screen, within } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { initLocale } from '$lib/i18n/runtime.svelte';
import { t } from '$lib/i18n/ns/vm-wizard';
import VmResourcePreparation from '../VmResourcePreparation.svelte';
import { afterglowGeometry } from '$lib/components/ui/afterglowLoadingScene';

type Task = { id: string; label: string; status: 'pending' | 'complete' | 'failed' };
const tasks: Task[] = [
	{ id: 'resources', label: 'CPU / memory', status: 'pending' },
	{ id: 'gpu', label: 'GPU availability', status: 'pending' },
	{ id: 'history', label: 'Saved specifications', status: 'pending' },
];

beforeEach(() => {
	initLocale('ko'); vi.useFakeTimers();
	vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null);
	vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({ width: 784, height: 724 } as DOMRect);
});
afterEach(() => { cleanup(); vi.useRealTimers(); vi.restoreAllMocks(); });

describe('VM resource preparation presentation', () => {
	it('announces only an actual pending task and advances on settled state, never a timer', async () => {
		const view = render(VmResourcePreparation, { tasks, error: false, retrying: false, onRetry: vi.fn() });
		const status = screen.getByRole('status');
		expect(status.textContent).toContain('CPU / memory');
		expect(status.getAttribute('aria-live')).toBe('polite');
		expect(status.getAttribute('aria-atomic')).toBe('true');
		expect(screen.queryByRole('progressbar')).toBeNull();
		const geometry = afterglowGeometry(784, 724);
		expect(status.style.getPropertyValue('--orbit-center-x')).toBe(`${geometry.centerX}px`);
		expect(status.style.getPropertyValue('--orbit-center-y')).toBe(`${geometry.centerY}px`);
		expect(status.style.getPropertyValue('--orbit-radius')).toBe(`${geometry.radius}px`);
		expect(view.container.querySelector('.afterglow-orbit')?.getAttribute('data-renderer')).toBe('fallback');
		expect(view.container.querySelector('.af-loader')).toBeNull();
		await vi.advanceTimersByTimeAsync(30_000);
		expect(status.textContent).toContain('CPU / memory');
		await view.rerender({ tasks: tasks.map<Task>(task => ({ ...task, status: task.id === 'history' ? 'pending' : 'complete' })) });
		expect(status.textContent).toContain('Saved specifications');
		expect(status.textContent).not.toContain('CPU / memory');
		expect(view.container.querySelector('[data-preparation-task="gpu"]')?.getAttribute('data-state')).toBe('complete');
		expect(view.container.querySelector('.afterglow-orbit')?.getAttribute('aria-hidden')).toBe('true');
	});

	it('retains accessible failure details and the explicit retry without replaying anything', async () => {
		const retry = vi.fn();
		const view = render(VmResourcePreparation, {
			tasks: tasks.map<Task>(task => ({ ...task, status: task.id === 'history' ? 'failed' : 'complete' })),
			error: true, retrying: false, onRetry: retry,
		});
		expect(view.container.querySelector('[data-preparation-lanes]')?.getAttribute('aria-busy')).toBe('false');
		expect(screen.getByRole('status').textContent).toContain(t('preparation.failed'));
		expect(within(screen.getByRole('alert')).getByText(/Saved specifications/)).toBeTruthy();
		expect(view.container.querySelector('.afterglow-orbit')?.getAttribute('data-running')).toBe('false');
		expect(retry).not.toHaveBeenCalled();
		await fireEvent.click(screen.getByRole('button', { name: t('preparation.retry') }));
		expect(retry).toHaveBeenCalledOnce();
		await view.rerender({ retrying: true });
		expect(screen.getByRole<HTMLButtonElement>('button').disabled).toBe(true);
	});

	it('announces failed and pending work without a busy ancestor deferring either live region', () => {
		const view = render(VmResourcePreparation, {
			tasks: tasks.map<Task>(task => ({ ...task, status: task.id === 'resources' ? 'failed' : 'pending' })),
			error: true, retrying: true, onRetry: vi.fn(),
		});
		expect(view.container.querySelector('[data-preparation-lanes]')?.getAttribute('aria-busy')).toBe('true');
		const status = screen.getByRole('status');
		const alert = screen.getByRole('alert');
		expect(status.textContent).toContain('GPU availability');
		expect(alert.textContent).toContain('CPU / memory');
		const details = screen.getByRole('region', { name: t('preparation.failed') });
		expect(details.getAttribute('tabindex')).toBe('0');
		expect(within(details).getByRole<HTMLButtonElement>('button').disabled).toBe(true);
		details.focus();
		expect(document.activeElement).toBe(details);
		for (const live of [status, alert]) expect(live.closest('[aria-busy="true"]')).toBeNull();
	});
});
