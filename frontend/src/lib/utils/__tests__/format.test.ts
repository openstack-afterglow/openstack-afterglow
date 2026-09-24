// @vitest-environment node
import { describe, it, expect } from 'vitest';
import { formatDate, formatNumber, formatStorage, shortContentType } from '../format';

describe('formatDate', () => {
	it('유효한 ISO 문자열을 날짜로 포맷한다', () => {
		const result = formatDate('2024-03-15T00:00:00Z');
		expect(result).toMatch(/2024/);
		expect(result).toMatch(/03/);
		expect(result).toMatch(/15/);
	});

	it('빈 문자열은 "-" 반환', () => {
		expect(formatDate('')).toBe('-');
	});

	it('잘못된 날짜 문자열은 "-" 반환', () => {
		expect(formatDate('not-a-date')).toBe('-');
	});

	it('날짜만 있는 문자열도 처리', () => {
		const result = formatDate('2025-01-01');
		expect(result).toMatch(/2025/);
	});
});

describe('formatNumber', () => {
	it('양수에 천단위 구분자 적용', () => {
		const result = formatNumber(1234567);
		expect(result).toContain('1');
		expect(result.replace(/\D/g, '')).toBe('1234567');
	});

	it('0은 "0" 반환', () => {
		expect(formatNumber(0)).toBe('0');
	});

	it('음수도 처리', () => {
		const result = formatNumber(-1000);
		expect(result).toContain('1');
		expect(result).toContain('000');
	});

	it('소수도 처리', () => {
		const result = formatNumber(1.5);
		expect(result).toContain('1');
	});
});

describe('formatStorage', () => {
	it('1000 GB 미만은 GB 단위 반환', () => {
		expect(formatStorage(512)).toContain('GB');
		expect(formatStorage(512)).toContain('512');
	});

	it('1000 GB 이상은 TB 단위로 변환', () => {
		const result = formatStorage(2000);
		expect(result).toContain('TB');
		expect(result).toContain('2');
	});

	it('1_000_000 GB 이상은 PB 단위로 변환', () => {
		const result = formatStorage(3_000_000);
		expect(result).toContain('PB');
		expect(result).toContain('3');
	});

	it('0 GB 처리', () => {
		expect(formatStorage(0)).toContain('GB');
	});

	it('정확히 1000 GB는 TB', () => {
		const result = formatStorage(1000);
		expect(result).toContain('TB');
	});

	it('소수점 TB 포맷', () => {
		const result = formatStorage(1500);
		expect(result).toContain('TB');
		expect(result).toContain('1.5');
	});
});

describe('shortContentType', () => {
	it('알려진 MIME 타입을 짧은 레이블로 변환', () => {
		expect(shortContentType('application/pdf')).toBe('PDF');
		expect(shortContentType('application/zip')).toBe('ZIP');
		expect(shortContentType('image/png')).toBe('PNG');
		expect(shortContentType('image/jpeg')).toBe('JPG');
		expect(shortContentType('text/html')).toBe('HTML');
	});

	it('null/undefined는 "-" 반환', () => {
		expect(shortContentType(null)).toBe('-');
		expect(shortContentType(undefined)).toBe('-');
		expect(shortContentType('')).toBe('-');
	});

	it('MS Office 확장자 처리', () => {
		expect(shortContentType('application/vnd.openxmlformats-officedocument.wordprocessingml.document')).toBe('DOCX');
		expect(shortContentType('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')).toBe('XLSX');
		expect(shortContentType('application/vnd.openxmlformats-officedocument.presentationml.presentation')).toBe('PPTX');
	});

	it('알려지지 않은 MIME 타입은 subtype 마지막 점 뒤 토큰 대문자', () => {
		// x- 제거 후 마지막 점 뒤 토큰 추출, 최대 8자
		expect(shortContentType('application/x-something.format')).toBe('FORMAT');
		// 점 없는 경우 x- 제거 후 전체를 최대 8자로
		expect(shortContentType('application/x-custom-format')).toBe('CUSTOM-F');
	});

	it('슬래시 없는 타입은 원본 반환 (최대 12자)', () => {
		const result = shortContentType('plaintext');
		expect(result).toBe('plaintext');
	});

	it('알려진 video 타입 처리', () => {
		expect(shortContentType('video/mp4')).toBe('MP4');
		expect(shortContentType('audio/mpeg')).toBe('MP3');
	});

	it('x- 접두어 제거 후 subtype 추출', () => {
		const result = shortContentType('application/x-tar');
		expect(result).toBe('TAR');
	});
});
