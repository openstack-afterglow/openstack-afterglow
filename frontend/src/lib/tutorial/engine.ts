import { goto } from '$app/navigation';
import type { Driver, PopoverDOM, State } from 'driver.js';
import { tick } from 'svelte';
import { getTour, TOUR_STORAGE_KEY, type TourDefinition, type TourId } from './tours';
import { t } from '$lib/i18n/ns/tutorial';

export interface PersistedTourState {
	tourId: TourId;
	stepIndex: number;
}

export function readPersistedTour(): PersistedTourState | null {
	if (typeof sessionStorage === 'undefined') return null;
	try {
		const raw = sessionStorage.getItem(TOUR_STORAGE_KEY);
		if (!raw) return null;
		const parsed = JSON.parse(raw) as PersistedTourState;
		const tour = getTour(parsed.tourId);
		if (!tour || !Number.isInteger(parsed.stepIndex)) return null;
		if (parsed.stepIndex < 0 || parsed.stepIndex >= tour.steps.length) return null;
		return parsed;
	} catch {
		return null;
	}
}

export function clearPersistedTour(): void {
	if (typeof sessionStorage === 'undefined') return;
	sessionStorage.removeItem(TOUR_STORAGE_KEY);
}

function persistTour(tourId: TourId, stepIndex: number): void {
	if (typeof sessionStorage === 'undefined') return;
	sessionStorage.setItem(TOUR_STORAGE_KEY, JSON.stringify({ tourId, stepIndex }));
}

export async function waitForElement(
	selector: string,
	timeoutMs = 8000,
	pollMs = 120,
): Promise<HTMLElement | null> {
	const deadline = Date.now() + timeoutMs;
	for (;;) {
		const el = document.querySelector<HTMLElement>(selector);
		if (el && el.getClientRects().length > 0) return el;
		if (Date.now() >= deadline) return el;
		await new Promise((resolve) => setTimeout(resolve, pollMs));
	}
}

let driverInstance: Driver | null = null;
let currentTour: TourDefinition | null = null;
let currentIndex = 0;
let stopping = false;
let clickCleanup: (() => void) | null = null;
let wizardStepCleanup: (() => void) | null = null;
let resizeCleanup: (() => void) | null = null;
// 동시에 여러 showStep이 진행되지 않도록 최신 호출만 유효화한다.
let showSerial = 0;

export function isTourActive(): boolean {
	return driverInstance !== null;
}

/**
 * 투어를 끝까지 완주했을 때만 발행한다(취소/× /ESC 로 인한 stopTour 에서는 발행 안 함).
 * 상태 스토어가 이 이벤트를 수신해 서버에 'completed' 로 기록한다.
 */
function fireTourComplete(tourId: TourId): void {
	if (typeof window === 'undefined') return;
	window.dispatchEvent(new CustomEvent('afterglow:tour-complete', { detail: { tourId } }));
}

export async function startTour(tourId: TourId, fromStep = 0): Promise<boolean> {
	if (typeof window === 'undefined') return false;
	const tour = getTour(tourId);
	if (!tour) return false;
	stopTour();
	const { driver } = await import('driver.js');
	currentTour = tour;
	driverInstance = driver({
		animate: true,
		overlayOpacity: 0.65,
		stagePadding: 6,
		// 튜토리얼 중에도 페이지/패널 스크롤을 허용한다(driver가 body에 driver-no-scroll(overflow:hidden)을 걸지 않도록).
		allowScroll: true,
		// 하이라이트 밖(dim 영역) 클릭으로 투어가 사라지지 않게 한다. ESC/× 버튼으로만 종료.
		allowClose: false,
		disableActiveInteraction: false,
		popoverClass: 'afterglow-tour',
		nextBtnText: t('engine.next'),
		prevBtnText: t('engine.previous'),
		onPopoverRender: (popover) => updatePopoverMessages(popover),
		onNextClick: () => void moveTo(currentIndex + 1),
		onPrevClick: () => void moveTo(currentIndex - 1),
		onCloseClick: () => stopTour(),
		onDestroyStarted: () => stopTour(),
	});
	const startIndex = Math.min(Math.max(fromStep, 0), tour.steps.length - 1);
	await showStep(startIndex);
	return true;
}

