import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MOTION_DURATION_MS } from '$lib/design/tokens';
import LandingOpsBoard from '../LandingOpsBoard.svelte';

const delay = MOTION_DURATION_MS.statusPulse + MOTION_DURATION_MS.data;
const panelKeys = ['request', 'policy', 'resource', 'reuse'];
let hidden = false;
let preference: EventTarget & { matches: boolean };
let observer: ViewObserver;

class ViewObserver {
	private target!: Element;
	readonly disconnect = vi.fn();
	constructor(private callback: IntersectionObserverCallback) {
		observer = this;
	}
	observe(target: Element) { this.target = target; }
	setVisible(isIntersecting: boolean) {
		this.callback([{ target: this.target, isIntersecting } as IntersectionObserverEntry], this as unknown as IntersectionObserver);
	}
}

async function advance(ms: number = delay) {
	await act(async () => {
		await vi.advanceTimersByTimeAsync(ms);
		await tick();
	});
}

async function motion(reduce: boolean) {
	await act(async () => {
		preference.matches = reduce;
		preference.dispatchEvent(new Event('change'));
		await tick();
	});
}

function progress() {
	return (screen.getByRole('progressbar') as HTMLProgressElement).value;
}

function currentStep() {
	return screen.getAllByRole('listitem').find((item) => item.getAttribute('aria-current') === 'step');
}

function panel(key: string) {
	const element = document.querySelector<HTMLElement>(`[data-panel="${key}"]`);
	if (!element) throw new Error(`missing ${key} panel`);
	return element;
}

function panelStates() {
	return panelKeys.map((key) => panel(key).dataset.state);
}

function reuseResult() {
	return panel('reuse').querySelector('[data-result]')?.getAttribute('data-result');
}

function stepStates(step: number) {
	return panelKeys.map((_, index) => (index < step ? 'done' : index === step ? 'active' : 'waiting'));
}

async function start() {
	await fireEvent.click(screen.getByRole('button', { name: '환경 구성 체험' }));
}

beforeEach(() => {
	vi.useFakeTimers();
	hidden = false;
	vi.spyOn(document, 'hidden', 'get').mockImplementation(() => hidden);
	preference = Object.assign(new EventTarget(), { matches: false });
	vi.stubGlobal('matchMedia', vi.fn(() => preference));
	vi.stubGlobal('IntersectionObserver', ViewObserver);
});

afterEach(() => {
	cleanup();
	vi.clearAllTimers();
	vi.useRealTimers();
	vi.restoreAllMocks();
	vi.unstubAllGlobals();
});

