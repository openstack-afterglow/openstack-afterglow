import { describe, expect, it, beforeEach } from 'vitest';
import { ApiError } from '$lib/api/errors';
import { mockContainers } from './containers';
import { resetMockupState } from './state';

type ListResponse = { items: { uuid: string; name: string; status: string }[]; service_available: boolean };

function list(): ListResponse {
	return mockContainers('GET', '/api/v1/containers', null) as ListResponse;
}

describe('mockContainers lifecycle', () => {
	beforeEach(() => resetMockupState());

	it('starts empty and lists a created container in state order', () => {
		expect(list().items).toEqual([]);
		mockContainers('POST', '/api/v1/containers', { name: 'qa-web', image: 'nginx:latest' });
		expect(list().items.map((item) => [item.name, item.status])).toEqual([['qa-web', 'Created']]);
	});

	it('rejects a missing image and a duplicate name', () => {
		expect(() => mockContainers('POST', '/api/v1/containers', { name: 'qa-web', image: '' })).toThrow(ApiError);
		mockContainers('POST', '/api/v1/containers', { name: 'qa-web', image: 'nginx:latest' });
		expect(() => mockContainers('POST', '/api/v1/containers', { name: 'qa-web', image: 'nginx:latest' })).toThrow(ApiError);
	});

	it('removes a stopped container but refuses to delete a running one', () => {
		mockContainers('POST', '/api/v1/containers', { name: 'qa-web', image: 'nginx:latest' });
		const uuid = list().items[0].uuid;
		mockContainers('POST', `/api/v1/containers/${uuid}/start`, {});
		expect(() => mockContainers('DELETE', `/api/v1/containers/${uuid}`, null)).toThrow(ApiError);
		expect(list().items).toHaveLength(1);
		mockContainers('POST', `/api/v1/containers/${uuid}/stop`, {});
		mockContainers('DELETE', `/api/v1/containers/${uuid}`, null);
		expect(list().items).toEqual([]);
	});

	it('returns undefined for paths it does not own', () => {
		expect(mockContainers('GET', '/api/v1/volumes', null)).toBeUndefined();
	});
});
