import { untrack } from 'svelte';
import { createCoalescedRefresh } from './coalescedRefresh';

interface AutoRefreshOptions {
	storageKey: string;
	defaultActive?: boolean;
	defaultInterval?: number;
	intervalOptions?: number[];
	invokeOnMount?: boolean;
}

export interface AutoRefreshController {
	active: boolean;
	intervalSeconds: number;
	readonly intervalOptions: number[];
	setBoost(seconds: number | null): void;
	refresh(): Promise<void>;
}

export function createAutoRefresh(
	fn: (force?: boolean) => void | Promise<void>,
	options: AutoRefreshOptions,
): AutoRefreshController {
	const {
		storageKey,
		defaultActive = true,
		defaultInterval = 30,
		intervalOptions = [10, 15, 30, 60],
		invokeOnMount = true
	} = options;

	const state = $state({
		active: defaultActive,
		intervalSeconds: defaultInterval,
		intervalOptions
	});

	// 비영속 boost: setBoost(seconds) 로 임시 가속, setBoost(null) 로 해제
	let _boost = $state<number | null>(null);
	function setBoost(seconds: number | null) { _boost = seconds; }

	// One queue owns timer and manual rounds. A manual refresh arriving during an
	// automatic round gets one subsequent round; timer ticks only join active work.
	const refresh = createCoalescedRefresh(async (force) => { await fn(force); });
	let disposed = false;
	let schedule: (() => void) | null = null;
	let pause: (() => void) | null = null;
	async function tick(force = false): Promise<void> {
		pause?.();
		try {
			await refresh.run(force);
		} finally {
			if (!disposed) schedule?.();
		}
	}
	$effect(() => () => {
		disposed = true;
		pause?.();
		refresh.dispose();
	});

	// Restore saved preferences from localStorage (client-only via $effect)
	$effect(() => {
		const savedActive = localStorage.getItem(`autoRefresh.${storageKey}.active`);
		const savedInterval = localStorage.getItem(`autoRefresh.${storageKey}.interval`);
		if (savedActive !== null) state.active = savedActive === 'true';
		if (savedInterval !== null) {
			const n = parseInt(savedInterval, 10);
			if (!isNaN(n) && intervalOptions.includes(n)) state.intervalSeconds = n;
		}
	});

	// Persist preferences whenever they change
	$effect(() => {
		localStorage.setItem(`autoRefresh.${storageKey}.active`, String(state.active));
		localStorage.setItem(`autoRefresh.${storageKey}.interval`, String(state.intervalSeconds));
	});

	// Delay from completion, not from dispatch. Slow providers cannot create a
	// back-to-back round at the next fixed wall-clock tick. Preference/boost
	// changes re-arm the timer without repeating the initial load.
	let initialized = false;
	$effect(() => {
		const active = state.active;
		const effectiveMs = (_boost ?? state.intervalSeconds) * 1000;
		const initial = !initialized;
		initialized = true;
		let stopped = false;
		let timerId: number | undefined;
		const available = () => active && !stopped && !document.hidden && navigator.onLine !== false;
		function stop() {
			window.clearTimeout(timerId);
			timerId = undefined;
		}
		function start() {
			stop();
			if (available()) timerId = window.setTimeout(run, effectiveMs);
		}
		function run() {
			if (available()) void untrack(() => tick()).catch(() => {});
		}
		function onAvailability() {
			stop();
			if (available()) run();
		}
		schedule = start;
		pause = stop;
		if (available() && initial && invokeOnMount) run();
		else start();
		document.addEventListener('visibilitychange', onAvailability);
		window.addEventListener('online', onAvailability);
		window.addEventListener('offline', onAvailability);
		return () => {
			stopped = true;
			stop();
			if (schedule === start) schedule = null;
			if (pause === stop) pause = null;
			document.removeEventListener('visibilitychange', onAvailability);
			window.removeEventListener('online', onAvailability);
			window.removeEventListener('offline', onAvailability);
		};
	});

	return {
		get active() { return state.active; },
		set active(v: boolean) { state.active = v; },
		get intervalSeconds() { return state.intervalSeconds; },
		set intervalSeconds(v: number) { state.intervalSeconds = v; },
		get intervalOptions() { return state.intervalOptions; },
		setBoost,
		refresh: () => tick(true),
	};
}
