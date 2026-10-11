import { get } from 'svelte/store';

const driverHarness = vi.hoisted(() => {
	const highlight = vi.fn();
	const refresh = vi.fn();
	const destroy = vi.fn();
	let options: Record<string, () => void> = {};
	const driver = vi.fn((nextOptions: Record<string, () => void>) => {
		options = nextOptions;
		return { highlight, refresh, destroy };
	});
	return {
		driver,
		highlight,
		refresh,
		destroy,
		options: () => options,
	};
});

vi.mock('driver.js', () => ({ driver: driverHarness.driver }));
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { sidebarOpen } from '$lib/stores/sidebar';
import { refreshTourAnchor, startTour, stopTour } from '../engine';
import { clearPersistedTour, readPersistedTour, waitForElement } from '../engine';
import { getTour, isTourId, tours, TOUR_IDS, TOUR_STORAGE_KEY } from '../tours';

const originalInnerWidth = window.innerWidth;
const originalGetClientRects = HTMLElement.prototype.getClientRects;

beforeEach(() => {
	sessionStorage.clear();
	document.body.innerHTML = '';
	sidebarOpen.close();
	driverHarness.highlight.mockClear();
	driverHarness.refresh.mockClear();
	driverHarness.destroy.mockClear();
	HTMLElement.prototype.getClientRects = function () {
		return { 0: this.getBoundingClientRect(), length: 1, item: () => this.getBoundingClientRect(), [Symbol.iterator]: function* () { yield this[0]; } } as DOMRectList;
	};
});

afterEach(() => {
	stopTour();
	vi.useRealTimers();
	sessionStorage.clear();
	document.body.innerHTML = '';
	sidebarOpen.close();
	Object.defineProperty(window, 'innerWidth', { value: originalInnerWidth, configurable: true });
	HTMLElement.prototype.getClientRects = originalGetClientRects;
});

describe('tour definitions', () => {
	it('declares unique ids and valid data-tour anchors', () => {
		const ids = tours.map((tour) => tour.id);
		expect(new Set(ids).size).toBe(ids.length);
		for (const { id } of tours) {
			const tour = getTour(id);
			expect(tour).not.toBeNull();
			expect(tour!.steps.length).toBeGreaterThan(0);
			// 첫 step은 시작 라우트를 가져야 어디서 시작해도 올바른 페이지로 이동한다
			expect(tour!.steps[0].route).toBeTruthy();
			for (const step of tour!.steps) {
				expect(step.element).toMatch(/^\[data-tour="[a-z-]+"\]$/);
				expect(step.title.length).toBeGreaterThan(0);
				expect(step.description.length).toBeGreaterThan(0);
			}
		}
	});

	it('resolves tour ids strictly', () => {
		expect(isTourId('vm-create')).toBe(true);
		expect(isTourId('volume')).toBe(true);
		expect(isTourId('drover')).toBe(true);
		expect(isTourId('admin')).toBe(false);
		expect(getTour('volume')?.steps[0].route).toBe('/dashboard/volumes');
		expect(getTour('nope')).toBeNull();
	});

	it('defines administrator tours with routed settlement anchors', () => {
		const expected = [
			['admin-compute', '/admin/instances', 'Compute 관리', 'admin-compute-ready'],
			['admin-storage', '/admin/volumes', '스토리지 관리', 'admin-storage-ready'],
			['admin-library', '/admin/libraries', '라이브러리 관리', 'admin-library-ready'],
			['admin-waygate', '/admin/waygate', 'Waygate 관리', 'waygate-ready'],
			['admin-network', '/admin/topology', '네트워크 관리', 'admin-network-ready'],
			['admin-containers', '/admin/containers', '컨테이너 관리', 'admin-containers-ready'],
			['admin-key-manager', '/admin/secrets', 'Key Manager 관리', 'admin-key-manager-ready'],
			['admin-monitoring', '/admin/monitoring', '통합 모니터링', 'admin-monitoring-list-ready'],
			['admin-system', '/admin/services', '시스템 서비스', 'admin-system-panel-ready'],
			['admin-identity', '/admin/users', 'Identity 관리', 'admin-identity-list-ready'],
		] as const;

		for (const [id, route, label, readyAnchor] of expected) {
			const definition = getTour(id);
			expect(definition).toMatchObject({ id, label });
			expect(definition?.steps[0].route).toBe(route);
			expect(definition?.steps.some((step) =>
				step.readyElement?.includes(readyAnchor) || step.skipReadyElement?.includes(readyAnchor)
			)).toBe(true);
			for (const step of definition?.steps ?? []) {
				const clickSelector = step.advanceOn === 'click' ? (step.advanceElement ?? step.element) : '';
				expect(clickSelector).not.toMatch(/create|delete|save|reset|submit|recover/i);
			}
		}
		const tenant = getTour('waygate');
		expect(tenant?.steps[0].route).toBe('/dashboard/network/waygate');
		expect(tenant?.steps[1].readyElement).toBe('[data-tour="waygate-ready"]');
	});

	it('vm-create 투어는 일반 VM 단계만 안내한다', () => {
		const tour = getTour('vm-create')!;
		expect(tour.steps).toHaveLength(6);
		expect(tour.steps.some((step) => /라이브러리|전략|베타|\bHA\b/.test(`${step.title} ${step.description}`))).toBe(false);
		expect(tour.steps.filter((step) => step.wizardStep !== undefined).map((step) => step.wizardStep)).toEqual([1, 2, 5, 6]);
	});

	it('vm-create 투어는 raw 위저드 단계와 팝오버 진행 방식을 매핑한다', () => {
		const tour = getTour('vm-create')!;
		const expected = [
			{ title: '이미지 선택', wizardStep: 1, advanceOn: 'wizard' },
			{ title: '플레이버 선택', wizardStep: 2, advanceOn: 'wizard' },
			{ title: '기본 설정 확인', wizardStep: 5, advanceOn: 'wizard' },
			{ title: '배포', wizardStep: 6, advanceOn: 'click' },
		] as const;

		for (const mapping of expected) {
			const step = tour.steps.find((candidate) => candidate.title === mapping.title);
			expect(step).toMatchObject({
				wizardStep: mapping.wizardStep,
				advanceOn: mapping.advanceOn,
			});
			expect(step?.backElement).toBeUndefined();
			expect(step?.cancelElement).toBe('[data-tour="wizard-cancel"]');
		}

		const imageStep = tour.steps.find((step) => step.title === '이미지 선택');
		expect(imageStep?.readyElement).toBe('[data-tour="wizard-body"]');
		const deployStep = tour.steps.find((step) => step.title === '배포');
		expect(deployStep?.advanceElement).toBe('[data-tour="wizard-next"]');
	});

});

