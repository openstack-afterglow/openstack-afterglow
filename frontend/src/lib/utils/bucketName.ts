/**
 * 오브젝트 스토리지 버킷 이름 클라이언트 검증 (Phase 10).
 *
 * S3 RFC 1123 + Ceph/Swift/AWS 예약어 + 관리용 시스템 이름 차단.
 * backend `app/services/bucket_naming.py` 와 정책을 동일하게 유지해야 함.
 *
 * 통과 시 null, 위반 시 한국어 사유 메시지 반환.
 */
import { t } from '$lib/i18n/ns/object-storage';

const RESERVED_EXACT: ReadonlySet<string> = new Set([
	'admin',
	'administrator',
	'root',
	'system',
	'default',
	'swift',
	'ceph',
	'rgw',
	's3',
	'aws',
	'bucket',
	'container',
	'account',
	'test-quarantine',
	'.well-known'
]);

const RESERVED_SUFFIXES: readonly string[] = ['-quarantine', '-trash', '_segments'];
const RESERVED_PREFIXES: readonly string[] = ['aws-', 'amazon-', '_account', '_container'];

const FORMAT_RE = /^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$/;
const IPV4_RE = /^(?:\d{1,3}\.){3}\d{1,3}$/;

export function validateBucketName(name: unknown): string | null {
	if (typeof name !== 'string') {
		return t('buckets.nameValidation.string');
	}

	if (name !== name.trim()) {
		return t('buckets.nameValidation.whitespace');
	}

	if (!name) {
		return t('buckets.nameValidation.empty');
	}

	if (name.startsWith('.')) {
		return t('buckets.nameValidation.leadingDot');
	}
	if (name.startsWith('-')) {
		return t('buckets.nameValidation.leadingHyphen');
	}

	const lower = name.toLowerCase();

	if (RESERVED_EXACT.has(lower)) {
		return t('buckets.nameValidation.reservedName', { name });
	}

	for (const suf of RESERVED_SUFFIXES) {
		if (lower.endsWith(suf)) {
			return t('buckets.nameValidation.reservedSuffix', { suffix: suf });
		}
	}

	for (const pre of RESERVED_PREFIXES) {
		if (lower.startsWith(pre)) {
			return t('buckets.nameValidation.reservedPrefix', { prefix: pre });
		}
	}

	if (name.length < 3) return t('buckets.nameValidation.tooShort');
	if (name.length > 63) return t('buckets.nameValidation.tooLong');

	if (!FORMAT_RE.test(name)) {
		if (/[A-Z]/.test(name)) return t('buckets.nameValidation.lowercase');
		if (name.includes('.')) return t('buckets.nameValidation.dot');
		if (name.includes('_')) return t('buckets.nameValidation.underscore');
		if (name.includes(' ')) return t('buckets.nameValidation.space');
		for (const ch of name) {
			if (!/[a-z0-9-]/.test(ch)) {
				return t('buckets.nameValidation.character', { character: ch });
			}
		}
		if (name.endsWith('-')) return t('buckets.nameValidation.trailingHyphen');
		return t('buckets.nameValidation.format');
	}

	if (name.includes('--')) {
		return t('buckets.nameValidation.consecutiveHyphens');
	}

	if (IPV4_RE.test(name)) {
		return t('buckets.nameValidation.ipAddress');
	}

	return null;
}
