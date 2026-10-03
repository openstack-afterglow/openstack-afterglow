import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/svelte';
import { flushSync } from 'svelte';
import SlidePanelWrapper from './_SlidePanelWrapper.svelte';

// jsdom은 Web Animations API / matchMedia를 지원하지 않음 — mock 필요
beforeEach(() => {
	Element.prototype.animate = vi.fn().mockReturnValue({
		finished: Promise.resolve(),
		cancel: vi.fn(),
		play: vi.fn(),
	});
	window.matchMedia = vi.fn().mockImplementation((query: string) => ({
		matches: false,
		media: query,
		onchange: null,
		addListener: vi.fn(),
		removeListener: vi.fn(),
		addEventListener: vi.fn(),
		removeEventListener: vi.fn(),
		dispatchEvent: vi.fn(),
	}));
	localStorage.clear();
});

describe('SlidePanel', () => {
	it('role=dialog aria-modal=true로 렌더링', () => {
		render(SlidePanelWrapper, { onClose: vi.fn() });
		flushSync();
		const dialog = screen.getByRole('dialog');
		expect(dialog.getAttribute('aria-modal')).toBe('true');
	});

	it('backdrop 클릭 시 onClose 호출', async () => {
		const onClose = vi.fn();
		render(SlidePanelWrapper, { onClose });
		flushSync();
		const closeBtn = screen.getByLabelText('패널 닫기');
		await fireEvent.click(closeBtn);
		expect(onClose).toHaveBeenCalledOnce();
	});

	it('Escape 키 누를 시 onClose 호출', async () => {
		const onClose = vi.fn();
		render(SlidePanelWrapper, { onClose });
		flushSync();
		const dialog = screen.getByRole('dialog');
		await fireEvent.keyDown(dialog, { key: 'Escape' });
		expect(onClose).toHaveBeenCalledOnce();
	});

	// 자식 패널이 자기 × 를 또 그려 헤더에 닫기 버튼이 두 개 보이는 버그가 실제로 있었다.
	// 정본은 이 컨테이너가 그리는 `[data-slide-panel-close]` 하나뿐이다.
	// role/name 으로 세면 안 된다 — 배경 scrim 도 aria-label="패널 닫기" 인 button 이라 정상 상태에서도 2개다.
	it('닫기 버튼(data-slide-panel-close)을 정확히 1개만 렌더한다', () => {
		const { container } = render(SlidePanelWrapper, { onClose: vi.fn() });
		flushSync();
		expect(container.querySelectorAll('[data-slide-panel-close]')).toHaveLength(1);
	});

	it('scrim 과 헤더 닫기의 accessible name 이 서로 구분된다', () => {
		render(SlidePanelWrapper, { onClose: vi.fn() });
		flushSync();
		// 이름이 같아지면 getByLabelText 가 다중 매치로 throw 하고, 스크린리더에도 같은 컨트롤이 두 번 읽힌다
		expect(screen.getByLabelText('패널 닫기')).toBeTruthy();
		expect(screen.getByLabelText('패널 닫기 버튼')).toBeTruthy();
	});

});