describe('VM tour engine behavior', () => {
	it('tracks steps 1, 2, 5, 6 in both directions and finishes after deployment', async () => {
		document.body.innerHTML = `
			<div data-tour="wizard-panel"><div data-tour="wizard-body"></div></div>
			<button data-tour="wizard-next">deploy</button>
			<button data-tour="wizard-cancel">cancel</button>
			<div data-tour="dashboard-recent"></div>
		`;
		await startTour('vm-create', 1);
		expect(readPersistedTour()).toEqual({ tourId: 'vm-create', stepIndex: 1 });

		const sequence = [
			[2, 2, '플레이버 선택'],
			[5, 3, '기본 설정 확인'],
			[6, 4, '배포'],
			[5, 3, '기본 설정 확인'],
			[2, 2, '플레이버 선택'],
			[1, 1, '이미지 선택'],
			[6, 4, '배포'],
		] as const;
		for (const [wizardStep, stepIndex, title] of sequence) {
			const highlights = driverHarness.highlight.mock.calls.length;
			window.dispatchEvent(new CustomEvent('afterglow:wizard-step', { detail: { step: wizardStep } }));
			await vi.waitFor(() => expect(driverHarness.highlight).toHaveBeenCalledTimes(highlights + 1));
			expect(readPersistedTour()).toEqual({ tourId: 'vm-create', stepIndex });
			expect(driverHarness.highlight).toHaveBeenLastCalledWith(expect.objectContaining({
				popover: expect.objectContaining({ title: expect.stringContaining(title), showButtons: ['close'] }),
			}));
		}

		document.querySelector<HTMLButtonElement>('[data-tour="wizard-next"]')!.click();
		await vi.waitFor(() => expect(driverHarness.highlight).toHaveBeenLastCalledWith(
			expect.objectContaining({ element: '[data-tour="dashboard-recent"]' }),
		));
		expect(readPersistedTour()).toEqual({ tourId: 'vm-create', stepIndex: 5 });
		driverHarness.options().onNextClick();
		expect(readPersistedTour()).toBeNull();
	});
});


