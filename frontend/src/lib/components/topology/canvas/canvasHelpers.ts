// 캔버스 토폴로지 공용 헬퍼. 레인 뷰의 topologyHelpers 를 재사용하고 캔버스 전용 포맷터만 추가한다.
import type { TrafficRate } from '$lib/types/topology';
import { _ipv4InCidr, edgeIntensity, flowDotCount, flowRate, formatBps } from '../topologyHelpers';
import type { CanvasNetKind, CanvasNodeKind } from './types';

export { _ipv4InCidr, edgeIntensity, flowDotCount, flowRate, formatBps };

export const clamp = (v: number, a: number, b: number): number => Math.max(a, Math.min(b, v));

export const mean = (arr: readonly number[]): number | null =>
	arr.length ? arr.reduce((a, b) => a + b, 0) / arr.length : null;

export const uniq = <T>(arr: readonly T[]): T[] => [...new Set(arr)];

export const slug = (s: string): string =>
	String(s).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');

/** MAC 비교용 정규화: 소문자 hex 만 남긴다 ('FA:16:3E:..' → 'fa163e..'). */
export const normalizeMac = (s: string | null | undefined): string =>
	String(s ?? '').toLowerCase().replace(/[^0-9a-f]/g, '');

/** 이름 → id 순 총순서 비교자. 모든 정렬의 tie-break 로 사용해 결정론을 보장한다. */
export const byName = <T extends { name: string; id: string }>(a: T, b: T): number =>
	a.name.localeCompare(b.name) || a.id.localeCompare(b.id);

/** 소수 첫째 자리 반올림(SVG path 문자열 안정화). */
export const r1 = (v: number): number => Math.round(v * 10) / 10;

/** 배열 사전순 비교(rank 튜플 비교용). */
export function cmpArr(a: readonly (string | number)[], b: readonly (string | number)[]): number {
	for (let i = 0; i < Math.min(a.length, b.length); i++) {
		if (a[i] < b[i]) return -1;
		if (a[i] > b[i]) return 1;
	}
	return a.length - b.length;
}

/** 스위치·LB 카드용 양방향 속도. 텔레메트리 없음은 '▼ —  ▲ —'. */
export const fmtRate = (r: TrafficRate | null | undefined): string =>
	r ? `▼ ${formatBps(r.rx_bps)}  ▲ ${formatBps(r.tx_bps)}` : '▼ —  ▲ —';

/** VM NIC 행용 축약 속도. 텔레메트리 없음은 '—'. */
export const fmtRateShort = (r: TrafficRate | null | undefined): string =>
	r ? `↓${formatBps(r.rx_bps)} ↑${formatBps(r.tx_bps)}` : '—';

export const KIND_LABEL: Record<CanvasNodeKind, string> = {
	vm: '인스턴스',
	router: '라우터',
	switch: '네트워크 스위치',
	lb: '로드밸런서',
};

export const NET_KIND_LABEL: Record<CanvasNetKind, string> = {
	external: '외부',
	shared: '공유',
	internal: '내부',
};

/** 라우터 트렁크 배지 캡션(사용자 결정: 네트워크 합산값 표시). */
export const TRUNK_CAPTION = '네트워크 합산';
export const TRUNK_TITLE = '네트워크 합산 트래픽 · 라우터 exporter 없음';

/**
 * 휠 이벤트가 **마우스 휠**인지 추정한다. 브라우저는 입력 장치를 알려주지 않으므로 휴리스틱이다.
 *
 * - Firefox: 마우스 휠은 줄/페이지 단위(`deltaMode !== 0`), 트랙패드는 픽셀 단위(0).
 * - Chrome·Safari: 둘 다 픽셀 단위지만 비표준 `wheelDeltaY` 가 마우스 휠에서 120 의 배수로 온다(노치 단위).
 * - 트랙패드는 가로 성분(`deltaX`)과 소수점 델타가 흔하다 — 하나라도 있으면 트랙패드로 본다.
 *
 * 판단 근거가 없으면 **트랙패드로 본다**(= 이동). 잘못 확대되는 것이 잘못 이동하는 것보다 훨씬 거슬리고,
 * 트랙패드 관성 스크롤을 확대로 오판하면 뷰가 크게 튄다.
 */
export function isMouseWheel(e: WheelEvent): boolean {
	if (e.deltaMode !== 0) return true;
	if (e.deltaX !== 0) return false;
	if (!Number.isInteger(e.deltaY)) return false;
	const notch = (e as WheelEvent & { wheelDeltaY?: number }).wheelDeltaY;
	if (typeof notch === 'number' && notch !== 0) return Math.abs(notch) % 120 === 0;
	return false;
}

/**
 * 휠 제스처의 의도. `ctrl`/`⌘`+휠과 트랙패드 핀치(브라우저가 ctrlKey wheel 로 보고)는 항상 확대·축소이고,
 * 그 밖에는 마우스 휠이면 확대·축소, 트랙패드 두 손가락 스크롤이면 위치 이동이다.
 */
export function wheelIntent(e: WheelEvent): 'zoom' | 'pan' {
	if (e.ctrlKey || e.metaKey) return 'zoom';
	return isMouseWheel(e) ? 'zoom' : 'pan';
}

/**
 * 스파크라인 폴리라인 좌표. `peak` 를 rx/tx 공용 상한으로 써서 두 선을 같은 축에 올린다.
 *
 * 샘플이 1개면 두 점을 내보내 가로선으로 보이게 한다 — polyline 은 점 1개로 아무것도 그리지 않는다.
 * 빈 입력은 빈 문자열이며, 호출부가 "데이터 없음"을 0 과 구분해 표시해야 한다.
 */
export function sparkPoints(values: readonly number[], w: number, h: number, peak: number): string {
	if (!values.length) return '';
	const top = peak > 0 ? peak : 1;
	const r = (v: number) => Math.round(v * 100) / 100;
	const y = (v: number) => r(h - Math.max(0, Math.min(1, v / top)) * h);
	if (values.length === 1) return `0,${y(values[0])} ${r(w)},${y(values[0])}`;
	const span = values.length - 1;
	return values.map((v, i) => `${r((i / span) * w)},${y(v)}`).join(' ');
}