/**
 * 라우트 변경 후 현재 스텝을 다시 앵커링한다.
 * 대상 요소가 사라졌으면(모달 닫힘 등) 유효한 이전 스텝으로 되감는다.
 */
export function refreshTourAnchor(): void {
	if (!driverInstance || !currentTour) return;
	void showStep(currentIndex);
}

/** Refresh only text when the root controller observes a locale change; never replay step actions. */
export function refreshTourMessages(): void {
	if (!driverInstance || !currentTour) return;
	const { popover } = driverInstance.getState() as State;
	if (!popover) return;
	updatePopoverMessages(popover);
	driverInstance.refresh();
}

function updatePopoverMessages(popover: PopoverDOM): void {
	if (!currentTour) return;
	const step = currentTour.steps[currentIndex];
	popover.title.textContent = t('engine.stepTitle', {
		title: step.title,
		current: currentIndex + 1,
		total: currentTour.steps.length,
	});
	popover.description.textContent = step.description;
	popover.nextButton.textContent = t(currentIndex === currentTour.steps.length - 1 ? 'engine.complete' : 'engine.next');
	popover.previousButton.textContent = t('engine.previous');
	popover.closeButton.setAttribute('aria-label', t('engine.close'));
}

async function moveTo(index: number): Promise<void> {
	if (!currentTour) return;
	if (index < 0) return;
	if (index >= currentTour.steps.length) {
		const finishedId = currentTour.id;
		stopTour();
		fireTourComplete(finishedId);
		return;
	}
	await showStep(index, index >= currentIndex ? 1 : -1);
}

