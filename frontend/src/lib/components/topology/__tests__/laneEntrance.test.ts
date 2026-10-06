// 레인 뷰 진입·흐름 모션 계약: 스코프별 첫 도착에만 진입하고, 자동 갱신은 다시 재생하지 않으며,
// 흐름 점선은 측정된 트래픽에만 붙는다. jsdom 은 matchMedia·ResizeObserver 가 없어 필요한 만큼만 채운다.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render } from '@testing-library/svelte';
import GlobalTopology from '../../GlobalTopology.svelte';
import { REDUCED_MOTION_QUERY } from '$lib/design/tokens';
import { TOPOLOGY_ENTRANCE_MS } from '../firstArrival.svelte';
import { OTHER, P, makeFixture, makeTraffic } from '../canvas/__tests__/fixtures';

class NoopResizeObserver {
	observe() {}
	unobserve() {}
	disconnect() {}
}

/** 진입 모션 흔적: 카드 cascade, 레인 카드 페이드, 레일 성장, 연결선 draw-in(pathLength 포함) */
function entranceMarks() {
	return {
		cards: document.querySelectorAll('.motion-enter').length,
		laneCards: document.querySelectorAll('button.motion-fade').length,
		rails: document.querySelectorAll('.rail-enter').length,
		drawnLines: [...document.querySelectorAll('line.motion-draw')].filter((l) => l.getAttribute('pathLength') === '1').length,
		pathLength: [...document.querySelectorAll('line')].filter((l) => l.hasAttribute('pathLength')).length,
	};
}

/** 앵커 측정 rAF 를 흘려보낸다(연결선은 측정 뒤에 생긴다) */
const flushMeasure = () => vi.advanceTimersByTimeAsync(20);

describe('GlobalTopology 진입·흐름 모션', () => {
	beforeEach(() => {
		vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'requestAnimationFrame', 'cancelAnimationFrame', 'performance'] });
		vi.stubGlobal('ResizeObserver', NoopResizeObserver);
	});
	afterEach(() => {
		cleanup();
		vi.useRealTimers();
		vi.unstubAllGlobals();
	});

	it('첫 도착은 카드·레인·연결선이 진입하고, 진입 창이 지난 뒤의 자동 갱신은 다시 재생하지 않는다', async () => {
		const view = render(GlobalTopology, { props: { data: makeFixture(), traffic: makeTraffic(), projectId: P } });
		await flushMeasure();
		const first = entranceMarks();
		expect(first.cards).toBeGreaterThan(0);
		expect(first.laneCards).toBeGreaterThan(0);
		expect(first.rails).toBeGreaterThan(0);
		expect(first.drawnLines).toBeGreaterThan(0);

		await vi.advanceTimersByTimeAsync(TOPOLOGY_ENTRANCE_MS);
		await view.rerender({ data: makeFixture(), traffic: makeTraffic(), projectId: P });
		await flushMeasure();
		// 연결선은 그대로 그려져 있지만 진입 흔적은 하나도 없다
		expect(document.querySelectorAll('line').length).toBeGreaterThan(0);
		expect(entranceMarks()).toEqual({ cards: 0, laneCards: 0, rails: 0, drawnLines: 0, pathLength: 0 });
	});

	it('진입 창 중 갱신도 즉시 진입을 종료한다', async () => {
		const view = render(GlobalTopology, { props: { data: makeFixture(), projectId: P } });
		await flushMeasure();
		expect(entranceMarks().cards).toBeGreaterThan(0);
		await view.rerender({ data: makeFixture(), projectId: P });
		await flushMeasure();
		expect(entranceMarks()).toEqual({ cards: 0, laneCards: 0, rails: 0, drawnLines: 0, pathLength: 0 });
	});

	it('진입 창 중 검색·필터와 다음 갱신은 다시 진입하지 않는다', async () => {
		const view = render(GlobalTopology, { props: { data: makeFixture(), projectId: P, arrivalScope: 'admin' } });
		await flushMeasure();
		await fireEvent.input(view.getByPlaceholderText('이름 또는 IP 검색…'), { target: { value: '없음' } });
		await fireEvent.input(view.getByPlaceholderText('이름 또는 IP 검색…'), { target: { value: '' } });
		await view.rerender({ data: makeFixture(), projectId: OTHER, arrivalScope: 'admin' });
		await flushMeasure();
		expect(document.querySelectorAll('line').length).toBeGreaterThan(0);
		expect(entranceMarks()).toEqual({ cards: 0, laneCards: 0, rails: 0, drawnLines: 0, pathLength: 0 });
	});

	it('프로젝트 전환의 이전 데이터에는 진입하지 않고 새 응답을 기다린다', async () => {
		const data = makeFixture();
		const view = render(GlobalTopology, { props: { data, projectId: P } });
		await flushMeasure();
		await view.rerender({ data, projectId: OTHER });
		await flushMeasure();
		expect(entranceMarks().cards).toBe(0);
		await view.rerender({ data: makeFixture(), projectId: OTHER });
		await flushMeasure();
		expect(entranceMarks().cards).toBeGreaterThan(0);
	});

	it('스코프(프로젝트)가 바뀌면 그 스코프의 첫 도착이 다시 진입한다', async () => {
		const view = render(GlobalTopology, { props: { data: makeFixture(), traffic: makeTraffic(), projectId: P } });
		await flushMeasure();
		await vi.advanceTimersByTimeAsync(TOPOLOGY_ENTRANCE_MS);
		expect(entranceMarks().cards).toBe(0);

		await view.rerender({ data: makeFixture(), traffic: makeTraffic(), projectId: OTHER });
		await flushMeasure();
		expect(entranceMarks().cards).toBeGreaterThan(0);
		expect(entranceMarks().rails).toBeGreaterThan(0);
	});

	it('reduced-motion 이면 첫 도착에도 진입 모션을 붙이지 않는다', async () => {
		vi.stubGlobal('matchMedia', (query: string) => ({
			matches: query === REDUCED_MOTION_QUERY,
			media: query,
			addEventListener() {},
			removeEventListener() {},
		}));
		render(GlobalTopology, { props: { data: makeFixture(), traffic: makeTraffic(), projectId: P } });
		await flushMeasure();
		expect(document.querySelectorAll('line').length).toBeGreaterThan(0);
		expect(entranceMarks()).toEqual({ cards: 0, laneCards: 0, rails: 0, drawnLines: 0, pathLength: 0 });
	});

	it('흐름 점선은 측정된 트래픽이 있을 때만 붙고, 트래픽이 없으면 하나도 없다', async () => {
		const view = render(GlobalTopology, { props: { data: makeFixture(), traffic: makeTraffic(), projectId: P } });
		await flushMeasure();
		expect(document.querySelectorAll('line.motion-flow').length).toBeGreaterThan(0);
		expect(document.querySelectorAll('.rail-flow').length).toBeGreaterThan(0);

		await view.rerender({ data: makeFixture(), traffic: null, projectId: P });
		await flushMeasure();
		expect(document.querySelectorAll('.motion-flow').length).toBe(0);
	});
});
