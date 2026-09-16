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
/**
 * 강도 스케일 하한. **이 아래는 "조용함"이지 "계측 없음"이 아니다.**
 *
 * 예전 값은 `1e5` 였는데 실측(2026-09-13, 운영 Prometheus, 윈도우 2m)에서 NIC 43개 중
 * rx+tx 중앙값이 8,729 bps, 최대가 365,770 bps 였다 — 43개 중 39개가 하한 아래로 떨어져
 * `bps == null`(텔레메트리 없음)과 **완전히 같은 스타일**로 그려졌다. 살아 있는 링크를
 * 죽은 것으로 그리는 셈이라 "어떤 네트워크가 바쁜가"를 읽을 수 없었다.
 */
export const INTENSITY_FLOOR_BPS = 1e3;

/** 하한부터 포화까지의 decade 수. `1e3` → `1e9`(1 Gbps)에서 포화한다. */
export const INTENSITY_DECADES = 6;

/**
 * 계측값이 **없을 때**의 스타일. 하한(`INTENSITY_ANCHORS[0]`)보다 가늘고 흐려서
 * 조용한 링크와 절대 겹치지 않는다 — 이 분리가 스케일 교정의 핵심이다.
 * dash 는 SHUTOFF/DOWN 이 이미 쓰므로 굵기·불투명도로만 가른다.
 */
export const NO_TELEMETRY_STYLE: { readonly width: number; readonly opacity: number } = { width: 1.5, opacity: 0.40 };

/** 사용량 강도 앵커: [하한으로부터의 decade, 굵기, 불투명도] */
const INTENSITY_ANCHORS: ReadonlyArray<readonly [number, number, number]> = [
	[0, 1.8, 0.55],
	[2, 2.7, 0.70],
	[4, 3.6, 0.85],
	[6, 4.5, 1.00],
];

/**
 * bps → 하한으로부터의 decade(`0..INTENSITY_DECADES` 포화). 하한 미만은 0 이다.
 *
 * `!(bps > 0)` 가드는 NaN 도 함께 거른다. 이게 없으면 NaN 이 그대로 흘러
 * `stroke-width: NaN` 이 되어 선이 통째로 사라진다 — 예전 구현의 `if (!(bps >= 1e5))`
 * 조기 반환이 우연히 맡고 있던 역할이라 구간을 넓히면서 같이 사라질 뻔했다.
 */
export function bpsDecade(bps: number): number {
	if (!(bps > 0)) return 0;
	const d = Math.log10(bps) - Math.log10(INTENSITY_FLOOR_BPS);
	return Math.min(Math.max(d, 0), INTENSITY_DECADES);
}

/**
 * 사용량 → 선 굵기·불투명도. decade 축에서 앵커 사이를 선형 보간한다.
 *
 * **계측값이 있는 한 절대 `NO_TELEMETRY_STYLE` 을 돌려주지 않는다.** 0 bps 는
 * "쟀더니 0"이라는 정보이므로 하한 앵커(1.8/0.55)로 그린다. "잴 수 없었다"는
 * 호출자가 `NO_TELEMETRY_STYLE` 로 따로 표현해야 한다.
 */
export function edgeIntensity(bps: number): { opacity: number; width: number } {
	const d = bpsDecade(bps);
	let i = 0;
	while (i < INTENSITY_ANCHORS.length - 2 && d >= INTENSITY_ANCHORS[i + 1][0]) i++;
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
 * 구간이 3 → 6 decade 로 넓어졌으므로 정규화한 decade 로 보간해
 * **양 끝값(0.6/40 ~ 4.0/130)은 예전과 같게** 유지한다.
 */
export function flowRate(bps: number): { freq: number; speed: number } {
	const d = bpsDecade(bps) / INTENSITY_DECADES;
	return { freq: 0.6 + 3.4 * d, speed: 40 + 90 * d };
}

/**
 * 경로에 띄울 점 개수. 점이 균일 간격으로 순환하므로 한 지점 통과 빈도는 `n · speed / len` 이다.
 * 이 값을 목표 빈도에 맞추면 경로 길이와 무관하게 사용량이 빈도로 읽힌다
 * (개수를 고정하면 긴 케이블이 같은 트래픽에서 더 한가해 보인다).
 *
 * **다만 `maxPerEdge` 에 닿으면 빈도 보존이 깨진다.** 긴 경로(이 상한 기준 대략 400px 이상)에서는
 * 사용량이 달라도 개수가 똑같이 8 로 포화하고, 남는 구분은 `flowRate` 의 속도뿐이다.
 * 상한은 rAF 마다 옮길 원 개수의 성능 한도이므로 그대로 두고, 이 한계를 계약으로 명시한다.
 */
export function flowDotCount(bps: number, pathLen: number, maxPerEdge = 8): number {
	const { freq, speed } = flowRate(bps);
	return Math.max(1, Math.min(maxPerEdge, Math.round((freq * Math.max(pathLen, 1)) / speed)));
}