describe('administrator tour engine behavior', () => {
	it('waits for settlement before skipping an empty detail chain and completes', async () => {
		document.body.innerHTML = `
			<div data-tour="admin-containers-ready"></div>
			<div data-tour="admin-containers-list"></div>
		`;
		const complete = vi.fn();
		window.addEventListener('afterglow:tour-complete', complete, { once: true });

		await startTour('admin-containers', 2);

		await vi.waitFor(() => expect(complete).toHaveBeenCalledOnce());
		expect(readPersistedTour()).toBeNull();
	});

	it('reopens a compute detail on resume and Previous closes it before returning to the row', async () => {
		document.body.innerHTML = `
			<div data-tour="admin-compute-ready"></div>
			<div data-tour="admin-compute-row">
				<button data-tour="admin-compute-row-open">open</button>
			</div>
		`;
		const open = document.querySelector<HTMLElement>('[data-tour="admin-compute-row-open"]')!;
		open.onclick = () => {
			if (!document.querySelector('[data-tour="admin-compute-detail"]')) {
				const detail = document.createElement('div');
				detail.dataset.tour = 'admin-compute-detail';
				// 실제 DOM 과 같은 계약: 상세 패널의 닫기는 SlidePanel 이 그리는 `[data-slide-panel-close]` 하나뿐이다.
				// 자식 패널이 자기 × 를 또 그리던 중복을 제거하면서 투어 셀렉터도 이 정본으로 재배선했다.
				const close = document.createElement('button');
				close.textContent = 'close';
				close.setAttribute('data-slide-panel-close', '');
				close.onclick = () => detail.remove();
				detail.appendChild(close);
				document.body.appendChild(detail);
			}
		};

		await startTour('admin-compute', 5);
		expect(document.querySelector('[data-tour="admin-compute-detail"]')).not.toBeNull();
		expect(driverHarness.highlight).toHaveBeenLastCalledWith(
			expect.objectContaining({ element: '[data-tour="admin-compute-detail"]' }),
		);

		driverHarness.options().onPrevClick();
		await vi.waitFor(() => expect(driverHarness.highlight).toHaveBeenLastCalledWith(
			expect.objectContaining({ element: '[data-tour="admin-compute-row"]' }),
		));
		expect(document.querySelector('[data-tour="admin-compute-detail"]')).toBeNull();
		expect(driverHarness.highlight.mock.calls.at(-1)?.[0].popover.showButtons).toEqual(['previous', 'close']);
	});

	it('runs monitoring beforeReady before settlement so a hidden mobile list can be restored', async () => {
		document.body.innerHTML = `
			<button data-tour="admin-monitoring-instances-tab">instances</button>
			<button data-tour="admin-monitoring-back">back</button>
		`;
		document.querySelector<HTMLElement>('[data-tour="admin-monitoring-instances-tab"]')!.onclick = () => {
			if (document.querySelector('[data-tour="admin-monitoring-list-ready"]')) return;
			const ready = document.createElement('div');
			ready.dataset.tour = 'admin-monitoring-list-ready';
			const row = document.createElement('button');
			row.dataset.tour = 'admin-monitoring-row';
			document.body.append(ready, row);
		};

		await startTour('admin-monitoring', 4);

		expect(driverHarness.highlight).toHaveBeenLastCalledWith(
			expect.objectContaining({ element: '[data-tour="admin-monitoring-row"]' }),
		);
	});

	it('restores the selected system tab on start and refresh', async () => {
		document.body.innerHTML = `
			<div data-tour="admin-system-tabs"></div>
			<button data-tour="admin-system-network-tab">network</button>
			<div data-tour="admin-system-panel"></div>
		`;
		const tab = document.querySelector<HTMLElement>('[data-tour="admin-system-network-tab"]')!;
		tab.onclick = () => {
			if (document.querySelector('[data-tour="admin-system-panel-ready"]')) return;
			const ready = document.createElement('div');
			ready.dataset.tour = 'admin-system-panel-ready';
			document.body.appendChild(ready);
		};

		await startTour('admin-system', 3);
		expect(driverHarness.highlight).toHaveBeenLastCalledWith(
			expect.objectContaining({ element: '[data-tour="admin-system-panel"]' }),
		);

		document.querySelector('[data-tour="admin-system-panel-ready"]')?.remove();
		refreshTourAnchor();
		await vi.waitFor(() => expect(document.querySelector('[data-tour="admin-system-panel-ready"]')).not.toBeNull());
		expect(driverHarness.highlight).toHaveBeenLastCalledWith(
			expect.objectContaining({ element: '[data-tour="admin-system-panel"]' }),
		);
	});
});
describe('tour persistence', () => {
	it('roundtrips a valid tour state', () => {
		sessionStorage.setItem(TOUR_STORAGE_KEY, JSON.stringify({ tourId: 'drover', stepIndex: 2 }));
		expect(readPersistedTour()).toEqual({ tourId: 'drover', stepIndex: 2 });
		clearPersistedTour();
		expect(readPersistedTour()).toBeNull();
	});

	it('rejects unknown tours, out-of-range steps, and corrupt payloads', () => {
		sessionStorage.setItem(TOUR_STORAGE_KEY, JSON.stringify({ tourId: 'unknown', stepIndex: 0 }));
		expect(readPersistedTour()).toBeNull();
		sessionStorage.setItem(TOUR_STORAGE_KEY, JSON.stringify({ tourId: 'volume', stepIndex: 99 }));
		expect(readPersistedTour()).toBeNull();
		sessionStorage.setItem(TOUR_STORAGE_KEY, 'not-json');
		expect(readPersistedTour()).toBeNull();
	});
});

describe('waitForElement', () => {
	it('returns an element that appears after polling starts', async () => {
		setTimeout(() => {
			const el = document.createElement('div');
			el.dataset.tour = 'late-anchor';
			document.body.appendChild(el);
		}, 30);
		const found = await waitForElement('[data-tour="late-anchor"]', 500, 10);
		expect(found).not.toBeNull();
		expect(found?.dataset.tour).toBe('late-anchor');
	});

	it('returns null when the element never appears', async () => {
		const found = await waitForElement('[data-tour="never"]', 80, 10);
		expect(found).toBeNull();
	});
});
