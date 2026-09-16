import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import { fireEvent } from '@testing-library/svelte';
import { get } from 'svelte/store';
import { flushSync } from 'svelte';
import { toast } from '$lib/stores/toast';
import Toast from '../Toast.svelte';

vi.stubGlobal('crypto', { randomUUID: vi.fn() });

let idCounter = 0;

beforeEach(() => {
	idCounter = 0;
	vi.mocked(crypto.randomUUID).mockImplementation(() => `00000000-0000-4000-8000-${String(++idCounter).padStart(12, '0')}`);
	vi.useFakeTimers();
});

afterEach(() => {
	// 모든 toast 제거하여 테스트 간 격리
	const current = get(toast);
	current.forEach((t) => toast.remove(t.id));
	flushSync();
	vi.useRealTimers();
});

describe('Toast', () => {
	it('$toast가 비어있으면 fixed 컨테이너 없음', () => {
		const { container } = render(Toast);
		flushSync();
		expect(container.querySelector('.fixed')).toBeNull();
	});

	it('success toast 추가 시 메시지 렌더링', () => {
		render(Toast);
		toast.success('작업 완료');
		flushSync();
		expect(screen.getByText('작업 완료')).toBeTruthy();
	});

	it('error toast는 ✕ 아이콘 표시', () => {
		render(Toast);
		toast.error('오류 발생');
		flushSync();
		expect(screen.getByText('✕')).toBeTruthy();
	});

	it('success toast는 ✓ 아이콘 표시', () => {
		render(Toast);
		toast.success('성공');
		flushSync();
		expect(screen.getByText('✓')).toBeTruthy();
	});

	it('warning toast는 ⚠ 아이콘 표시', () => {
		render(Toast);
		toast.warning('경고');
		flushSync();
		expect(screen.getByText('⚠')).toBeTruthy();
	});

	it('닫기 버튼 클릭 시 toast 제거', async () => {
		render(Toast);
		toast.success('닫을 메시지');
		flushSync();
		const closeBtn = screen.getByText('×');
		await fireEvent.click(closeBtn);
		flushSync();
		expect(get(toast)).toHaveLength(0);
	});
});
