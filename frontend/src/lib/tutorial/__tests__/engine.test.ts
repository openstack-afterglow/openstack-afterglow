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
vi.mock('$app/navigation', () => ({ goto: vi.fn().mockResolvedValue(undefined) }));
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { sidebarOpen } from '$lib/stores/sidebar';
import { goto } from '$app/navigation';
import { refreshTourAnchor, startTour, stopTour } from '../engine';
import { clearPersistedTour, readPersistedTour, waitForElement } from '../engine';
import { getTour, isTourId, tours, TOUR_IDS, TOUR_STORAGE_KEY } from '../tours';
import { closeWizard, resetWizard, wizard, wizardOpen } from '$lib/stores/wizard';
import { createdInstance } from '../createdInstance.svelte';
import { buildMockAuth } from '$lib/mockup/auth';
import { enterMockAuth, exitMockAuth } from '$lib/stores/auth';

const originalInnerWidth = window.innerWidth;
const originalLocation = window.location.href;
const originalGetClientRects = HTMLElement.prototype.getClientRects;

beforeEach(() => {
	sessionStorage.clear();
	enterMockAuth(buildMockAuth('admin', '/admin/projects'), 'admin');
	document.body.innerHTML = '';
	sidebarOpen.close();
	wizardOpen.set(false);
	vi.mocked(goto).mockReset().mockResolvedValue(undefined);
	driverHarness.highlight.mockClear();
	driverHarness.refresh.mockClear();
	driverHarness.destroy.mockClear();
	HTMLElement.prototype.getClientRects = function () {
		return { 0: this.getBoundingClientRect(), length: 1, item: () => this.getBoundingClientRect(), [Symbol.iterator]: function* () { yield this[0]; } } as DOMRectList;
	};
});