async function showStep(index: number, direction: 1 | -1 = 1): Promise<void> {
	const tour = currentTour;
	const d = driverInstance;
	if (!tour || !d) return;
	const serial = ++showSerial;
	cleanupClickListener();
	const step = tour.steps[index];

	currentIndex = index;
	persistTour(tour.id, index);

	if (step.route && window.location.pathname !== step.route) {
		try {
			await goto(step.route);
		} catch {
			// mockup 레이어의 beforeNavigate가 쿼리를 붙여 재시도할 수 있음 — 요소 대기로 흡수
		}
		if (d !== driverInstance || currentTour !== tour || serial !== showSerial) return;
	}

	const timeout = step.waitTimeoutMs ?? (index === 0 ? 8000 : 3000);

	// 숨겨진 탭 내부가 settlement anchor인 경우 먼저 탭을 연다.
	if (step.beforeReady) {
		await tick();
		await step.beforeReady();
		if (d !== driverInstance || currentTour !== tour || serial !== showSerial) return;
	}

	// 재개된 optional step은 부모 목록의 로딩/빈/오류 상태가 확정된 뒤 skipIf를 평가한다.
	if (step.skipReadyElement) {
		await waitForElement(step.skipReadyElement, timeout);
		if (d !== driverInstance || currentTour !== tour || serial !== showSerial) return;
	}

	// route 이동과 settlement 대기가 플러시된 뒤 transient UI를 복원한다.
	if (step.prepare) {
		await tick();
		await step.prepare();
		if (d !== driverInstance || currentTour !== tour || serial !== showSerial) return;
	}

	// 조건부 step: 현재 화면 상태에 해당 단계가 없으면 진행 방향을 유지한 채 건너뛴다.
	if (step.skipIf?.()) {
		const next = index + direction;
		if (next < 0) return;
		if (next >= tour.steps.length) {
			const finishedId = tour.id;
			stopTour();
			fireTourComplete(finishedId);
			return;
		}
		void showStep(next, direction);
		return;
	}

	let el = await waitForElement(step.element, timeout);
	// 로딩 스피너 등이 걷히고 실제 콘텐츠가 나타난 뒤에 하이라이트한다
	if (el && step.readyElement) {
		const ready = await waitForElement(step.readyElement, timeout);
		if (!ready) el = null;
	}
	// 대기 중 사용자가 투어를 닫았거나 더 새로운 스텝 전환이 시작된 경우
	if (d !== driverInstance || currentTour !== tour || serial !== showSerial) return;
	if (!el) {
		// 요소가 사라졌으면(페이지 이동으로 모달이 닫힘 등) 이전 스텝으로 되감는다.
		if (index > 0) {
			void showStep(index - 1, -1);
		} else {
			stopTour();
		}
		return;
	}

	const isLast = index === tour.steps.length - 1;
	const clickDriven = step.advanceOn === 'click';
	const wizardDriven = step.advanceOn === 'wizard';

	if (clickDriven || step.backElement || step.cancelElement) {
		// 진행/후진/취소 트리거는 하이라이트 요소와 다를 수 있다(예: 폼 전체 하이라이트 + 생성/이전/취소 버튼).
		// document 캡처 위임: 하이라이트 표시 전에 무장되고, 대상 노드가 리렌더로 교체돼도 동작한다.
		const advanceSelector = clickDriven ? (step.advanceElement ?? step.element) : null;
		const backSelector = step.backElement ?? null;
		const cancelSelector = step.cancelElement ?? null;
		const handler = (event: Event) => {
			const target = event.target as Element | null;
			if (!target?.closest) return;
			if (cancelSelector && target.closest(cancelSelector)) {
				stopTour();
			} else if (advanceSelector && target.closest(advanceSelector)) {
				cleanupClickListener();
				void moveTo(index + 1);
			} else if (backSelector && target.closest(backSelector)) {
				cleanupClickListener();
				void moveTo(index - 1);
			}
		};
		document.addEventListener('click', handler, { capture: true });
		clickCleanup = () => document.removeEventListener('click', handler, { capture: true });
	}

	if (step.wizardStep != null) {
		const onWizardStep = (event: Event) => {
			const detail = (event as CustomEvent<{ step: number }>).detail;
			if (!detail) return;
			const mappedIndex = tour.steps.findIndex((st) => st.wizardStep === detail.step);
			if (mappedIndex >= 0 && mappedIndex !== currentIndex) {
				void moveTo(mappedIndex);
			}
		};
		window.addEventListener('afterglow:wizard-step', onWizardStep);
		wizardStepCleanup = () => window.removeEventListener('afterglow:wizard-step', onWizardStep);
	}

	d.highlight({
		element: step.element,
		popover: {
			title: t('engine.stepTitle', { title: step.title, current: index + 1, total: tour.steps.length }),
			description: step.description,
			showButtons: clickDriven
				? step.showPrevious && index > 0
					? ['previous', 'close']
					: ['close']
				: wizardDriven
					? ['close']
					: index === 0
						? ['next', 'close']
						: ['next', 'previous', 'close'],
			nextBtnText: t(isLast ? 'engine.complete' : 'engine.next'),
			prevBtnText: t('engine.previous'),
		},
	});

	// 콘텐츠가 뒤늦게 로드되어 대상 크기가 바뀌면 하이라이트/팝오버 위치를 재계산하고,
	// 대상이 DOM에서 사라지면(모달 취소/ESC 등) 유효한 이전 스텝으로 자동 되감는다.
	const observers: Array<() => void> = [];
	if (typeof ResizeObserver !== 'undefined') {
		const ro = new ResizeObserver(() => {
			if (d === driverInstance && serial === showSerial) d.refresh();
		});
		ro.observe(el);
		observers.push(() => ro.disconnect());
	}
	if (typeof MutationObserver !== 'undefined') {
		const target = el;
		const mo = new MutationObserver(() => {
			if (d !== driverInstance || serial !== showSerial) {
				mo.disconnect();
				return;
			}
			if (!target.isConnected) {
				mo.disconnect();
				void showStep(index, -1);
			}
		});
		mo.observe(document.body, { childList: true, subtree: true });
		observers.push(() => mo.disconnect());
	}
	resizeCleanup = () => observers.forEach((dispose) => dispose());
}

function cleanupClickListener(): void {
	clickCleanup?.();
	clickCleanup = null;
	wizardStepCleanup?.();
	wizardStepCleanup = null;
	resizeCleanup?.();
	resizeCleanup = null;
}

export function stopTour(): void {
	if (stopping) return;
	stopping = true;
	try {
		showSerial += 1;
		cleanupClickListener();
		clearPersistedTour();
		const d = driverInstance;
		driverInstance = null;
		currentTour = null;
		currentIndex = 0;
		d?.destroy();
	} finally {
		stopping = false;
	}
}
