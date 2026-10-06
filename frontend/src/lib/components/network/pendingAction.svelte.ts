/**
 * Network detail controllers expose one shared `saving` flag for every mutation. This remembers
 * which control started the current request so only that control shows activity, and only while the
 * shared flag confirms the request is in flight (a confirmation dialog before the request keeps the
 * flag false, so nothing spins while the user is still deciding).
 */
export function createPendingAction() {
	let key = $state<string | null>(null);
	return {
		isActive(candidate: string, inFlight: boolean): boolean {
			return inFlight && key === candidate;
		},
		async run<T>(candidate: string, action: () => T | Promise<T>): Promise<T> {
			key = candidate;
			try {
				return await action();
			} finally {
				if (key === candidate) key = null;
			}
		},
	};
}
