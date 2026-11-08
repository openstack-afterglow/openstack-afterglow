import { goto } from '$app/navigation';
import type { Driver, PopoverDOM, State } from 'driver.js';
import { tick } from 'svelte';
import { getTour, TOUR_STORAGE_KEY, type TourDefinition, type TourId } from './tours';
import { canStartTour } from './access';
import { tutorialViewport } from './viewport';
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

const activityListeners = new Set<(active: boolean) => void>();

/** Observe both edges synchronously, including a start/stop inside one await. */
export function onTourActivityChange(listener: (active: boolean) => void): () => void {
	activityListeners.add(listener);
	return () => { activityListeners.delete(listener); };
}

function notifyTourActivity(): void {
	for (const listener of activityListeners) {
		try {
			listener(isTourActive());
		} catch {
			// Diagnostic observers must not interrupt the tutorial's lifecycle.
		}
	}
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
	// Mobile has no tutorials; this also stops saved-tour resume and ?tour= deep links.
	if (!tutorialViewport.current) return false;
	// Real-administrator tours never start for the synthetic tutorial admin or an unverified session.
	if (!canStartTour(tourId)) return false;
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
	notifyTourActivity();
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
	// Elements matching `rewindOnNew` that exist right now are stale (an earlier failure still on screen: the
	// page's own submit handler runs after the capture listener that advanced the tour). Only an element that
	// appears later signals a failure of THIS attempt. Taken before any await, so before that handler runs.
	const staleRewind = step.rewindOnNew ? new Set(document.querySelectorAll(step.rewindOnNew)) : null;

	currentIndex = index;
	persistTour(tour.id, index);

	if (step.route && !matchesCurrentRoute(step.route)) {
		try {
			await goto(step.route);
		} catch {
			// mockup 레이어의 beforeNavigate가 쿼리를 붙여 재시도할 수 있음 — 요소 대기로 흡수
		}
		if (d !== driverInstance || currentTour !== tour || serial !== showSerial) return;
	}

	const timeout = step.waitTimeoutMs ?? (index === 0 ? 8000 : 3000);

	const isLast = index === tour.steps.length - 1;
	const clickDriven = step.advanceOn === 'click';
	const wizardDriven = step.advanceOn === 'wizard';
	// True while a readyElement settle anchor is pending: the target is highlighted but the step must not advance.
	let settling = false;
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
				if (settling) {
					// The click would act on a resource that has not settled yet (token issue, revoke): swallow it.
					event.preventDefault();
					event.stopPropagation();
					return;
				}
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

	// An information step (Next button) highlights a region that can contain the NEXT step's click target (the
	// delete button of the row just created). Acting on it early opens its confirm dialog behind the overlay with
	// the tour popover inert, which a mouse-only user cannot leave. Swallow that click until its own step.
	const upcoming = !clickDriven && !wizardDriven ? tour.steps[index + 1] : undefined;
	const upcomingSelector = upcoming?.advanceOn === 'click' ? (upcoming.advanceElement ?? upcoming.element) : null;
	if (upcomingSelector) {
		const guardUpcoming = (event: Event) => {
			if (event.target instanceof Element && event.target.closest(upcomingSelector)) {
				event.preventDefault();
				event.stopPropagation();
			}
		};
		document.addEventListener('click', guardUpcoming, { capture: true });
		const previousCleanup = clickCleanup;
		clickCleanup = () => {
			previousCleanup?.();
			document.removeEventListener('click', guardUpcoming, { capture: true });
		};
	}

	if (step.readOnly) {
		// Read-only steps may highlight a block that contains live controls (revoke, add). Any activation inside the
		// target is swallowed in capture phase: mouse, touch, and keyboard Enter/Space all arrive as a click.
		const guardReadOnly = (event: Event) => {
			if (event.target instanceof Element && event.target.closest(step.element)) {
				event.preventDefault();
				event.stopPropagation();
				event.stopImmediatePropagation();
			}
		};
		document.addEventListener('click', guardReadOnly, { capture: true });
		const previousCleanup = clickCleanup;
		clickCleanup = () => {
			previousCleanup?.();
			document.removeEventListener('click', guardReadOnly, { capture: true });
		};
	}

	if (step.wizardStep != null || step.followWizard) {
		const onWizardStep = async (event: Event) => {
			const detail = (event as CustomEvent<{ step: number }>).detail;
			if (!detail) return;
			if (step.followWizard) {
				// Successful deployment resets the step immediately before closing the wizard.
				await tick();
				if (!await step.followWizard() || d !== driverInstance || currentTour !== tour || serial !== showSerial) return;
			}
			const mappedIndex = tour.steps.findIndex((st) => st.wizardStep === detail.step);
			if (mappedIndex >= 0 && mappedIndex !== currentIndex) {
				void moveTo(mappedIndex);
			}
		};
		window.addEventListener('afterglow:wizard-step', onWizardStep);
		wizardStepCleanup = () => window.removeEventListener('afterglow:wizard-step', onWizardStep);
	}
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

	const el = await waitForElement(step.element, timeout);
	// 대기 중 사용자가 투어를 닫았거나 더 새로운 스텝 전환이 시작된 경우
	if (d !== driverInstance || currentTour !== tour || serial !== showSerial) return;
	const rewindOrStop = () => {
		// 요소가 사라졌으면(페이지 이동으로 모달이 닫힘 등) 이전 스텝으로 되감는다.
		if (index > 0) {
			void showStep(index - 1, -1);
		} else {
			stopTour();
		}
	};
	if (!el) {
		rewindOrStop();
		return;
	}
	// Center the target before measuring it; instant scroll keeps the driver overlay in sync.
	el.scrollIntoView?.({ block: 'center', inline: 'nearest', behavior: 'instant' });

	const addStepCleanup = (cleanup: () => void) => {
		const previousCleanup = clickCleanup;
		clickCleanup = () => {
			previousCleanup?.();
			cleanup();
		};
	};
	// driver.js moves focus to a popover button whenever a popover renders (a step opens, Next appears), so
	// Enter or Space typed into the field the user is in would press Close. Hand focus back once when it was
	// inside the highlighted target, unless the user acts first. On typing steps (waitAllowsInput) whose
	// dialog focused something outside the target (its backdrop button), focus the target's first usable
	// field instead: the step exists to type there.
	const keepTypingFocus = () => {
		// Information steps (Next button) keep the default focus behaviour unless they hold a form field (the
		// announcement form is an information step the user types in). Interactive steps (click-driven,
		// wizard-driven, typing, or holding a form field) must never leave focus on a button that Space or Enter
		// would press: the popover's × (driver.js focuses it whenever a popover renders) or the target's own panel
		// × would end the tour or close the dialog on the first key.
		const formField = el.querySelector('textarea:not([disabled]), input:not([type="hidden"]):not([type="checkbox"]):not([type="radio"]):not([type="button"]):not([type="submit"]):not([type="search"]):not([disabled])');
		const selectOnlyForm = el.querySelector('select:not([disabled])') !== null && (el.closest('form, fieldset') !== null || el.querySelector('form, fieldset') !== null);
		const holdsForm = (formField !== null && formField.closest('[role="search"]') === null) || selectOnlyForm;
		const interactive = step.waitAllowsInput || clickDriven || wizardDriven || holdsForm;
		if (!interactive) return;
		// Text-like fields only (plus selects on typing steps): a checkbox or button must never receive the
		// automatic focus, and steps without a text field (confirm buttons, select-only forms) have none.
		const textLike = 'input:not([type="hidden"]):not([type="checkbox"]):not([type="radio"]):not([type="button"]):not([type="submit"]):not([disabled]), textarea:not([disabled])';
		const selector = step.waitAllowsInput ? `${textLike}, select:not([disabled])` : textLike;
		let active = document.activeElement;
		const inField = active instanceof HTMLElement && el.contains(active) && active.matches(`${selector}, select`);
		if (!inField) {
			const field = el.matches(selector) ? el : el.querySelector(selector);
			if (field instanceof HTMLElement) {
				field.focus({ preventScroll: true });
				active = document.activeElement;
			}
		}
		const keep = active instanceof HTMLElement && el.contains(active) && active.matches(`${selector}, select`) ? active : null;
		// A button of the target that holds focus (a panel's own ×) is dropped; the guard below keeps the popover
		// from taking it.
		if (!keep && active instanceof HTMLElement && el.contains(active) && active !== el) active.blur();
		const release = () => {
			document.removeEventListener('focusin', restore, true);
			document.removeEventListener('pointerdown', release, true);
			document.removeEventListener('keydown', release, true);
		};
		const restore = (event: FocusEvent) => {
			if (!(event.target instanceof HTMLElement) || !event.target.closest('.driver-popover')) return;
			release();
			if (keep?.isConnected) keep.focus({ preventScroll: true });
			else event.target.blur();
		};
		document.addEventListener('focusin', restore, true);
		document.addEventListener('pointerdown', release, true);
		document.addEventListener('keydown', release, true);
		// With focus on the bare page, Space would scroll the page and carry the highlighted target out of view.
		const swallowPageSpace = (event: KeyboardEvent) => {
			if (event.key === ' ' && (event.target === document.body || event.target === document.documentElement)) event.preventDefault();
		};
		document.addEventListener('keydown', swallowPageSpace, true);
		addStepCleanup(() => document.removeEventListener('keydown', swallowPageSpace, true));
		addStepCleanup(release);
	};
	// Previous is offered only when the previous step can be presented again: its target is on this route and
	// reachable (not hidden behind a modal's inert page), or it lives on another route. Otherwise it would
	// strand the user (open dialog over a covered opener) or do nothing (the target is already gone).
	const canGoBack = (): boolean => {
		if (index === 0) return false;
		const previousStep = tour.steps[index - 1];
		if (previousStep.route && !matchesCurrentRoute(previousStep.route)) return true;
		const previousEl = document.querySelector(previousStep.element);
		return previousEl !== null && previousEl.closest('[inert]') === null;
	};
	const highlightStep = (waiting: boolean) => {
		const back = canGoBack();
		d.highlight({
			element: step.element,
			popover: {
				side: step.popoverSide,
				title: t('engine.stepTitle', { title: step.title, current: index + 1, total: tour.steps.length }),
				description: step.description,
				// While the settle anchor is pending Next is withheld (the step cannot advance early).
				showButtons: waiting
					? back
						? ['previous', 'close']
						: ['close']
					: clickDriven
						? step.showPrevious && back
							? ['previous', 'close']
							: ['close']
						: wizardDriven
							? ['close']
							: index === 0
								? ['next', 'close']
								: back
									? ['next', 'previous', 'close']
									: ['next', 'close'],
				nextBtnText: t(isLast ? 'engine.complete' : 'engine.next'),
				prevBtnText: t('engine.previous'),
			},
		});
	};
	// Show the target at once. A settle anchor (readyElement: spinner gone, resource settled) is awaited
	// with this step's popover already visible, never with the previous step's popover left on screen.
	if (step.readyElement && !document.querySelector(step.readyElement)) {
		settling = true;
		// The target's own buttons act on unsettled state, so clicks inside it are swallowed unless the input that
		// ends the wait lives in it. A listener (not driver.js disableActiveInteraction, which can stay on the
		// element after a short wait) keeps this exact and removable.
		const blockClick = (event: Event) => {
			if (!step.waitAllowsInput && event.target instanceof Node && el.contains(event.target)) {
				event.preventDefault();
				event.stopPropagation();
			}
		};
		document.addEventListener('click', blockClick, { capture: true });
		const previousCleanup = clickCleanup;
		clickCleanup = () => {
			previousCleanup?.();
			document.removeEventListener('click', blockClick, { capture: true });
		};
		keepTypingFocus();
		highlightStep(true);
		// A dialog dismissed (Escape, Cancel) or a re-render during the wait must not leave the step stuck for the full timeout.
		const lost = Promise.withResolvers<null>();
		let rewindRequested = false;
		const check = () => {
			if (step.rewindOnNew && staleRewind && [...document.querySelectorAll(step.rewindOnNew)].some((node) => !staleRewind.has(node))) rewindRequested = true;
			if (rewindRequested || !el.isConnected) lost.resolve(null);
		};
		const lostObserver = new MutationObserver(check);
		lostObserver.observe(document.body, { childList: true, subtree: true });
		check();
		const ready = await Promise.race([waitForElement(step.readyElement, timeout), lost.promise]);
		lostObserver.disconnect();
		document.removeEventListener('click', blockClick, { capture: true });
		settling = false;
		if (d !== driverInstance || currentTour !== tour || serial !== showSerial) return;
		if (rewindRequested) {
			rewindOrStop();
			return;
		}
		if (!el.isConnected) {
			if (document.querySelector(step.element)) {
				// The list re-rendered while settling and replaced the target: present the step again.
				void showStep(index, direction);
			} else {
				const previous = presentPreviousStep(tour, index);
				void showStep(previous >= 0 ? previous : Math.max(index - 1, 0), -1);
			}
			return;
		}
		if (!ready) {
			rewindOrStop();
			return;
		}
	}
	keepTypingFocus();
	// Previous availability is evaluated when the popover renders. The previous target can vanish right after
	// (a dialog closing after the confirm click), which would leave a dead Previous button on screen.
	const shownBack = canGoBack();
	const readySelector = step.readyElement && step.waitAllowsInput ? step.readyElement : null;
	highlightStep(false);
	// Re-check on DOM mutations and on input/change events: property-only changes (a re-checked box bound with
	// bind:checked) fire no mutation. An input that became incomplete must withdraw Next (a stale Next would
	// continue to a step whose control is disabled); a changed Previous availability must re-render the buttons.
	const recheck = () => {
		if (d !== driverInstance || serial !== showSerial) return;
		if (!el.isConnected) return;
		if ((readySelector !== null && !document.querySelector(readySelector)) || canGoBack() !== shownBack) {
			void showStep(index, direction);
		}
	};
	// driver.js redraws its overlay only on window scroll/resize, but the app scrolls inside #main-content (and
	// dialogs scroll themselves): without this the cut-out stays where the target used to be.
	let scrollFrame = 0;
	const syncOnScroll = () => {
		if (scrollFrame) return;
		scrollFrame = requestAnimationFrame(() => {
			scrollFrame = 0;
			if (d === driverInstance && serial === showSerial && el.isConnected) d.refresh();
		});
	};
	document.addEventListener('scroll', syncOnScroll, { capture: true, passive: true });
	addStepCleanup(() => {
		document.removeEventListener('scroll', syncOnScroll, true);
		if (scrollFrame) cancelAnimationFrame(scrollFrame);
	});
	const stateWatch = new MutationObserver(recheck);
	stateWatch.observe(document.body, { childList: true, subtree: true, attributes: true });
	document.addEventListener('input', recheck, true);
	document.addEventListener('change', recheck, true);
	addStepCleanup(() => {
		stateWatch.disconnect();
		document.removeEventListener('input', recheck, true);
		document.removeEventListener('change', recheck, true);
	});
	// driver.js scrolls the target again inside highlight() when it is not fully inside the window and
	// would undo any earlier adjustment, so the header-aware reveal runs after it and re-syncs the overlay.
	requestAnimationFrame(() => {
		if (d !== driverInstance || serial !== showSerial || !el.isConnected) return;
		if (revealBelowHeader(el)) d.refresh();
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
		// 폼/확인 단계는 대화상자를 하이라이트한다. ESC·취소·스크림으로 대화상자가 닫히면 같은 스텝을
		// 다시 기다리지 않고(빈 하이라이트로 수 초 멈춤) 지금 화면에 있는 직전 스텝(대개 여는 버튼)으로 되감는다.
		const dialog = target.closest<HTMLElement>('[role="dialog"], [role="alertdialog"], dialog');
		const mo = new MutationObserver(() => {
			if (d !== driverInstance || serial !== showSerial) {
				mo.disconnect();
				return;
			}
			if (!target.isConnected) {
				mo.disconnect();
				const dismissed = dialog !== null && !dialog.isConnected && !document.querySelector(step.element);
				const previous = dismissed ? presentPreviousStep(tour, index) : -1;
				void showStep(previous >= 0 ? previous : index, -1);
			}
		});
		mo.observe(document.body, { childList: true, subtree: true });
		observers.push(() => mo.disconnect());
	}
	resizeCleanup = () => observers.forEach((dispose) => dispose());
}

function matchesCurrentRoute(route: string): boolean {
	const targetUrl = new URL(route, window.location.href);
	const currentUrl = new URL(window.location.href);
	return currentUrl.pathname === targetUrl.pathname
		&& [...new Set(targetUrl.searchParams.keys())].every(key => {
			const expected = targetUrl.searchParams.getAll(key);
			const actual = currentUrl.searchParams.getAll(key);
			return expected.length === actual.length && expected.every((value, position) => actual[position] === value);
		});
}

/** Nearest earlier step whose target is visible on the current route right now, or -1. */
function presentPreviousStep(tour: TourDefinition, index: number): number {
	for (let previous = index - 1; previous >= 0; previous -= 1) {
		const step = tour.steps[previous];
		if (step.route && !matchesCurrentRoute(step.route)) continue;
		const candidate = document.querySelector<HTMLElement>(step.element);
		if (candidate && candidate.getClientRects().length > 0) return previous;
	}
	return -1;
}

// The app shell scrolls #main-content, which sits under the fixed 48px header. Centering a target can
// leave its top behind the header; scrolling the container back up reveals it. Returns whether it moved.
const HEADER_PX = 48;

function revealBelowHeader(target: HTMLElement): boolean {
	const hidden = HEADER_PX + 8 - target.getBoundingClientRect().top;
	if (hidden <= 0) return false;
	const scroller = target.closest<HTMLElement>('#main-content') ?? document.querySelector<HTMLElement>('#main-content');
	if (!scroller) return false;
	const before = scroller.scrollTop;
	scroller.scrollTop = before - hidden;
	return scroller.scrollTop !== before;
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
		if (d) notifyTourActivity();
		d?.destroy();
	} finally {
		stopping = false;
	}
}
