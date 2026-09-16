import { writable } from 'svelte/store';

export type ToastType = 'success' | 'error' | 'warning' | 'info';

export interface ToastAction {
	label: string;
	onClick: () => void;
}

export interface Toast {
	id: string;
	type: ToastType;
	message: string;
	duration: number;
	action?: ToastAction;
}

function createToastStore() {
	const { subscribe, update } = writable<Toast[]>([]);

	interface Countdown {
		/** null 이면 hover/focus 로 얼어 있는 상태. */
		handle: ReturnType<typeof setTimeout> | null;
		remaining: number;
		startedAt: number;
	}
	const countdowns = new Map<string, Countdown>();
	/** `${toastId}:hover` / `${toastId}:focus`. 가리킨 채로 언마운트되면 mouseleave 가 보장되지
	    않으므로 제거 시 해당 토스트의 키를 직접 버린다. */
	const holders = new Set<string>();

	function arm(id: string, remaining: number) {
		countdowns.set(id, {
			handle: setTimeout(() => removeToast(id), remaining),
			remaining,
			startedAt: Date.now(),
		});
	}

	function resumeAll() {
		for (const [id, c] of countdowns) if (c.handle === null) arm(id, c.remaining);
	}

	function addToast(type: ToastType, message: string, duration = 4000, action?: ToastAction): string {
		const id = crypto.randomUUID();
		// WCAG 2.2.1 의 "turn off": 오류는 실패한 작업과 해결 단계를 담으므로(DESIGN.md) 시간 제한을
		// 두지 않고 사용자가 직접 닫는다. 나머지는 pause/resume 으로 "adjust" 요건을 만족한다.
		const effective = type === 'error' ? 0 : duration;
		update(toasts => [...toasts, { id, type, message, duration: effective, action }]);
		if (effective <= 0) return id;
		if (holders.size > 0) countdowns.set(id, { handle: null, remaining: effective, startedAt: Date.now() });
		else arm(id, effective);
		return id;
	}

	function removeToast(id: string) {
		const c = countdowns.get(id);
		if (c && c.handle !== null) clearTimeout(c.handle);
		countdowns.delete(id);
		const hadHover = holders.delete(`${id}:hover`);
		const hadFocus = holders.delete(`${id}:focus`);
		update(toasts => toasts.filter(t => t.id !== id));
		if ((hadHover || hadFocus) && holders.size === 0) resumeAll();
	}

	/** 포인터가 어떤 토스트 위에 있거나 포커스가 그 안에 있는 동안 모든 카운트다운을 멈춘다. */
	function pause(id: string, source: 'hover' | 'focus') {
		const wasIdle = holders.size === 0;
		holders.add(`${id}:${source}`);
		if (!wasIdle) return;
		const now = Date.now();
		for (const c of countdowns.values()) {
			if (c.handle === null) continue;
			clearTimeout(c.handle);
			c.handle = null;
			c.remaining = Math.max(0, c.remaining - (now - c.startedAt));
		}
	}

	/** 마지막 해제가 남은 시간만큼 다시 무장한다. */
	function resume(id: string, source: 'hover' | 'focus') {
		if (!holders.delete(`${id}:${source}`)) return;
		if (holders.size === 0) resumeAll();
	}

	return {
		subscribe,
		success: (msg: string, duration?: number, action?: ToastAction) => addToast('success', msg, duration, action),
		error: (msg: string, duration = 6000, action?: ToastAction) => addToast('error', msg, duration, action),
		warning: (msg: string, duration?: number, action?: ToastAction) => addToast('warning', msg, duration, action),
		info: (msg: string, duration?: number, action?: ToastAction) => addToast('info', msg, duration, action),
		remove: removeToast,
		pause,
		resume,
	};
}

export const toast = createToastStore();
