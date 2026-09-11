export const EXT_COLORS = ['#ea580c', '#f97316'];
export const SHR_COLORS = ['#0d9488', '#14b8a6'];
export const INT_COLORS = ['#3b82f6', '#22c55e', '#a855f7', '#f59e0b', '#06b6d4', '#ec4899', '#ef4444'];

export const LANE_W = 180;
export const LANE_GAP = 16;
export const LANE_PAD = 16;
export const SIDEBAR_W = 300;

export function _ipToNum(ip: string): number | null {
	const parts = ip.split('.');
	if (parts.length !== 4) return null;
	const nums = parts.map(Number);
	if (nums.some(n => isNaN(n) || n < 0 || n > 255)) return null;
	return ((nums[0] << 24) | (nums[1] << 16) | (nums[2] << 8) | nums[3]) >>> 0;
}

export function _ipv4InCidr(ip: string, cidr: string): boolean {
	const si = cidr.lastIndexOf('/');
	if (si < 0) return false;
	const mask = parseInt(cidr.slice(si + 1));
	if (isNaN(mask) || mask < 0 || mask > 32) return false;
	const ipN = _ipToNum(ip), netN = _ipToNum(cidr.slice(0, si));
	if (ipN === null || netN === null) return false;
	const mb = mask === 0 ? 0 : ((0xFFFFFFFF << (32 - mask)) >>> 0);
	return (ipN & mb) === (netN & mb);
}

export function formatBps(bps: number): string {
	if (bps >= 1e9) return `${(bps / 1e9).toFixed(1)}G`;
	if (bps >= 1e6) return `${(bps / 1e6).toFixed(1)}M`;
	if (bps >= 1e3) return `${(bps / 1e3).toFixed(0)}k`;
	if (bps > 0) return `${bps.toFixed(0)}b`;
	return '0';
}

/** 사용량 강도 앵커: [1e5 로부터의 decade, 굵기, 불투명도] */
const INTENSITY_ANCHORS: ReadonlyArray<readonly [number, number, number]> = [
	[0, 2.0, 0.65],
	[1, 2.5, 0.80],
	[2, 3.0, 0.90],
	[3, 3.5, 1.00],
];

/** bps → 1e5 로부터의 decade(0..3 포화). 1e5 미만은 0 미만이 되므로 호출자가 걸러야 한다. */
export function bpsDecade(bps: number): number {
	return Math.min(Math.max(Math.log10(Math.max(bps, 1)) - 5, 0), 3);
}

/**
 * 사용량 → 선 굵기·불투명도. 예전에는 1e5/1e6/1e7/1e8 네 계단이었지만,
 * 같은 계단 안에서는 10배 차이가 똑같이 보여 사용량을 읽을 수 없었다.
 * 이제 decade 축에서 앵커 사이를 선형 보간한다 — **앵커 값은 그대로**이므로
 * 경계에서의 모양은 유지되고 그 사이만 연속으로 변한다(레인 뷰도 같은 함수를 쓴다).
 */
export function edgeIntensity(bps: number): { opacity: number; width: number } {
	if (!(bps >= 1e5)) return { opacity: 0.40, width: 1.5 };
	const d = bpsDecade(bps);
	const i = Math.min(Math.floor(d), INTENSITY_ANCHORS.length - 2);
	const [d0, w0, o0] = INTENSITY_ANCHORS[i];
	const [d1, w1, o1] = INTENSITY_ANCHORS[i + 1];
	const f = (d - d0) / (d1 - d0);
	return {
		width: Math.round((w0 + (w1 - w0) * f) * 100) / 100,
		opacity: Math.round((o0 + (o1 - o0) * f) * 1000) / 1000,
	};
}

/**
 * 사용량 → 흐르는 점의 **빈도**(초당 한 지점을 통과하는 개수)와 속도(월드 px/s).
 * 속도는 예전 값(`40 + 30·decade`)을 그대로 유지한다.
 */
export function flowRate(bps: number): { freq: number; speed: number } {
	const d = bpsDecade(bps);
	return { freq: 0.6 + (3.4 * d) / 3, speed: 40 + 30 * d };
}

/**
 * 경로에 띄울 점 개수. 점이 균일 간격으로 순환하므로 한 지점 통과 빈도는 `n · speed / len` 이다.
 * 이 값을 목표 빈도에 맞추면 **경로 길이와 무관하게** 사용량이 빈도로 읽힌다
 * (개수를 고정하면 긴 케이블이 같은 트래픽에서 더 한가해 보인다).
 */
export function flowDotCount(bps: number, pathLen: number, maxPerEdge = 8): number {
	const { freq, speed } = flowRate(bps);
	return Math.max(1, Math.min(maxPerEdge, Math.round((freq * Math.max(pathLen, 1)) / speed)));
}
