import { beforeEach, describe, expect, it, vi } from 'vitest';
import { initLocale } from '$lib/i18n/runtime.svelte';
import { t } from '$lib/i18n/ns/domain-auth';
import { beginAuthExperience, observedAuthText, createAuthNoticePresenter } from '../authExperience';
import type { ExperienceContext } from '$lib/utils/experience';

const observations = vi.hoisted(() => ({
	begin: vi.fn(), load: vi.fn(), applied: vi.fn(), discarded: vi.fn(), message: vi.fn(), state: vi.fn(), record: vi.fn(),
}));
vi.mock('$lib/utils/experience', () => ({
	beginExperienceAction: observations.begin,
	beginExperienceLoad: observations.load,
	experienceApplied: observations.applied,
	experienceDiscarded: observations.discarded,
	experienceMessage: observations.message,
	experienceState: observations.state,
	recordExperience: observations.record,
}));
const context = Object.freeze({ segmentId: 'anonymous-segment', actionId: 'one-use-action' }) as unknown as ExperienceContext;

beforeEach(() => {
	vi.resetAllMocks(); initLocale('en');
	observations.begin.mockReturnValue(context);
	observations.load.mockReturnValue(context);
	observations.applied.mockResolvedValue(undefined);
});

describe('explicit standalone auth observations', () => {
	it('uses an unlinked source load for mounted discovery instead of inventing a human action', () => {
		const observation = beginAuthExperience('auth.callback', 'load', () => true);
		expect(observation.options).toEqual({ experience: context });
		expect(observations.load).toHaveBeenCalledExactlyOnceWith('auth', 'auth.callback');
		expect(observations.begin).not.toHaveBeenCalled();
	});

	it('preserves default-off request options and never invents a context', () => {
		observations.begin.mockReturnValue(undefined);
		const observation = beginAuthExperience('auth.recover', 'inspect', () => true, 'account');
		expect(observation.context).toBeUndefined();
		expect(observation.options).toEqual({});
	});

	it('carries the original form action into its one-use parent request without beginning another action', () => {
		const form = beginAuthExperience('auth.invitation', 'create', () => true);
		const parent = beginAuthExperience('auth.invitation', 'create', () => true, 'account', form.context);
		expect(parent.options).toEqual({ experience: context });
		expect(observations.begin).toHaveBeenCalledOnce();
	});

	it('passes the actual generation/liveness assertion through the DOM tick instead of trusting matching current identities', async () => {
		let epoch = 0;
		const captured = epoch;
		let mounted = true;
		const observation = beginAuthExperience('auth.callback', 'verify', () => mounted && captured === epoch);
		await observation.applied();
		const guard = observations.applied.mock.calls[0][2] as () => boolean;
		expect(guard()).toBe(true);
		epoch++; epoch++; // Product owner A -> B -> A still has a different generation.
		expect(guard()).toBe(false);
		mounted = false;
		await observation.applied();
		expect(observations.applied).toHaveBeenCalledOnce();
		expect(observations.discarded).not.toHaveBeenCalled();
	});

	it('fences a replaced state snapshot even when its mounted action owner remains current', async () => {
		let state = { loading: false };
		const appliedState = state;
		const observation = beginAuthExperience('auth.recover', 'verify', () => true);
		await observation.applied(() => state === appliedState);
		const guard = observations.applied.mock.calls[0][2] as () => boolean;
		state = { loading: false };
		expect(guard()).toBe(false);
	});

	it('captures the actual message locale at formatting time without recording text or formatting parameters', () => {
		const observation = beginAuthExperience('auth.callback', 'verify', () => true);
		const text = observedAuthText(observation, 'domain-auth', t);
		expect(text('callback.failed', { status: 503 })).toBe(t('callback.failed', { status: 503 }));
		expect(observations.message).toHaveBeenLastCalledWith(context, expect.objectContaining({ key: 'domain-auth:callback.failed', locale: 'en', tone: 'danger', restoration: 'restored' }));
		initLocale('ko');
		text('callback.failed', { status: 409 });
		expect(observations.message).toHaveBeenLastCalledWith(context, expect.objectContaining({ locale: 'ko' }));
		for (const [, metadata] of observations.message.mock.calls) {
			expect(Object.keys(metadata).sort()).toEqual(['catalog_revision', 'key', 'locale', 'restoration', 'tone']);
		}
		expect(observations.begin).toHaveBeenCalledOnce();
	});

	it('uses unavailable metadata for an untrusted server error without accepting the error text', () => {
		const observation = beginAuthExperience('mcp.consent', 'approve', () => true, 'mcp');
		observation.unknownMessage();
		expect(observations.message).toHaveBeenCalledWith(context, expect.objectContaining({ key: null, locale: 'unknown', restoration: 'unavailable', tone: 'danger' }));
	});
});

it('keeps one visible notice on its original producer across unrelated actions and locale changes', () => {
	const nextContext = Object.freeze({ segmentId: 'next-source' }) as unknown as ExperienceContext;
	observations.begin.mockReturnValueOnce(context).mockReturnValueOnce(nextContext);
	const initial = beginAuthExperience('auth.callback', 'verify', () => true);
	const unrelated = beginAuthExperience('auth.callback', 'approve', () => true);
	const present = createAuthNoticePresenter();
	present('result', undefined, 'domain-auth', 'link.description');
	present('result', initial, 'domain-auth', 'link.description');
	present('result', unrelated, 'domain-auth', 'link.description');
	expect(observations.message).toHaveBeenCalledOnce();
	expect(observations.message).toHaveBeenLastCalledWith(context, expect.objectContaining({ locale: 'en' }));
	initLocale('ko');
	present('result', unrelated, 'domain-auth', 'link.description');
	expect(observations.message).toHaveBeenCalledTimes(2);
	expect(observations.message).toHaveBeenLastCalledWith(context, expect.objectContaining({ locale: 'ko' }));
	present('result', unrelated, 'domain-auth', null);
	present('result', unrelated, 'domain-auth', 'link.description');
	expect(observations.message).toHaveBeenCalledTimes(3);
	expect(observations.message).toHaveBeenLastCalledWith(nextContext, expect.objectContaining({ locale: 'ko' }));
});
