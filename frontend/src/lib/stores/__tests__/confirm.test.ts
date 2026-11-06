import { afterEach, describe, expect, it, vi } from 'vitest';
import { confirmDialog, dialogState } from '../confirm.svelte';

afterEach(() => {
	dialogState.reject();
});

describe('confirmDialog typed gate', () => {
	it('keeps the promise pending for missing, wrong, padded, or normalized input until exact acceptance', async () => {
		const settled = vi.fn();
		const result = confirmDialog('Delete attached volumes', {
			requiredText: '제거',
			requiredTextLabel: '제거를 입력하세요',
		});
		void result.then(settled);
		expect(dialogState.requiredText).toBe('제거');
		expect(dialogState.requiredTextLabel).toBe('제거를 입력하세요');

		for (const value of [undefined, '', '삭제', ' 제거', '제거 ', '제거'.normalize('NFD')]) {
			dialogState.accept(value);
			await Promise.resolve();
			expect(dialogState.open).toBe(true);
			expect(settled).not.toHaveBeenCalled();
		}

		dialogState.accept('제거');
		await expect(result).resolves.toBe(true);
		expect(dialogState.open).toBe(false);
		expect(settled).toHaveBeenCalledTimes(1);
		expect(settled).toHaveBeenCalledWith(true);
	});

	it('can cancel a gated dialog without entering the required text', async () => {
		const result = confirmDialog('Delete attached volumes', { requiredText: '제거' });
		dialogState.reject();
		await expect(result).resolves.toBe(false);
		expect(dialogState.open).toBe(false);
	});

	it('resets the gate, label, and button options for a later ungated dialog', async () => {
		const first = confirmDialog('First', {
			requiredText: '제거', requiredTextLabel: '제거를 입력하세요',
			confirmLabel: '제거', confirmVariant: 'accent',
		});
		const firstRequestId = dialogState.requestId;
		dialogState.reject();
		await expect(first).resolves.toBe(false);

		const next = confirmDialog('Second');
		expect(dialogState.requestId).toBeGreaterThan(firstRequestId);
		expect(dialogState.requiredText).toBeUndefined();
		expect(dialogState.requiredTextLabel).toBeUndefined();
		expect(dialogState.confirmLabel).toBeUndefined();
		expect(dialogState.confirmVariant).toBe('danger');
		dialogState.accept();
		await expect(next).resolves.toBe(true);
	});

	it('treats an explicitly empty required string as an exact gate rather than an absent option', async () => {
		const result = confirmDialog('Empty gate', { requiredText: '' });
		dialogState.accept();
		expect(dialogState.open).toBe(true);
		dialogState.accept('');
		await expect(result).resolves.toBe(true);
	});
});
