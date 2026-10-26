export interface CoalescedRefresh {
	run(force?: boolean): Promise<void>;
	invalidate(): Promise<void>;
	dispose(): void;
}

/**
 * Serializes visible refreshes while guaranteeing one forced round after a
 * successful mutation. Automatic callers join in-flight work; manual callers
 * bypass cache once, without racing the currently visible result.
 */
export function createCoalescedRefresh(task: (force: boolean) => Promise<void>): CoalescedRefresh {
	type Cycle = {
		force: boolean;
		startedMutationEpoch: number;
		promise: Promise<void>;
		resolve: () => void;
		reject: (error: unknown) => void;
	};
	type InvalidationWaiter = {
		epoch: number;
		resolve: () => void;
		reject: (error: unknown) => void;
	};

	let active: Cycle | null = null;
	let queuedForce: Cycle | null = null;
	let mutationEpoch = 0;
	let invalidationWaiters: InvalidationWaiter[] = [];
	let disposed = false;

	function createCycle(force: boolean): Cycle {
		let resolve!: () => void;
		let reject!: (error: unknown) => void;
		const promise = new Promise<void>((res, rej) => {
			resolve = res;
			reject = rej;
		});
		void promise.catch(() => {});
		return { force, startedMutationEpoch: 0, promise, resolve, reject };
	}

	function resolveInvalidations(startedMutationEpoch: number) {
		const pending: InvalidationWaiter[] = [];
		for (const waiter of invalidationWaiters) {
			if (waiter.epoch <= startedMutationEpoch) waiter.resolve();
			else pending.push(waiter);
		}
		invalidationWaiters = pending;
	}

	function rejectInvalidations(error: unknown) {
		for (const waiter of invalidationWaiters) waiter.reject(error);
		invalidationWaiters = [];
	}

	function start(cycle: Cycle) {
		active = cycle;
		cycle.startedMutationEpoch = mutationEpoch;

		let taskPromise: Promise<void>;
		try {
			taskPromise = Promise.resolve(task(cycle.force));
		} catch (error) {
			taskPromise = Promise.reject(error);
		}

		void taskPromise.then(
			() => finish(cycle, true),
			(error: unknown) => finish(cycle, false, error),
		);
	}

	function finish(cycle: Cycle, succeeded: boolean, error?: unknown) {
		if (active !== cycle) return;
		active = null;

		if (succeeded) {
			cycle.resolve();
			if (cycle.force) resolveInvalidations(cycle.startedMutationEpoch);
		} else {
			cycle.reject(error);
		}

		const next = queuedForce;
		queuedForce = null;
		if (next) {
			start(next);
			return;
		}

		if (!succeeded && invalidationWaiters.length > 0) rejectInvalidations(error);
	}

	function run(force = false): Promise<void> {
		if (disposed) return Promise.resolve();
		if (!active) {
			const cycle = createCycle(force);
			start(cycle);
			return cycle.promise;
		}

		if (!force || active.force) return active.promise;

		if (!queuedForce) queuedForce = createCycle(true);
		return queuedForce.promise;
	}

	function invalidate(): Promise<void> {
		if (disposed) return Promise.resolve();
		const epoch = ++mutationEpoch;
		const promise = new Promise<void>((resolve, reject) => {
			invalidationWaiters.push({ epoch, resolve, reject });
		});

		if (!active) {
			const cycle = createCycle(true);
			start(cycle);
		} else if (!queuedForce) {
			queuedForce = createCycle(true);
		}

		return promise;
	}

	function dispose() {
		disposed = true;
		queuedForce?.resolve();
		queuedForce = null;
		for (const waiter of invalidationWaiters) waiter.resolve();
		invalidationWaiters = [];
	}

	return { run, invalidate, dispose };
}
