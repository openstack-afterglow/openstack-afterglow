/** Nova resizes running (with a guest restart) and stopped instances. */
export const RESIZABLE_STATUSES: ReadonlySet<string> = new Set(['ACTIVE', 'SHUTOFF']);

/** 인스턴스 전이 중 상태 집합 (Nova 상태값 기준, 대소문자 무관 비교) */
export const TRANSITIONAL_STATUSES = new Set([
	'BUILD',
	'REBOOT',
	'HARD_REBOOT',
	'RESIZE',
	'VERIFY_RESIZE',
	'MIGRATING',
	'SHELVING',
	'UNSHELVING',
	'REBUILD',
	'DELETING',
	'STOPPING',
	'POWERING-ON',
	'POWERING-OFF',
]);

/** 인스턴스 상태가 전이 중(transitional)인지 반환. */
export function isTransitional(status: string | null | undefined): boolean {
	if (!status) return false;
	return TRANSITIONAL_STATUSES.has(status.toUpperCase());
}
