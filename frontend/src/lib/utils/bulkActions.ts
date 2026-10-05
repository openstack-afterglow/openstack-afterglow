import { t } from '$lib/i18n/ns/shared';

export type BulkMutationResult =
	| { id: string; ok: true }
	| { id: string; ok: false; error: string };

export function partitionBulkIds(
	selected: Iterable<string>,
	eligible: Iterable<string>,
): { eligible: string[]; skipped: string[] } {
	const eligibleIds = new Set(eligible);
	const applicable: string[] = [];
	const skipped: string[] = [];
	for (const id of selected) {
		if (eligibleIds.has(id)) applicable.push(id);
		else skipped.push(id);
	}
	return { eligible: applicable, skipped };
}

export async function executeBulkMutations(
	ids: readonly string[],
	mutate: (id: string) => Promise<unknown>,
	options: { concurrency?: number } = {},
): Promise<BulkMutationResult[]> {
	if (ids.length === 0) return [];

	const results = new Array<BulkMutationResult>(ids.length);
	const concurrency = Math.max(1, Math.floor(options.concurrency ?? 4));
	let nextIndex = 0;

	async function worker() {
		while (nextIndex < ids.length) {
			const index = nextIndex++;
			const id = ids[index];
			try {
				await mutate(id);
				results[index] = { id, ok: true };
			} catch {
				results[index] = { id, ok: false, error: t('bulkActions.requestFailed') };
			}
		}
	}

	await Promise.all(Array.from({ length: Math.min(concurrency, ids.length) }, worker));
	return results;
}