describe('LandingOpsBoard local preview', () => {
	it('waits for explicit start, visits all four stages and ends with a replayable result without requests', async () => {
		const fetch = vi.fn();
		vi.stubGlobal('fetch', fetch);
		render(LandingOpsBoard);
		expect(screen.getByRole('button', { name: 'GPU 연구' }).getAttribute('aria-pressed')).toBe('true');
		await advance(delay * 8);
		expect(progress()).toBe(0);
		expect(currentStep()).toBeUndefined();
		expect(panel('reuse').dataset.state).toBe('waiting');

		await start();
		for (const [index, name] of ['신청', '정책 확인', '자원 배정', '재사용 결과'].entries()) {
			expect(progress()).toBe(index);
			expect(currentStep()?.textContent).toContain(name);
			await advance();
		}
		expect(progress()).toBe(4);
		expect(currentStep()).toBeUndefined();
		expect(panel('reuse').dataset.state).toBe('done');
		expect(reuseResult()).toBe('pytorch-vision-lab');
		await advance(delay * 8);
		expect(progress()).toBe(4);
		const completedScene = document.querySelector('.scene');
		await fireEvent.click(screen.getByRole('button', { name: '다시 체험' }));
		expect(document.querySelector('.scene')).not.toBe(completedScene);
		expect(progress()).toBe(0);
		expect(currentStep()?.textContent).toContain('신청');
		expect(panel('reuse').dataset.state).toBe('waiting');
		await advance(delay * 4);
		expect(progress()).toBe(4);
		expect(fetch).not.toHaveBeenCalled();
	});

	it('treats every activation as a toggle so a double activation ends paused without leftover work', async () => {
		render(LandingOpsBoard);
		await start();
		const pausedObserver = observer;
		await advance();
		await fireEvent.click(screen.getByRole('button', { name: '일시정지' }));
		const control = screen.getByRole('button', { name: '계속하기' });
		await act(async () => {
			await fireEvent.click(control, { detail: 1 });
			await fireEvent.click(control, { detail: 2 });
			await tick();
		});
		expect(control.textContent).toContain('계속하기');
		expect(progress()).toBe(1);
		expect(currentStep()?.textContent).toContain('정책 확인');
		expect(vi.getTimerCount()).toBe(0);
		await act(async () => {
			pausedObserver.setVisible(false);
			await tick();
		});
		await advance(delay * 5);
		expect(progress()).toBe(1);
		expect(control.textContent).toContain('계속하기');

		await fireEvent.click(control);
		expect(control.textContent).toContain('일시정지');
		expect(vi.getTimerCount()).toBe(1);
		await act(async () => {
			pausedObserver.setVisible(false);
			await tick();
		});
		await advance(delay - 1);
		expect(progress()).toBe(1);
		await advance(1);
		expect(progress()).toBe(2);
		await advance();
		expect(progress()).toBe(3);
		await advance();
		expect(progress()).toBe(4);
		await advance(delay * 4);
		expect(progress()).toBe(4);
		expect(vi.getTimerCount()).toBe(0);
	});

	it('marks exactly the current step panel active with earlier panels done and later panels waiting', async () => {
		render(LandingOpsBoard);
		expect(panelStates()).toEqual(['ready', 'waiting', 'waiting', 'waiting']);
		const fills = () => [...panel('policy').querySelectorAll<HTMLElement>(':not([aria-hidden]) > .meters .usage-fill')].map((fill) => fill.style.width);
		const idleFills = fills();
		expect(idleFills).toHaveLength(2);
		await start();
		for (let step = 0; step < 4; step += 1) {
			expect(panelStates()).toEqual(stepStates(step));
			expect(panelStates().filter((state) => state === 'active')).toHaveLength(1);
			if (step === 0) expect(fills()).toEqual(idleFills);
			if (step === 1) expect(fills().every((width, index) => parseFloat(width) > parseFloat(idleFills[index]!))).toBe(true);
			await advance();
		}
		expect(panelStates()).toEqual(['done', 'done', 'done', 'done']);

		await fireEvent.click(screen.getByRole('button', { name: '다시 체험' }));
		await advance();
		await advance();
		await fireEvent.click(screen.getByRole('button', { name: '일시정지' }));
		await advance(delay * 3);
		expect(panelStates()).toEqual(stepStates(2));
	});

	it('completes 클러스터 실습 with cluster nodes and its template instead of the GPU instance', async () => {
		render(LandingOpsBoard);
		await fireEvent.click(screen.getByRole('button', { name: '클러스터 실습' }));
		await start();
		await advance(delay * 4);
		const resource = panel('resource');
		expect(resource.dataset.state).toBe('done');
		expect(resource.querySelector('[data-resource]')?.getAttribute('data-resource')).toBe('cluster');
		expect(resource.querySelectorAll('[data-node]')).toHaveLength(4);
		expect(resource.querySelectorAll('[data-pod]')).toHaveLength(12);
		expect(resource.querySelector('[data-link]')).toBeNull();
		expect(document.querySelector('[data-resource="gpu"]')).toBeNull();
		expect(panel('reuse').dataset.state).toBe('done');
		expect(reuseResult()).toBe('distributed-training');
	});

	it('keeps keyboard focus on one run control while its action changes', async () => {
		render(LandingOpsBoard);
		const control = screen.getByRole('button', { name: '환경 구성 체험' });
		control.focus();
		await fireEvent.click(control);
		expect(document.activeElement).toBe(screen.getByRole('button', { name: '일시정지' }));
		await fireEvent.click(control);
		expect(document.activeElement).toBe(screen.getByRole('button', { name: '계속하기' }));
		await fireEvent.click(control);
		await advance(delay * 4);
		expect(document.activeElement).toBe(screen.getByRole('button', { name: '다시 체험' }));
	});

	it.each([
		['클러스터 실습', 'cluster', 'distributed-training'],
		['공유 데이터', 'data', 'genomics-baseline'],
	])('cancels pending GPU work when switching to %s and publishes only the new scenario', async (label, key, output) => {
		render(LandingOpsBoard);
		await start();
		const previousObserver = observer;
		await advance(delay * 3 + delay - 1);
		await fireEvent.click(screen.getByRole('button', { name: label }));
		expect(screen.getByRole('button', { name: label }).getAttribute('aria-pressed')).toBe('true');
		expect(screen.getByRole('button', { name: 'GPU 연구' }).getAttribute('aria-pressed')).toBe('false');
		expect(progress()).toBe(0);
		expect(panelStates()).toEqual(['ready', 'waiting', 'waiting', 'waiting']);
		expect(panel('resource').querySelector('[data-resource]')?.getAttribute('data-resource')).toBe(key);
		await advance(delay * 5);
		expect(progress()).toBe(0);
		expect(panel('reuse').dataset.state).toBe('waiting');
		await start();
		previousObserver.setVisible(false);
		await advance(1);
		expect(progress()).toBe(0);
		await advance(delay * 4);
		expect(panel('reuse').dataset.state).toBe('done');
		expect(reuseResult()).toBe(output);
	});

	it('resets paused and completed configurations when choosing another scenario', async () => {
		render(LandingOpsBoard);
		await start();
		await advance();
		await fireEvent.click(screen.getByRole('button', { name: '일시정지' }));
		await fireEvent.click(screen.getByRole('button', { name: '공유 데이터' }));
		expect(progress()).toBe(0);
		await start();
		await advance(delay * 4);
		await fireEvent.click(screen.getByRole('button', { name: 'GPU 연구' }));
		expect(progress()).toBe(0);
		expect(panelStates()).toEqual(['ready', 'waiting', 'waiting', 'waiting']);
		await advance(delay * 5);
		expect(progress()).toBe(0);
	});

	it.each(['hidden', 'offscreen'])('pauses on %s and requires explicit resume after returning', async (reason) => {
		render(LandingOpsBoard);
		await start();
		await advance();
		await act(async () => {
			if (reason === 'hidden') {
				hidden = true;
				document.dispatchEvent(new Event('visibilitychange'));
			} else observer.setVisible(false);
			await tick();
		});
		await advance(delay * 5);
		expect(progress()).toBe(1);
		await fireEvent.click(screen.getByRole('button', { name: '계속하기' }));
		if (reason === 'offscreen') {
			await act(async () => {
				observer.setVisible(false);
				await tick();
			});
		}
		await advance();
		expect(progress()).toBe(1);
		await act(async () => {
			hidden = false;
			document.dispatchEvent(new Event('visibilitychange'));
			observer.setVisible(true);
			await tick();
		});
		await advance(delay * 5);
		expect(progress()).toBe(1);
		await fireEvent.click(screen.getByRole('button', { name: '계속하기' }));
		await advance(delay * 3);
		expect(progress()).toBe(4);
	});

	it('completes immediately with reduced motion but still waits for start and supports replay and scenario changes', async () => {
		preference.matches = true;
		render(LandingOpsBoard);
		expect(progress()).toBe(0);
		await start();
		expect(progress()).toBe(4);
		expect(panelStates()).toEqual(['done', 'done', 'done', 'done']);
		const stageItems = within(screen.getByRole('list', { name: '환경 구성 단계' })).getAllByRole('listitem');
		expect(stageItems.every((item) => item.classList.contains('done') && item.querySelector('svg'))).toBe(true);
		expect(vi.getTimerCount()).toBe(0);
		await fireEvent.click(screen.getByRole('button', { name: '다시 체험' }));
		expect(progress()).toBe(4);
		await fireEvent.click(screen.getByRole('button', { name: '공유 데이터' }));
		expect(progress()).toBe(0);
		await start();
		expect(reuseResult()).toBe('genomics-baseline');
	});

	it('cancels a running delay when reduced motion is enabled and restores timed playback only on a new run', async () => {
		render(LandingOpsBoard);
		await start();
		await advance(delay - 1);
		await motion(true);
		expect(progress()).toBe(4);
		expect(vi.getTimerCount()).toBe(0);
		await motion(false);
		await advance(delay * 5);
		expect(progress()).toBe(4);
		await fireEvent.click(screen.getByRole('button', { name: '다시 체험' }));
		expect(progress()).toBe(0);
		await advance();
		expect(progress()).toBe(1);
	});

	it('keeps a paused run under user control when the motion preference changes', async () => {
		render(LandingOpsBoard);
		await start();
		await advance();
		await fireEvent.click(screen.getByRole('button', { name: '일시정지' }));
		await motion(true);
		await advance(delay * 5);
		expect(progress()).toBe(1);
		await fireEvent.click(screen.getByRole('button', { name: '계속하기' }));
		expect(progress()).toBe(4);
		expect(vi.getTimerCount()).toBe(0);
	});

	it('releases pending work and browser subscriptions on unmount without affecting a new board', async () => {
		const removeMedia = vi.spyOn(preference, 'removeEventListener');
		const removeDocument = vi.spyOn(document, 'removeEventListener');
		const { unmount } = render(LandingOpsBoard);
		await start();
		await advance(delay - 1);
		const oldObserver = observer;
		unmount();
		expect(vi.getTimerCount()).toBe(0);
		expect(oldObserver.disconnect).toHaveBeenCalledOnce();
		expect(removeMedia).toHaveBeenCalledWith('change', expect.any(Function));
		expect(removeDocument).toHaveBeenCalledWith('visibilitychange', expect.any(Function));
		render(LandingOpsBoard);
		await start();
		oldObserver.setVisible(false);
		await advance(1);
		expect(progress()).toBe(0);
		await advance(delay - 1);
		expect(progress()).toBe(1);
	});
});
