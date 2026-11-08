import { describe, expect, it, beforeEach } from 'vitest';
import { ApiError } from '$lib/api/errors';
import { mockObjectStorage } from './objectStorage';
import { resetMockupState } from './state';

describe('mockObjectStorage bucket lifecycle', () => {
	beforeEach(() => resetMockupState());

	it('creates a bucket that then appears in the list', () => {
		mockObjectStorage('POST', '/api/v1/object-storage', { name: 'qa-bucket' });
		const names = (mockObjectStorage('GET', '/api/v1/object-storage', null) as { name: string }[]).map((item) => item.name);
		expect(names).toEqual(['sample-artifacts', 'qa-bucket']);
	});

	it('moves a deleted bucket to trash and restores it on request', () => {
		mockObjectStorage('DELETE', '/api/v1/object-storage/sample-artifacts', null);
		expect(mockObjectStorage('GET', '/api/v1/object-storage', null)).toEqual([]);
		expect(mockObjectStorage('GET', '/api/v1/object-storage/trash/containers', null)).toEqual([
			{ name: 'sample-artifacts', count: 12, bytes: 734003200 },
		]);
		mockObjectStorage('POST', '/api/v1/object-storage/trash/containers/sample-artifacts/restore', {});
		expect((mockObjectStorage('GET', '/api/v1/object-storage', null) as { name: string }[]).map((item) => item.name)).toEqual(['sample-artifacts']);
		expect(mockObjectStorage('GET', '/api/v1/object-storage/trash/containers', null)).toEqual([]);
	});

	it('purges a trashed bucket permanently', () => {
		mockObjectStorage('DELETE', '/api/v1/object-storage/sample-artifacts', null);
		mockObjectStorage('DELETE', '/api/v1/object-storage/trash/containers/sample-artifacts', null);
		expect(mockObjectStorage('GET', '/api/v1/object-storage/trash/containers', null)).toEqual([]);
		expect(mockObjectStorage('GET', '/api/v1/object-storage', null)).toEqual([]);
	});

	it('rejects a duplicate name, including a name still in trash', () => {
		expect(() => mockObjectStorage('POST', '/api/v1/object-storage', { name: 'sample-artifacts' })).toThrow(ApiError);
		mockObjectStorage('DELETE', '/api/v1/object-storage/sample-artifacts', null);
		expect(() => mockObjectStorage('POST', '/api/v1/object-storage', { name: 'sample-artifacts' })).toThrow(ApiError);
	});

	it('returns undefined for paths it does not own', () => {
		expect(mockObjectStorage('GET', '/api/v1/volumes', null)).toBeUndefined();
	});
});
