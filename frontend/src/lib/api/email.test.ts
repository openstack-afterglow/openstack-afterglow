import { describe, expect, it, vi } from 'vitest';
import { ApiError } from '$lib/api/errors';
vi.mock('$lib/api/client', () => ({ api: {}, ApiError }));
import { mailError, mailDispatchFailure, secretUpdate } from './email';
describe('email API security boundaries', () => {
	it('keeps write-only password actions explicit and never reuses the draft under keep or clear', () => {
		expect(secretUpdate('keep', 'discard-me', false)).toEqual({});
		expect(secretUpdate('keep', 'discard-me', true)).toEqual({ reconfirm_password: true });
		expect(secretUpdate('replace', 'new-secret', true)).toEqual({ password: 'new-secret' });
		expect(secretUpdate('clear', 'discard-me', true)).toEqual({ clear_password: true });
		expect(mailError(new ApiError(409, 'secret-bearing-provider-prose'))).toBe('conflict');
		expect(mailError(new ApiError(422, 'secret-bearing-input'))).toBe('failed');
	});
	it.each([403, 409, 422])('keeps definitive HTTP%s rejection editable without echoing error prose', status => {
		expect(mailDispatchFailure(new ApiError(status, 'secret-bearing-input', 'mail_invalid_subject'))).toEqual({ status: 'rejected', message: 'rejected', code: 'mail_invalid_subject' });
		expect(mailDispatchFailure(new ApiError(status, 'secret-bearing-input', 'private_provider_secret')).code).toBeUndefined();
	});
	it('distinguishes pre-enqueue identity failure from uncertain storage commit and network failures', () => {
		expect(mailDispatchFailure(new ApiError(503, 'private', 'mail_identity_unavailable')).status).toBe('rejected');
		expect(mailDispatchFailure(new ApiError(503, 'private', 'mail_storage_unavailable'))).toEqual({ status: 'indeterminate', message: 'unknown' });
		expect(mailDispatchFailure(new Error('private-network-error'))).toEqual({ status: 'indeterminate', message: 'unknown' });
	});
});
