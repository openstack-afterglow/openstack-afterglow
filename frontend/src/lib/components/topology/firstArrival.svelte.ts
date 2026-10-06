// 토폴로지 진입 모션 게이트. 스코프(프로젝트·전체 보기)마다 **첫 데이터 도착** 한 번만 진입 모션을 켠다.
// 자동 갱신·재측정(rAF/ResizeObserver)·가로 스크롤·검색·그룹 접기는 스코프를 바꾸지 않으므로 다시 켜지지 않는다.
import { untrack } from 'svelte';
import { MOTION_DURATION_MS, MOTION_STAGGER_LIMIT } from '$lib/design/tokens';
import { prefersReducedMotion } from '$lib/utils/motion';

/**
 * 진입 창 길이: 상한까지 쌓인 cascade 지연 뒤 data 길이 draw-in, 그 뒤에 두 단계 늦게 시작하는 LB 곡선의
 * panel 길이 페이드까지 끝나는 시간. 창 안에서 새로 마운트되는 항목(측정 뒤에 생기는 연결선 등)도 같은 진입에 속한다.
 */
export const TOPOLOGY_ENTRANCE_MS =
	MOTION_DURATION_MS.stagger * (MOTION_STAGGER_LIMIT + 2) + MOTION_DURATION_MS.data + MOTION_DURATION_MS.panel;

export interface FirstArrivalOptions {
	/** 진입을 다시 허용하는 경계. 바뀌면 다음 도착이 새 첫 도착이다. */
	scope: () => string;
	/** 구조 데이터의 참조. 같은 스코프의 새 응답은 진행 중 진입도 종료한다. */
	data: () => object;
	/** 검색·접기·프로젝트 필터는 진입을 종료하되 다시 허용하지 않는다. */
	filter: () => string;
	/** 그릴 내용이 있는지. 비어 있는 도착은 진입으로 치지 않는다. */
	ready: () => boolean;
}

export interface FirstArrival {
	/** 지금 진입 모션 중인지. 진입 클래스·pathLength 는 이 값이 참일 때만 붙인다. */
	readonly active: boolean;
}

/** 컴포넌트 초기화 중에 호출한다. `active` 는 첫 렌더 전에 이미 결정되므로 첫 프레임부터 진입 클래스가 붙는다. */
export function createFirstArrival(opts: FirstArrivalOptions): FirstArrival {
	let active = $state(false);
	let scope: string | null = null;
	let armed = false;
	let previousData: object | undefined;
	let staleData: object | undefined;
	let filter: string | undefined;
	let timer: ReturnType<typeof setTimeout> | undefined;

	function stop() {
		clearTimeout(timer);
		timer = undefined;
		active = false;
	}

	$effect.pre(() => {
		const nextScope = opts.scope();
		const nextData = opts.data();
		const nextFilter = opts.filter();
		const ready = opts.ready();
		untrack(() => {
			if (nextScope !== scope) {
				staleData = previousData;
				scope = nextScope;
				armed = true;
				stop();
			} else if (nextData !== previousData || nextFilter !== filter) {
				stop();
			}
			previousData = nextData;
			filter = nextFilter;
			if (!armed || !ready || nextData === staleData) return;
			armed = false;
			if (prefersReducedMotion()) return;
			active = true;
			timer = setTimeout(stop, TOPOLOGY_ENTRANCE_MS);
		});
	});

	$effect(() => () => clearTimeout(timer));

	return {
		get active() {
			return active;
		},
	};
}

/** cascade 단계(0…MOTION_STAGGER_LIMIT). 긴 목록도 한 박자 안에 끝난다. */
export function enterStep(index: number): number {
	return Math.min(Math.max(0, Math.floor(index)), MOTION_STAGGER_LIMIT);
}
