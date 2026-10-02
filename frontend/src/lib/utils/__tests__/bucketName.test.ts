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
	const cases = [
		'ab',
		'a'.repeat(64),
		'MyBucket',
		'a.b',
		'my_bucket',
		'my bucket',
		'my!bucket',
		'foo-',
		'a--b',
		'192.168.1.1'
	];
	for (const name of cases) {
		it(`'${name}' 차단`, () => {
			const result = validateBucketName(name);
			expect(result).not.toBeNull();
		});
	}

	it('점으로 시작', () => {
		expect(validateBucketName('.hidden')).not.toBeNull();
	});
	it('하이픈으로 시작', () => {
		expect(validateBucketName('-leading')).not.toBeNull();
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
		});
	}
});

describe('validateBucketName — suffix/prefix', () => {
	it('foo-quarantine 차단', () => {
		expect(validateBucketName('foo-quarantine')).not.toBeNull();
	});
	it('aws-data 차단', () => {
		expect(validateBucketName('aws-data')).not.toBeNull();
	});
	it('amazon-x 차단', () => {
		expect(validateBucketName('amazon-x')).not.toBeNull();
	});
});

describe('validateBucketName — 입력', () => {
	it('비-string 차단', () => {
		expect(validateBucketName(123 as unknown as string)).not.toBeNull();
	});
	it('앞뒤 공백 차단', () => {
		expect(validateBucketName(' my-bucket ')).not.toBeNull();
	});
	it('빈 문자열 차단', () => {
		expect(validateBucketName('')).not.toBeNull();
	});
});