afterEach(() => {
	stopTour();
	exitMockAuth();
	vi.useRealTimers();
	sessionStorage.clear();
	document.body.innerHTML = '';
	sidebarOpen.close();
	wizardOpen.set(false);
	window.history.replaceState({}, '', originalLocation);
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

	it('creates through the VM wizard steps and deletes only the created instance from its detail route', () => {
		const vm = getTour('vm-create')!.steps;
		const tour = getTour('instance-detail-delete')!;
		// Wizard anchors and raw wizard steps stay identical to vm-create; the copy is tour-specific.
		expect(tour.steps.slice(0, 5).map((step) => [step.element, step.wizardStep, step.advanceOn]))
			.toEqual(vm.slice(0, 5).map((step) => [step.element, step.wizardStep, step.advanceOn]));
		expect(tour.steps[0].title).not.toBe(vm[0].title);
		expect(tour.steps[5]).toMatchObject({ followWizard: expect.any(Function), beforeReady: expect.any(Function), cancelElement: vm.at(-1)!.cancelElement });
		expect(tour.steps.slice(5).map((step) => step.element)).toEqual([
			'[data-tour="instance-created-row"]',
			'[data-tour="instance-detail-stop"]',
			'[data-tour="confirm-accept"]',
			'[data-tour="instance-detail-delete"]',
			'[data-tour="confirm-accept"]',
			'[data-tour="instance-list"]',
		]);
		createdInstance.id = null;
		expect(tour.steps[6].route).toBe('/dashboard/compute/instances');
		createdInstance.id = 'mock-instance-9';
		expect(tour.steps[6].route).toBe('/dashboard/compute/instances/mock-instance-9');
		createdInstance.id = null;
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

	it.each(['studio', 'profiles'])('settles the studio route from tab=%s without repeated navigation', async tab => {
		window.history.replaceState({}, '', `/admin/libraries?tab=${tab}&tutorial=admin`);
		document.body.innerHTML = '<div data-tour="admin-library-import"></div>';
		vi.mocked(goto).mockImplementation(async url => {
			window.history.replaceState({}, '', `${url}&tutorial=admin`);
		});
		await startTour('admin-library', 1);
		expect(goto).toHaveBeenCalledTimes(tab === 'studio' ? 0 : 1);
		const highlights = driverHarness.highlight.mock.calls.length;
		refreshTourAnchor();
		await vi.waitFor(() => expect(driverHarness.highlight).toHaveBeenCalledTimes(highlights + 1));
		expect(goto).toHaveBeenCalledTimes(tab === 'studio' ? 0 : 1);
	});

	it('keeps unrelated query parameters on an already matching queryless route', async () => {
		window.history.replaceState({}, '', '/admin/libraries?tutorial=admin&tab=catalog');
		document.body.innerHTML = '<div data-tour="admin-library-header"></div><div data-tour="admin-library-ready"></div>';
		await startTour('admin-library');
		expect(goto).not.toHaveBeenCalled();
	});


});

describe('VM tour engine behavior', () => {
	it('finishes after the real successful reset-then-close sequence instead of returning to Flavor', async () => {
		document.body.innerHTML = '<div data-tour="wizard-panel"><div data-tour="wizard-body"></div></div><button data-tour="wizard-next">deploy</button><div data-tour="instance-list"></div>';
		wizard.update(value => ({ ...value, step: 6 }));
		wizardOpen.set(true);
		await startTour('vm-create', 4);
		document.querySelector<HTMLButtonElement>('[data-tour="wizard-next"]')!.click();
		await vi.waitFor(() => expect(readPersistedTour()).toEqual({ tourId: 'vm-create', stepIndex: 5 }));
		resetWizard();
		closeWizard();
		await vi.waitFor(() => expect(driverHarness.highlight).toHaveBeenLastCalledWith(expect.objectContaining({ element: '[data-tour="instance-list"]' })));
		expect(readPersistedTour()).toEqual({ tourId: 'vm-create', stepIndex: 5 });
		driverHarness.options().onNextClick();
		expect(readPersistedTour()).toBeNull();
	});
	it.each([false, true])('cancels deployment waiting without completion after capacity correction=%s', async correction => {
		document.body.innerHTML = '<div data-tour="wizard-panel"><div data-tour="wizard-body"></div></div><button data-tour="wizard-next">deploy</button><button data-tour="wizard-cancel">cancel</button><div data-tour="instance-list"></div>';
		wizardOpen.set(true);
		const complete = vi.fn();
		window.addEventListener('afterglow:tour-complete', complete);
		try {
			await startTour('vm-create', 4);
			document.querySelector<HTMLButtonElement>('[data-tour="wizard-next"]')!.click();
			await vi.waitFor(() => expect(readPersistedTour()).toEqual({ tourId: 'vm-create', stepIndex: 5 }));
			if (correction) {
				window.dispatchEvent(new CustomEvent('afterglow:wizard-step', { detail: { step: 2 } }));
				await vi.waitFor(() => expect(readPersistedTour()).toEqual({ tourId: 'vm-create', stepIndex: 1 }));
				await vi.waitFor(() => expect(driverHarness.highlight).toHaveBeenLastCalledWith(expect.objectContaining({ popover: expect.objectContaining({ title: expect.stringContaining('플레이버 선택') }) })));
			}
			document.querySelector<HTMLButtonElement>('[data-tour="wizard-cancel"]')!.click();
			wizardOpen.set(false);
			await Promise.resolve();
			expect(readPersistedTour()).toBeNull();
			expect(complete).not.toHaveBeenCalled();
		} finally {
			window.removeEventListener('afterglow:tour-complete', complete);
		}
	});
	it('waits for the instance route and page action without opening global navigation', async () => {
		const route = Promise.withResolvers<void>();
		vi.mocked(goto).mockImplementationOnce(async () => {
			await route.promise;
			document.body.innerHTML = '<button data-tour="vm-create-open">create</button>';
		});
		sidebarOpen.open();
		const starting = startTour('vm-create');
		await vi.waitFor(() => expect(goto).toHaveBeenCalledWith('/dashboard/compute/instances'));
		expect(driverHarness.highlight).not.toHaveBeenCalled();
		route.resolve();
		await starting;
		expect(get(sidebarOpen)).toBe(false);
		expect(driverHarness.highlight).toHaveBeenLastCalledWith(expect.objectContaining({ element: '[data-tour="vm-create-open"]' }));
		const button = document.querySelector<HTMLButtonElement>('[data-tour="vm-create-open"]')!;
		button.addEventListener('click', () => {
			document.body.insertAdjacentHTML('beforeend', '<div data-tour="wizard-panel"><div data-tour="wizard-body"></div></div>');
		}, { once: true });
		button.click();
		await vi.waitFor(() => expect(readPersistedTour()).toEqual({ tourId: 'vm-create', stepIndex: 1 }));
		await vi.waitFor(() => expect(driverHarness.highlight).toHaveBeenLastCalledWith(expect.objectContaining({ element: '[data-tour="wizard-panel"]' })));
	});
	it('tracks Flavor then image in both directions and finishes after deployment', async () => {
		document.body.innerHTML = `
			<div data-tour="wizard-panel"><div data-tour="wizard-body"></div></div>
			<button data-tour="wizard-next">deploy</button>
			<button data-tour="wizard-cancel">cancel</button>
		`;
		await startTour('vm-create', 1);
		expect(readPersistedTour()).toEqual({ tourId: 'vm-create', stepIndex: 1 });

		const sequence = [
			[1, 2, '이미지 선택'],
			[5, 3, '기본 설정 확인'],
			[6, 4, '배포'],
			[5, 3, '기본 설정 확인'],
			[1, 2, '이미지 선택'],
			[2, 1, '플레이버 선택'],
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

		wizardOpen.set(true);
		document.querySelector<HTMLButtonElement>('[data-tour="wizard-next"]')!.click();
		expect(driverHarness.highlight).toHaveBeenLastCalledWith(expect.objectContaining({ element: '[data-tour="wizard-panel"]' }));
		document.body.insertAdjacentHTML('beforeend', '<div data-tour="instance-list"></div>');
		vi.useFakeTimers();
		await vi.advanceTimersByTimeAsync(25000);
		expect(driverHarness.highlight).toHaveBeenLastCalledWith(expect.objectContaining({ element: '[data-tour="wizard-panel"]' }));
		wizardOpen.set(false);
		await vi.advanceTimersByTimeAsync(0);
		vi.useRealTimers();
		await vi.waitFor(() => expect(driverHarness.highlight).toHaveBeenLastCalledWith(
			expect.objectContaining({ element: '[data-tour="instance-list"]' }),
		));
		expect(readPersistedTour()).toEqual({ tourId: 'vm-create', stepIndex: 5 });
		driverHarness.options().onNextClick();
		expect(readPersistedTour()).toBeNull();
	});
});

describe('instance detail delete tour engine behavior', () => {
	afterEach(() => { createdInstance.id = null; });

	const lastElement = () => driverHarness.highlight.mock.lastCall?.[0]?.element;
	const clickAndReplace = (selector: string, html: string) => {
		const target = document.querySelector<HTMLElement>(selector)!;
		// Page reaction runs after the engine's capture-phase advance listener, as in the app.
		target.addEventListener('click', () => { document.body.innerHTML = html; }, { once: true });
		target.click();
	};

	it('clears an earlier recorded instance when the tour starts', async () => {
		createdInstance.id = 'mock-instance-old';
		document.body.innerHTML = '<button data-tour="vm-create-open">create</button>';
		await startTour('instance-detail-delete');
		expect(createdInstance.id).toBeNull();
		expect(lastElement()).toBe('[data-tour="vm-create-open"]');
	});

	it('opens the recorded tut- instance detail, stops it, deletes it and completes on the list', async () => {
		createdInstance.id = 'mock-instance-9';
		document.body.innerHTML = '<div data-tour="instance-list"><button data-tour="instance-created-row">tut-vm-delete</button></div>';
		await startTour('instance-detail-delete', 5);
		expect(lastElement()).toBe('[data-tour="instance-created-row"]');

		vi.mocked(goto).mockImplementationOnce(async () => {
			document.body.innerHTML = '<button data-tour="instance-detail-stop">stop</button>';
		});
		driverHarness.options().onNextClick();
		await vi.waitFor(() => expect(lastElement()).toBe('[data-tour="instance-detail-stop"]'));
		expect(goto).toHaveBeenLastCalledWith('/dashboard/compute/instances/mock-instance-9');

		clickAndReplace('[data-tour="instance-detail-stop"]', '<button data-tour="instance-detail-stop">stop</button><button data-tour="confirm-accept">ok</button>');
		await vi.waitFor(() => expect(lastElement()).toBe('[data-tour="confirm-accept"]'));
		expect(readPersistedTour()).toEqual({ tourId: 'instance-detail-delete', stepIndex: 7 });

		// Accepting closes the dialog; the SHUTOFF re-render replaces Stop with Delete after a poll.
		clickAndReplace('[data-tour="confirm-accept"]', '<p>stopping</p>');
		await vi.waitFor(() => expect(readPersistedTour()).toEqual({ tourId: 'instance-detail-delete', stepIndex: 8 }));
		document.body.innerHTML = '<button data-tour="instance-detail-delete">delete</button>';
		await vi.waitFor(() => expect(lastElement()).toBe('[data-tour="instance-detail-delete"]'));

		clickAndReplace('[data-tour="instance-detail-delete"]', '<button data-tour="instance-detail-delete">delete</button><button data-tour="confirm-accept">ok</button>');
		await vi.waitFor(() => expect(readPersistedTour()).toEqual({ tourId: 'instance-detail-delete', stepIndex: 9 }));
		await vi.waitFor(() => expect(lastElement()).toBe('[data-tour="confirm-accept"]'));

		clickAndReplace('[data-tour="confirm-accept"]', '<div data-tour="instance-list"></div>');
		await vi.waitFor(() => expect(lastElement()).toBe('[data-tour="instance-list"]'));
		expect(readPersistedTour()).toEqual({ tourId: 'instance-detail-delete', stepIndex: 10 });
		driverHarness.options().onNextClick();
		expect(readPersistedTour()).toBeNull();
	});
});


describe('image inventory tutorial behavior', () => {
	it.each(['images', 'admin-images'] as const)('waits for %s inventory and completes without invoking upload', async (tourId) => {
		const route = tourId === 'images' ? '/dashboard/compute/images' : '/admin/images';
		window.history.replaceState({}, '', route);
		document.body.innerHTML = `<div data-tour="${tourId}-header"><button>upload</button></div>`;
		const upload = vi.fn();
		document.querySelector('button')!.addEventListener('click', upload);
		const complete = vi.fn();
		window.addEventListener('afterglow:tour-complete', complete, { once: true });
		await startTour(tourId);
		driverHarness.options().onNextClick();
		expect(driverHarness.highlight).toHaveBeenCalledTimes(1);
		document.body.insertAdjacentHTML('beforeend', `<div data-tour="${tourId}-controls"></div><div data-tour="${tourId}-ready"></div><div data-tour="${tourId}-results"></div>`);
		await vi.waitFor(() => expect(readPersistedTour()).toEqual({ tourId, stepIndex: 1 }));
		await vi.waitFor(() => expect(driverHarness.highlight).toHaveBeenCalledTimes(2));
		driverHarness.options().onNextClick();
		await vi.waitFor(() => expect(readPersistedTour()).toEqual({ tourId, stepIndex: 2 }));
		driverHarness.options().onNextClick();
		await vi.waitFor(() => expect(complete).toHaveBeenCalledOnce());
		expect(readPersistedTour()).toBeNull();
		expect(upload).not.toHaveBeenCalled();
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
			<div data-tour="admin-compute-list"></div>
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

	function mountRouterCreateDialog(): void {
		window.history.replaceState({}, '', '/admin/routers');
		document.body.innerHTML = '<button data-tour="admin-routers-create-open">create</button>';
		document.querySelector<HTMLElement>('[data-tour="admin-routers-create-open"]')!.onclick = () => {
			const dialog = document.createElement('div');
			dialog.setAttribute('role', 'dialog');
			dialog.innerHTML = '<form data-tour="admin-routers-create-form"><input name="name"><button type="button" data-tour="admin-routers-create-submit">create</button></form>';
			document.body.appendChild(dialog);
		};
	}

	it('rewinds to the opener at once when Escape closes the highlighted form dialog', async () => {
		mountRouterCreateDialog();
		await startTour('admin-routers');
		document.querySelector<HTMLElement>('[data-tour="admin-routers-create-open"]')!.click();
		await vi.waitFor(() => expect(driverHarness.highlight).toHaveBeenLastCalledWith(
			expect.objectContaining({ element: '[data-tour="admin-routers-create-form"]' }),
		));

		// Modal's Escape handler unmounts the whole `{#if open}` dialog frame.
		document.querySelector('[role="dialog"]')!.remove();

		// The form step's 3s wait must not run first; vi.waitFor gives up after 1s.
		await vi.waitFor(() => expect(driverHarness.highlight).toHaveBeenLastCalledWith(
			expect.objectContaining({ element: '[data-tour="admin-routers-create-open"]' }),
		));
		expect(readPersistedTour()).toEqual({ tourId: 'admin-routers', stepIndex: 0 });

		// The re-armed opener reopens the dialog and the form step highlights again.
		document.querySelector<HTMLElement>('[data-tour="admin-routers-create-open"]')!.click();
		await vi.waitFor(() => expect(driverHarness.highlight).toHaveBeenLastCalledWith(
			expect.objectContaining({ element: '[data-tour="admin-routers-create-form"]' }),
		));
	});

	it('re-anchors the same form step when the target re-renders inside a still-open dialog', async () => {
		mountRouterCreateDialog();
		await startTour('admin-routers');
		document.querySelector<HTMLElement>('[data-tour="admin-routers-create-open"]')!.click();
		await vi.waitFor(() => expect(driverHarness.highlight).toHaveBeenLastCalledWith(
			expect.objectContaining({ element: '[data-tour="admin-routers-create-form"]' }),
		));
		const highlights = driverHarness.highlight.mock.calls.length;

		const dialog = document.querySelector('[role="dialog"]')!;
		dialog.querySelector('form')!.replaceWith(dialog.querySelector('form')!.cloneNode(true));

		await vi.waitFor(() => expect(driverHarness.highlight.mock.calls.length).toBe(highlights + 1));
		expect(driverHarness.highlight).toHaveBeenLastCalledWith(
			expect.objectContaining({ element: '[data-tour="admin-routers-create-form"]' }),
		);
		expect(readPersistedTour()).toEqual({ tourId: 'admin-routers', stepIndex: 1 });
	});

	it('highlights the target at once while the settle anchor is pending and offers Next only after it appears', async () => {
		document.body.innerHTML = '<div data-tour="database-backups-create-form"></div><div data-tour="database-backups-created">tut-backup NEW</div>';
		void startTour('database-backups', 3);
		await vi.waitFor(() => expect(driverHarness.highlight).toHaveBeenCalled());
		const waiting = driverHarness.highlight.mock.calls.at(-1)![0];
		expect(waiting.element).toBe('[data-tour="database-backups-created"]');
		// Next is withheld, Previous stays so a failed submit never traps the user.
		expect(waiting.popover.showButtons).toEqual(['previous', 'close']);

		document.body.insertAdjacentHTML('beforeend', '<button data-tour="database-backups-delete">delete</button>');
		await vi.waitFor(() => expect(driverHarness.highlight.mock.calls.at(-1)![0].popover.showButtons).toContain('next'));
		expect(driverHarness.highlight.mock.calls.at(-1)![0].element).toBe('[data-tour="database-backups-created"]');
	});

	it('does not leave focus on the popover close button of an interactive step and swallows Space on the bare page', async () => {
		document.body.innerHTML = '<button data-tour="database-backups-instance-open">open</button><div class="driver-popover"><button id="popover-close">x</button></div>';
		void startTour('database-backups', 0);
		await vi.waitFor(() => expect(driverHarness.highlight).toHaveBeenCalled());
		// driver.js focusing its close button after rendering must not stick: Space or Enter would end the tour.
		const close = document.querySelector<HTMLButtonElement>('#popover-close')!;
		close.focus();
		expect(document.activeElement).not.toBe(close);
		const space = new KeyboardEvent('keydown', { key: ' ', bubbles: true, cancelable: true });
		document.body.dispatchEvent(space);
		expect(space.defaultPrevented).toBe(true);
	});

	const snapshotDialog = (withStaleAlert: boolean) => {
		document.body.innerHTML = `<div role="dialog"><div data-tour="volume-snapshots-create-form"><button data-tour="volume-snapshots-create-submit">Create</button></div>${withStaleAlert ? '<p role="alert">Previous failure</p>' : ''}</div><div data-tour="volume-snapshots-list">list</div>`;
		return document.querySelector<HTMLButtonElement>('[data-tour="volume-snapshots-create-submit"]')!;
	};

	it('goes back to the form at once when a failed create adds an error alert to the open dialog', async () => {
		const submit = snapshotDialog(false);
		// Real failure: the page shows a NEW alert after the request is rejected.
		submit.addEventListener('click', () => {
			queueMicrotask(() => document.querySelector('[role="dialog"]')!.insertAdjacentHTML('beforeend', '<p role="alert">Invalid volume</p>'));
		});
		await startTour('volume-snapshots', 1);
		submit.click();
		// The 120s settle wait must not run: step 2 (the form) is presented again within vi.waitFor's 1s.
		await vi.waitFor(() => expect(readPersistedTour()).toEqual({ tourId: 'volume-snapshots', stepIndex: 1 }));
		await vi.waitFor(() => expect(driverHarness.highlight).toHaveBeenLastCalledWith(
			expect.objectContaining({ element: '[data-tour="volume-snapshots-create-form"]' }),
		));
	});

	it('does not mistake an alert left by an earlier failed attempt for a failed retry', async () => {
		const submit = snapshotDialog(true);
		// The retry succeeds: the page clears the old alert (after the tour advanced) and the delete anchor appears.
		submit.addEventListener('click', () => {
			document.querySelector('[role="alert"]')!.remove();
			document.body.insertAdjacentHTML('beforeend', '<button data-tour="volume-snapshots-delete">Delete</button>');
		});
		await startTour('volume-snapshots', 1);
		submit.click();
		await vi.waitFor(() => expect(driverHarness.highlight).toHaveBeenLastCalledWith(
			expect.objectContaining({ element: '[data-tour="volume-snapshots-list"]' }),
		));
		expect(readPersistedTour()).toEqual({ tourId: 'volume-snapshots', stepIndex: 2 });
	});

	it('refreshes the overlay when an inner container scrolls', async () => {
		document.body.innerHTML = '<div id="main-content"><button data-tour="database-backups-instance-open">open</button></div>';
		void startTour('database-backups', 0);
		await vi.waitFor(() => expect(driverHarness.highlight).toHaveBeenCalled());
		const before = driverHarness.refresh.mock.calls.length;
		document.querySelector('#main-content')!.dispatchEvent(new Event('scroll'));
		await vi.waitFor(() => expect(driverHarness.refresh.mock.calls.length).toBeGreaterThan(before));
	});

	it('focuses the field of a typing step when the dialog had focused its backdrop button', async () => {
		document.body.innerHTML = '<div role="dialog"><button id="backdrop">close dialog</button><input data-tour="mcp-token-name" /></div>';
		document.querySelector<HTMLButtonElement>('#backdrop')!.focus();
		void startTour('account-mcp', 1);
		await vi.waitFor(() => expect(driverHarness.highlight).toHaveBeenCalled());
		expect(document.activeElement).toBe(document.querySelector('[data-tour="mcp-token-name"]'));
	});

	it('does not offer Previous when the previous step is hidden behind a modal or already gone', async () => {
		document.body.innerHTML = '<div inert><button data-tour="database-backups-create-open">open</button></div><div data-tour="database-backups-create-form"></div>';
		void startTour('database-backups', 2);
		await vi.waitFor(() => expect(driverHarness.highlight).toHaveBeenCalled());
		// Step 3 (index 2) follows the opener, which a modal made inert: Previous would strand the user.
		expect(driverHarness.highlight.mock.calls.at(-1)![0].popover.showButtons).toEqual(['close']);
	});

	it('withdraws Previous when the previous target disappears right after the step is shown', async () => {
		document.body.innerHTML = '<div data-tour="database-backups-create-form"></div><div data-tour="database-backups-created">row</div><button data-tour="database-backups-delete">delete</button>';
		void startTour('database-backups', 3);
		await vi.waitFor(() => expect(driverHarness.highlight.mock.calls.at(-1)![0].popover.showButtons).toContain('previous'));
		// The previous step's dialog closes after the click that advanced the tour.
		document.querySelector('[data-tour="database-backups-create-form"]')!.remove();
		await vi.waitFor(() => expect(driverHarness.highlight.mock.calls.at(-1)![0].popover.showButtons).not.toContain('previous'));
	});

	it('withdraws Next when a property-only change (re-checked box) makes the ready anchor disappear', async () => {
		document.body.innerHTML = '<div data-tour="admin-domains-create-name"></div><div data-tour="admin-domains-enabled"><input type="checkbox" /></div><button data-tour="admin-domains-disable-submit">save</button>';
		const box = document.querySelector<HTMLInputElement>('[data-tour="admin-domains-enabled"] input')!;
		box.checked = true;
		void startTour('admin-domains', 4);
		await vi.waitFor(() => expect(driverHarness.highlight).toHaveBeenCalled());
		expect(driverHarness.highlight.mock.calls.at(-1)![0].popover.showButtons).not.toContain('next');
		box.checked = false;
		box.dispatchEvent(new Event('change', { bubbles: true }));
		await vi.waitFor(() => expect(driverHarness.highlight.mock.calls.at(-1)![0].popover.showButtons).toContain('next'));
		box.checked = true;
		box.dispatchEvent(new Event('change', { bubbles: true }));
		await vi.waitFor(() => expect(driverHarness.highlight.mock.calls.at(-1)![0].popover.showButtons).not.toContain('next'));
	});

	it('swallows clicks inside the target while the settle anchor is pending, then lets the advance click through', async () => {
		document.body.innerHTML = '<div data-tour="mcp-token-submit-row"><button data-tour="mcp-token-submit">Issue</button></div>';
		const submit = document.querySelector<HTMLButtonElement>('[data-tour="mcp-token-submit"]')!;
		const issued = vi.fn();
		submit.addEventListener('click', issued);
		void startTour('account-mcp', 2);
		await vi.waitFor(() => expect(driverHarness.highlight).toHaveBeenCalled());
		expect(driverHarness.highlight.mock.calls.at(-1)![0].popover.showButtons).not.toContain('next');

		submit.click();
		// The capture handlers and showStep's synchronous state write run inside click(), so no waiting is needed.
		expect(readPersistedTour()).toEqual({ tourId: 'account-mcp', stepIndex: 2 });
		expect(issued).not.toHaveBeenCalled();

		document.querySelector('[data-tour="mcp-token-submit-row"]')!.setAttribute('data-tour-settled', 'true');
		await vi.waitFor(() => {
			submit.click();
			expect(issued).toHaveBeenCalledOnce();
		});
		await vi.waitFor(() => expect(readPersistedTour()).toEqual({ tourId: 'account-mcp', stepIndex: 3 }));
	});

	it('keeps the target usable while waiting when the input that ends the wait lives in it', async () => {
		document.body.innerHTML = '<input data-tour="mcp-token-name" />';
		const input = document.querySelector<HTMLInputElement>('[data-tour="mcp-token-name"]')!;
		const clicked = vi.fn();
		input.addEventListener('click', clicked);
		void startTour('account-mcp', 1);
		await vi.waitFor(() => expect(driverHarness.highlight).toHaveBeenCalled());
		input.click();
		expect(clicked).toHaveBeenCalledOnce();
	});

	it('hands focus back to the typing field when driver.js moves it to the popover, and withdraws Next when the input becomes incomplete', async () => {
		document.body.innerHTML = '<input data-tour="mcp-token-name" /><button data-tour="mcp-token-submit">Issue</button><div class="driver-popover"><button id="popover-close">x</button></div>';
		const input = document.querySelector<HTMLInputElement>('[data-tour="mcp-token-name"]')!;
		input.focus();
		void startTour('account-mcp', 1);
		await vi.waitFor(() => expect(driverHarness.highlight.mock.calls.at(-1)![0].popover.showButtons).toContain('next'));

		// driver.js focusing a popover button must not keep the focus (Enter would press Close).
		document.querySelector<HTMLButtonElement>('#popover-close')!.focus();
		expect(document.activeElement).toBe(input);

		// The ready anchor disappears (submit disabled): the step goes back to the waiting state without Next.
		document.querySelector('[data-tour="mcp-token-submit"]')!.setAttribute('disabled', '');
		await vi.waitFor(() => expect(driverHarness.highlight.mock.calls.at(-1)![0].popover.showButtons).not.toContain('next'));
		document.querySelector('[data-tour="mcp-token-submit"]')!.removeAttribute('disabled');
		await vi.waitFor(() => expect(driverHarness.highlight.mock.calls.at(-1)![0].popover.showButtons).toContain('next'));
	});

	it('swallows the next step\'s click target on an information step and releases it on its own step', async () => {
		document.body.innerHTML = '<div data-tour="database-backups-created"><button data-tour="database-backups-delete">delete</button></div>';
		const remove = document.querySelector<HTMLButtonElement>('[data-tour="database-backups-delete"]')!;
		const opened = vi.fn();
		remove.addEventListener('click', opened);

		void startTour('database-backups', 3);
		await vi.waitFor(() => expect(driverHarness.highlight.mock.calls.at(-1)![0].popover.showButtons).toContain('next'));
		remove.click();
		// Info step: the delete would open a confirm dialog behind the overlay, so the click never reaches the page.
		expect(opened).not.toHaveBeenCalled();
		expect(readPersistedTour()).toEqual({ tourId: 'database-backups', stepIndex: 3 });

		stopTour();
		void startTour('database-backups', 4);
		await vi.waitFor(() => expect(driverHarness.highlight).toHaveBeenLastCalledWith(
			expect.objectContaining({ element: '[data-tour="database-backups-delete"]' }),
		));
		remove.click();
		expect(opened).toHaveBeenCalledOnce();
		await vi.waitFor(() => expect(readPersistedTour()).toEqual({ tourId: 'database-backups', stepIndex: 5 }));
	});

	it('leaves the wait at once when the highlighted target is removed', async () => {
		document.body.innerHTML = '<div data-tour="database-backups-created">row</div>';
		void startTour('database-backups', 3);
		await vi.waitFor(() => expect(driverHarness.highlight).toHaveBeenCalled());
		document.querySelector('[data-tour="database-backups-created"]')!.remove();
		// The 120 s settle timeout must not run first: the step moves off the missing target within vi.waitFor's 1 s.
		await vi.waitFor(() => expect(readPersistedTour()?.stepIndex).not.toBe(3));
	});
});
describe('header-aware reveal', () => {
	function nextFrame(): Promise<void> {
		const { promise, resolve } = Promise.withResolvers<void>();
		requestAnimationFrame(() => resolve());
		return promise;
	}

	function mount(startScroll: number, targetOffset: number) {
		document.body.innerHTML = '<div id="main-content"><div data-tour="admin-library-header"></div><div data-tour="admin-library-ready"></div></div>';
		const main = document.querySelector<HTMLElement>('#main-content')!;
		let scrollTop = startScroll;
		Object.defineProperty(main, 'scrollTop', {
			configurable: true,
			get: () => scrollTop,
			set: (value: number) => { scrollTop = Math.max(value, 0); },
		});
		const target = document.querySelector<HTMLElement>('[data-tour="admin-library-header"]')!;
		target.scrollIntoView = vi.fn();
		// Document position of the target is fixed; its viewport top follows the container scroll.
		target.getBoundingClientRect = () => ({ top: targetOffset - scrollTop, bottom: 0, left: 0, right: 0, width: 0, height: 0, x: 0, y: 0, toJSON: () => ({}) }) as DOMRect;
		return { main, setScroll: (value: number) => { scrollTop = value; } };
	}

	it('scrolls a target hidden behind the header back below it after driver.js has re-scrolled', async () => {
		const { main, setScroll } = mount(575, 540);
		// driver.js re-scrolls inside highlight() and puts the target top at -35.
		driverHarness.highlight.mockImplementationOnce(() => setScroll(575));
		await startTour('admin-library');
		await vi.waitFor(() => expect(driverHarness.refresh).toHaveBeenCalled());
		// Target viewport top is now at least 56px (header 48 + 8).
		expect(540 - main.scrollTop).toBeGreaterThanOrEqual(56);
	});

	it('leaves the scroll position and overlay alone when the target already sits below the header', async () => {
		const { main } = mount(0, 200);
		await startTour('admin-library');
		await nextFrame();
		expect(main.scrollTop).toBe(0);
		expect(driverHarness.refresh).not.toHaveBeenCalled();
	});

	it('does not touch the container after the tour moved to another step or stopped', async () => {
		const { main } = mount(575, 540);
		await startTour('admin-library');
		const settled = main.scrollTop;
		stopTour();
		await nextFrame();
		expect(main.scrollTop).toBe(settled);
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
