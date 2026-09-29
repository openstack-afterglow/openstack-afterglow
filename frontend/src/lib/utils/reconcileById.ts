// Waygate list responses are JSON records. Preserve row identity when a fresh
// response carries the same values, including nested fields such as allowed_ips.
export function sameJsonValue(left: unknown, right: unknown): boolean {
	if (Object.is(left, right)) return true;
	if (left === null || right === null || typeof left !== 'object' || typeof right !== 'object') return false;
	if (Array.isArray(left) || Array.isArray(right)) {
		if (!Array.isArray(left) || !Array.isArray(right) || left.length !== right.length) return false;
		for (let index = 0; index < left.length; index++) {
			if (!sameJsonValue(left[index], right[index])) return false;
		}
		return true;
	}
	const a = left as Record<string, unknown>;
	const b = right as Record<string, unknown>;
	let keys = 0;
	for (const key in a) {
		if (!Object.hasOwn(a, key)) continue;
		if (!Object.hasOwn(b, key) || !sameJsonValue(a[key], b[key])) return false;
		keys++;
	}
	for (const key in b) {
		if (Object.hasOwn(b, key)) keys--;
	}
	return keys === 0;
}

export function reconcileById<T extends { id: string | number }>(previous: T[], next: T[]): T[] {
	if (previous.length === next.length) {
		let unchanged = true;
		for (let index = 0; index < previous.length; index++) {
			if (previous[index].id !== next[index].id || !sameJsonValue(previous[index], next[index])) {
				unchanged = false;
				break;
			}
		}
		if (unchanged) return previous;
	}
	if (!previous.length) return next;
	const oldById = new Map(previous.map((item) => [item.id, item]));
	return next.map((item) => {
		const old = oldById.get(item.id);
		return old && sameJsonValue(old, item) ? old : item;
	});
}
