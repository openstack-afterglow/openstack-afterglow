// @vitest-environment node
import { describe, expect, it } from 'vitest';
import { executeBulkMutations, partitionBulkIds } from '../bulkActions';

describe('partitionBulkIds', () => {
	it('keeps selected input order while separating ineligible IDs', () => {
		expect(partitionBulkIds(['one', 'two', 'three'], ['two', 'three'])).toEqual({
		eligible: ['two', 'three'],
		skipped: ['one'],
	});
});
});

describe('executeBulkMutations', () => {
	it('returns immediately for an empty input', async () => {
		const result = await executeBulkMutations([], async () => undefined);
		expect(result).toEqual([]);
	});

	it('preserves input order and retains individual failures', async () => {
		const result = await executeBulkMutations(['one', 'two', 'three'], async (id) => {
			if (id === 'two') throw new Error('unavailable');
		});
		expect(result).toEqual([
			{ id: 'one', ok: true },
			{ id: 'two', ok: false, error: '요청 실패' },
			{ id: 'three', ok: true },
		]);
	});

	it('never starts more than four deferred mutations concurrently by default', async () => {
		const ids = ['one', 'two', 'three', 'four', 'five', 'six'];
		const gates = new Map(ids.map((id) => [id, Promise.withResolvers<void>()]));
		const started: string[] = [];
		const run = executeBulkMutations(ids, (id) => {
			started.push(id);
			return gates.get(id)!.promise;
		});

		expect(started).toEqual(['one', 'two', 'three', 'four']);
		for (const id of started) gates.get(id)!.resolve();
		await Promise.resolve();
		await Promise.resolve();
		expect(started).toEqual(ids);
		gates.get('five')!.resolve();
		gates.get('six')!.resolve();
		await expect(run).resolves.toEqual(ids.map((id) => ({ id, ok: true })));
	});
});
