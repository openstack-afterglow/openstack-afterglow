import { afterEach, describe, it, expect, beforeEach, vi } from 'vitest';
import { get } from 'svelte/store';

let uuidCounter = 0;
vi.stubGlobal('crypto', {
	randomUUID: () => `uuid-${++uuidCounter}`,
});

describe('toast store', () => {
	beforeEach(() => {
		vi.useFakeTimers();
		uuidCounter = 0;
		vi.resetModules();
	});

	afterEach(() => {
		vi.useRealTimers();
	});

	it('초기 상태는 빈 배열', async () => {
		const { toast } = await import('../toast');
		expect(get(toast)).toEqual([]);
	});

	it('success() 로 success 타입 토스트 추가', async () => {
		const { toast } = await import('../toast');
		toast.success('성공 메시지');
		const toasts = get(toast);
		expect(toasts).toHaveLength(1);
		expect(toasts[0].type).toBe('success');
		expect(toasts[0].message).toBe('성공 메시지');
	});

	it('error() 는 자동으로 사라지지 않는다 (duration 0)', async () => {
		const { toast } = await import('../toast');
		toast.error('오류 메시지');
		const toasts = get(toast);
		expect(toasts[0].type).toBe('error');
		// 오류는 실패한 작업과 해결 단계를 담으므로 시간 제한을 두지 않는다 (WCAG 2.2.1).
		expect(toasts[0].duration).toBe(0);
	});

	it('hover 중에는 자동 삭제 타이머가 멈추고 해제되면 남은 시간만큼 이어진다', async () => {
		vi.useFakeTimers();
		const { toast } = await import('../toast');
		const id = toast.success('성공', 1000);

		vi.advanceTimersByTime(400);
		toast.pause(id, 'hover');
		vi.advanceTimersByTime(5000);
		expect(get(toast)).toHaveLength(1);

		toast.resume(id, 'hover');
		vi.advanceTimersByTime(599);
		expect(get(toast)).toHaveLength(1);
		vi.advanceTimersByTime(2);
		expect(get(toast)).toHaveLength(0);
		vi.useRealTimers();
	});

	it('warning() 추가', async () => {
		const { toast } = await import('../toast');
		toast.warning('경고');
		expect(get(toast)[0].type).toBe('warning');
	});

	it('info() 추가', async () => {
		const { toast } = await import('../toast');
		toast.info('정보');
		expect(get(toast)[0].type).toBe('info');
	});

	it('remove(id)로 즉시 삭제', async () => {
		const { toast } = await import('../toast');
		const id = toast.success('삭제 대상');
		expect(get(toast)).toHaveLength(1);
		toast.remove(id);
		expect(get(toast)).toHaveLength(0);
	});

	it('duration 경과 후 자동 삭제', async () => {
		const { toast } = await import('../toast');
		toast.success('자동 삭제', 1000);
		expect(get(toast)).toHaveLength(1);
		vi.advanceTimersByTime(1000);
		expect(get(toast)).toHaveLength(0);
	});

	it('duration 이전에는 삭제되지 않음', async () => {
		const { toast } = await import('../toast');
		toast.success('아직 살아있음', 2000);
		vi.advanceTimersByTime(1999);
		expect(get(toast)).toHaveLength(1);
	});

	it('여러 토스트 독립적으로 관리', async () => {
		const { toast } = await import('../toast');
		const id1 = toast.success('첫 번째', 1000);
		toast.error('두 번째', 2000);
		vi.advanceTimersByTime(1000);
		const remaining = get(toast);
		expect(remaining).toHaveLength(1);
		expect(remaining[0].type).toBe('error');
		void id1;
	});

	it('존재하지 않는 id 삭제 시 오류 없음', async () => {
		const { toast } = await import('../toast');
		expect(() => toast.remove('non-existent-id')).not.toThrow();
	});

	it('duration=0이면 자동 삭제 안 함', async () => {
		const { toast } = await import('../toast');
		toast.success('영구', 0);
		vi.advanceTimersByTime(999_999);
		expect(get(toast)).toHaveLength(1);
	});
});
