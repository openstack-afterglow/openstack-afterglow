import { afterEach, describe, it, expect, vi, beforeEach } from 'vitest';
import { initLocale, KEY_DEBUG_STORAGE_KEY, restoreKeyDebugMode } from '$lib/i18n/runtime.svelte';
import type { ExperienceContext } from '$lib/utils/experience';

vi.mock('$env/dynamic/public', () => ({ env: { PUBLIC_API_BASE: 'http://localhost:8000' } }));

// toast mock
const mockToast = {
	success: vi.fn().mockReturnValue('toast-ok'),
	error: vi.fn().mockReturnValue('toast-err'),
	info: vi.fn().mockReturnValue('toast-info'),
	remove: vi.fn(),
};
vi.mock('$lib/stores/toast', () => ({ toast: mockToast }));

const { ApiError } = await import('../client');
const { apiMut } = await import('../mutations');

beforeEach(() => {
	vi.clearAllMocks();
});

afterEach(() => {
	initLocale('ko');
	localStorage.removeItem(KEY_DEBUG_STORAGE_KEY);
	restoreKeyDebugMode();
});

describe('apiMut', () => {
	it('성공 시 success toast 1회 호출', async () => {
		const result = await apiMut('볼륨 생성', () => Promise.resolve('vol-1'));
		expect(result).toBe('vol-1');
		expect(mockToast.success).toHaveBeenCalledOnce();
	});

	it('successMessage 지정 시 해당 메시지 표시', async () => {
		await apiMut('테스트', () => Promise.resolve(42), { successMessage: '작업 완료!' });
		expect(mockToast.success).toHaveBeenCalledWith('작업 완료!');
	});

	it('successMessage: null 이면 success toast 미호출', async () => {
		await apiMut('테스트', () => Promise.resolve(1), { successMessage: null });
		expect(mockToast.success).not.toHaveBeenCalled();
	});

	it('ApiError 발생 시 error toast + rethrow', async () => {
		const err = new ApiError(500, '서버 오류');
		await expect(apiMut('볼륨 삭제', () => Promise.reject(err))).rejects.toThrow(err);
		expect(mockToast.error).toHaveBeenCalledWith(expect.stringContaining(err.message));
	});

	it('errorPrefix 지정 시 해당 prefix 사용', async () => {
		const err = new ApiError(400, '잘못된 요청');
		await expect(
			apiMut('작업', () => Promise.reject(err), { errorPrefix: '커스텀 에러' })
		).rejects.toThrow(err);
		expect(mockToast.error).toHaveBeenCalledWith(expect.stringContaining('커스텀 에러'));
	});

	it('rethrow: false 이면 reject 흡수하고 undefined 반환', async () => {
		const err = new ApiError(500, '실패');
		const result = await apiMut('작업', () => Promise.reject(err), { rethrow: false });
		expect(result).toBeUndefined();
		expect(mockToast.error).toHaveBeenCalledOnce();
	});

	it('progress: true 이면 in-flight info toast 표시 후 제거', async () => {
		await apiMut('장시간 작업', () => Promise.resolve('done'), { progress: true });
		expect(mockToast.info).toHaveBeenCalledWith(expect.any(String), 0);
		expect(mockToast.remove).toHaveBeenCalledWith('toast-info');
	});

	it('progress: true + 실패 시에도 in-flight toast 제거', async () => {
		const err = new ApiError(500, '실패');
		await expect(
			apiMut('작업', () => Promise.reject(err), { progress: true })
		).rejects.toThrow(err);
		expect(mockToast.remove).toHaveBeenCalledWith('toast-info');
	});

	it('captures actual producer locale and static template identity without private label/error parameters', async () => {
		const experience = { segmentId: 'explicit-context' } as ExperienceContext;
		initLocale('en');
		await apiMut('private-resource-name', () => Promise.resolve('accepted'), { experience, progress: true });
		const progressMetadata = mockToast.info.mock.calls[0][3].message;
		const completedMetadata = mockToast.success.mock.calls[0][3].message;
		expect(progressMetadata).toMatchObject({ key: 'shared:mutation.progress', locale: 'en', restoration: 'redacted' });
		expect(completedMetadata).toMatchObject({ key: 'shared:mutation.completed', locale: 'en', restoration: 'redacted' });
		initLocale('ko');
		expect(completedMetadata.locale).toBe('en');
		expect(JSON.stringify(completedMetadata)).not.toContain('private-resource-name');

		await expect(apiMut('private label', () => Promise.reject(new ApiError(400, 'private server error')), { experience })).rejects.toThrow();
		const failureMetadata = mockToast.error.mock.calls[0][3].message;
		expect(failureMetadata).toMatchObject({ key: 'shared:mutation.failed', locale: 'ko', restoration: 'redacted' });
		expect(JSON.stringify(failureMetadata)).not.toContain('private server error');
	});

	it('does not reverse-match a custom preformatted success message', async () => {
		const experience = { segmentId: 'explicit-context' } as ExperienceContext;
		await apiMut('private label', () => Promise.resolve(1), { experience, successMessage: 'private custom message' });
		expect(mockToast.success.mock.calls[0][3].message).toMatchObject({ key: null, locale: 'unknown', restoration: 'unavailable' });
	});

	it('keeps key-debug presentations unavailable rather than claiming a redacted template', async () => {
		const experience = { segmentId: 'explicit-context' } as ExperienceContext;
		localStorage.setItem(KEY_DEBUG_STORAGE_KEY, 'keys');
		restoreKeyDebugMode();
		await apiMut('private label', () => Promise.resolve(1), { experience, progress: true });
		expect(mockToast.info.mock.calls[0][3].message).toMatchObject({ key: null, locale: 'unknown', restoration: 'unavailable' });
		expect(mockToast.success.mock.calls[0][3].message).toMatchObject({ key: null, locale: 'unknown', restoration: 'unavailable' });
		await expect(apiMut('private label', () => Promise.reject(new ApiError(400, 'private failure')), { experience })).rejects.toThrow();
		expect(mockToast.error.mock.calls[0][3].message).toMatchObject({ key: null, locale: 'unknown', restoration: 'unavailable' });
	});
});
