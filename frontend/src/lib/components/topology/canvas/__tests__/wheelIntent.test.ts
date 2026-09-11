// 휠 제스처 의도 판정. 브라우저가 입력 장치를 알려주지 않으므로 휴리스틱이며, 그 경계를 여기서 고정한다.
import { describe, expect, it } from 'vitest';
import { isMouseWheel, wheelIntent } from '../canvasHelpers';

/** jsdom WheelEvent 는 비표준 wheelDeltaY 를 만들지 않으므로 필요할 때 직접 주입한다. */
function wheel(init: {
	deltaX?: number;
	deltaY?: number;
	deltaMode?: number;
	ctrlKey?: boolean;
	metaKey?: boolean;
	wheelDeltaY?: number;
}): WheelEvent {
	const ev = new WheelEvent('wheel', {
		deltaX: init.deltaX ?? 0,
		deltaY: init.deltaY ?? 0,
		deltaMode: init.deltaMode ?? 0,
		ctrlKey: init.ctrlKey ?? false,
		metaKey: init.metaKey ?? false,
	});
	if (init.wheelDeltaY !== undefined) Object.defineProperty(ev, 'wheelDeltaY', { value: init.wheelDeltaY });
	return ev;
}

describe('isMouseWheel — 입력 장치 추정', () => {
	it('줄·페이지 단위 델타는 마우스 휠이다(Firefox 는 마우스 휠만 줄 단위로 보고한다)', () => {
		expect(isMouseWheel(wheel({ deltaY: 3, deltaMode: 1 }))).toBe(true);
		expect(isMouseWheel(wheel({ deltaY: 1, deltaMode: 2 }))).toBe(true);
	});

	it('wheelDeltaY 가 120 의 배수면 마우스 휠이다(Chrome·Safari 노치 단위)', () => {
		expect(isMouseWheel(wheel({ deltaY: 100, wheelDeltaY: -120 }))).toBe(true);
		expect(isMouseWheel(wheel({ deltaY: 300, wheelDeltaY: -360 }))).toBe(true);
		expect(isMouseWheel(wheel({ deltaY: -100, wheelDeltaY: 120 }))).toBe(true);
	});

	it('120 의 배수가 아닌 wheelDeltaY 는 트랙패드다', () => {
		expect(isMouseWheel(wheel({ deltaY: 7, wheelDeltaY: -8 }))).toBe(false);
		expect(isMouseWheel(wheel({ deltaY: 53, wheelDeltaY: -64 }))).toBe(false);
	});

	it('가로 성분이 있으면 트랙패드다', () => {
		expect(isMouseWheel(wheel({ deltaX: 12, deltaY: 100, wheelDeltaY: -120 }))).toBe(false);
	});

	it('소수점 델타는 트랙패드다', () => {
		expect(isMouseWheel(wheel({ deltaY: 4.5 }))).toBe(false);
		expect(isMouseWheel(wheel({ deltaY: 0.5, wheelDeltaY: -120 }))).toBe(false);
	});

	it('판단 근거가 없으면 트랙패드로 본다 — 잘못 확대되는 쪽이 더 거슬린다', () => {
		// wheelDeltaY 없음(비표준이라 없을 수 있다) + 픽셀 단위 + 가로 성분 없음 → 애매하다
		expect(isMouseWheel(wheel({ deltaY: 120 }))).toBe(false);
		expect(isMouseWheel(wheel({ deltaY: 100, wheelDeltaY: 0 }))).toBe(false);
	});
});

describe('wheelIntent — 확대·축소 vs 위치 이동', () => {
	it('마우스 휠은 확대·축소다', () => {
		expect(wheelIntent(wheel({ deltaY: 100, wheelDeltaY: -120 }))).toBe('zoom');
		expect(wheelIntent(wheel({ deltaY: 3, deltaMode: 1 }))).toBe('zoom');
	});

	it('트랙패드 두 손가락 스크롤은 위치 이동이다', () => {
		expect(wheelIntent(wheel({ deltaX: 20, deltaY: 8 }))).toBe('pan');
		expect(wheelIntent(wheel({ deltaY: 4.5 }))).toBe('pan');
	});

	it('ctrl·⌘+휠과 트랙패드 핀치는 장치와 무관하게 항상 확대·축소다', () => {
		// 브라우저는 트랙패드 핀치를 ctrlKey wheel 로 보고한다
		expect(wheelIntent(wheel({ deltaY: 4.5, ctrlKey: true }))).toBe('zoom');
		expect(wheelIntent(wheel({ deltaX: 20, deltaY: 8, metaKey: true }))).toBe('zoom');
	});
});
