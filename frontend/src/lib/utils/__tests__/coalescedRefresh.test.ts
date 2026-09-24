// @vitest-environment node
import { describe, expect, it, vi } from 'vitest';
import { createCoalescedRefresh } from '../coalescedRefresh';

function deferred<T = void>() {
	let resolve!: (value: T | PromiseLike<T>) => void;
	let reject!: (reason?: unknown) => void;
	const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
	return { promise, resolve, reject };
}

describe('createCoalescedRefresh', () => {
	it('joins automatic callers to the active task even after a force is queued', async () => {
		const first = deferred<void>();
		const second = deferred<void>();
		const task = vi.fn()
			.mockImplementationOnce(() => first.promise)
			.mockImplementationOnce(() => second.promise);
		const refresh = createCoalescedRefresh(task);

		const automatic = refresh.run();
		expect(refresh.run()).toBe(automatic);
		const manual = refresh.run(true);
		expect(refresh.run(true)).toBe(manual);
		const laterAutomatic = refresh.run(false);
		expect(laterAutomatic).toBe(automatic);
		expect(task).toHaveBeenCalledWith(false);

		first.resolve();
		await expect(laterAutomatic).resolves.toBeUndefined();
		await vi.waitFor(() => expect(task).toHaveBeenLastCalledWith(true));
		second.resolve();
		await expect(manual).resolves.toBeUndefined();
	});

	it('joins an active force and flushes an invalidation that arrives during it', async () => {
		const first = deferred<void>();
		const second = deferred<void>();
		const task = vi.fn()
			.mockImplementationOnce(() => first.promise)
			.mockImplementationOnce(() => second.promise);
		const refresh = createCoalescedRefresh(task);

		const force = refresh.run(true);
		expect(refresh.run(true)).toBe(force);
		const invalidated = refresh.invalidate();
		first.resolve();
		await vi.waitFor(() => expect(task).toHaveBeenNthCalledWith(2, true));
		await expect(force).resolves.toBeUndefined();
		second.resolve();
		await expect(invalidated).resolves.toBeUndefined();
	});

	it('coalesces mutations before queued force starts and extends the flush after it starts', async () => {
		const first = deferred<void>();
		const second = deferred<void>();
		const third = deferred<void>();
		const task = vi.fn()
			.mockImplementationOnce(() => first.promise)
			.mockImplementationOnce(() => second.promise)
			.mockImplementationOnce(() => third.promise);
		const refresh = createCoalescedRefresh(task);

		void refresh.run();
		const firstInvalidation = refresh.invalidate();
		const secondInvalidation = refresh.invalidate();
		first.resolve();
		await vi.waitFor(() => expect(task).toHaveBeenNthCalledWith(2, true));
		const lateInvalidation = refresh.invalidate();
		second.resolve();
		await vi.waitFor(() => expect(task).toHaveBeenNthCalledWith(3, true));
		await expect(firstInvalidation).resolves.toBeUndefined();
		await expect(secondInvalidation).resolves.toBeUndefined();
		third.resolve();
		await expect(lateInvalidation).resolves.toBeUndefined();
	});

	it('runs queued force work after an automatic failure without poisoning its callers', async () => {
		const first = deferred<void>();
		const second = deferred<void>();
		const task = vi.fn()
			.mockImplementationOnce(() => first.promise)
			.mockImplementationOnce(() => second.promise);
		const refresh = createCoalescedRefresh(task);

		const automatic = refresh.run();
		const manual = refresh.run(true);
		const invalidated = refresh.invalidate();
		first.reject(new Error('automatic failure'));
		await expect(automatic).rejects.toThrow('automatic failure');
		await vi.waitFor(() => expect(task).toHaveBeenNthCalledWith(2, true));
		second.resolve();
		await expect(manual).resolves.toBeUndefined();
		await expect(invalidated).resolves.toBeUndefined();
	});

	it('rejects a failed invalidation force and recovers when idle', async () => {
		const task = vi.fn()
			.mockRejectedValueOnce(new Error('forced failure'))
			.mockResolvedValueOnce(undefined);
		const refresh = createCoalescedRefresh(task);

		await expect(refresh.invalidate()).rejects.toThrow('forced failure');
		await expect(refresh.run()).resolves.toBeUndefined();
		expect(task).toHaveBeenNthCalledWith(2, false);
	});

	it('treats an undefined rejection as a failure and recovers when idle', async () => {
		const task = vi.fn()
			.mockRejectedValueOnce(undefined)
			.mockResolvedValueOnce(undefined);
		const refresh = createCoalescedRefresh(task);

		await expect(refresh.invalidate()).rejects.toBeUndefined();
		await expect(refresh.run()).resolves.toBeUndefined();
		expect(task).toHaveBeenNthCalledWith(2, false);
	});
});
