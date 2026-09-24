// @vitest-environment node
import { describe, it, expect } from 'vitest';
import { validateBucketName } from '../bucketName';

describe('validateBucketName — 정상 통과', () => {
	const valid = [
		'my-bucket',
		'data2025',
		'team-photos-v2',
		'abc',
		'a'.repeat(63),
		'x1y',
		'log-2025-01'
	];
	for (const name of valid) {
		it(`'${name}' 은 통과`, () => {
			expect(validateBucketName(name)).toBeNull();
		});
	}
});

describe('validateBucketName — 형식 위반', () => {
	const cases: Array<[string, string]> = [
		['ab', '3자 이상'],
		['a'.repeat(64), '63자 이하'],
		['MyBucket', '소문자'],
		['a.b', '점'],
		['my_bucket', '밑줄'],
		['my bucket', '공백'],
		['my!bucket', '사용할 수 없'],
		['foo-', '하이픈(-)으로 끝'],
		['a--b', '연속된 하이픈'],
		['192.168.1.1', '점']
	];
	for (const [name, keyword] of cases) {
		it(`'${name}' → '${keyword}' 사유`, () => {
			const result = validateBucketName(name);
			expect(result).not.toBeNull();
			expect(result).toContain(keyword);
		});
	}

	it('점으로 시작', () => {
		expect(validateBucketName('.hidden')).toContain('점');
	});
	it('하이픈으로 시작', () => {
		expect(validateBucketName('-leading')).toContain('하이픈');
	});
});

describe('validateBucketName — 예약어', () => {
	const exact = [
		'admin',
		'Admin',
		'ADMIN',
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
		'test-quarantine'
	];
	for (const name of exact) {
		it(`'${name}' (예약어) 차단`, () => {
			const result = validateBucketName(name);
			expect(result).not.toBeNull();
			expect(result).toContain('예약');
		});
	}
});

describe('validateBucketName — suffix/prefix', () => {
	it('foo-quarantine 차단', () => {
		expect(validateBucketName('foo-quarantine')).toContain('quarantine');
	});
	it('aws-data 차단', () => {
		expect(validateBucketName('aws-data')).toContain('시작하는');
	});
	it('amazon-x 차단', () => {
		expect(validateBucketName('amazon-x')).toContain('시작하는');
	});
});

describe('validateBucketName — 입력', () => {
	it('비-string 차단', () => {
		expect(validateBucketName(123 as unknown as string)).toContain('문자열');
	});
	it('앞뒤 공백 차단', () => {
		expect(validateBucketName(' my-bucket ')).toContain('공백');
	});
	it('빈 문자열 차단', () => {
		expect(validateBucketName('')).toContain('비어');
	});
});
