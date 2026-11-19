import { afterEach, describe, expect, it } from 'vitest';
import { get } from 'svelte/store';
import { auth, clearAuth } from '$lib/stores/auth';
import { isPersonalWorkspace, personalWorkspace } from '$lib/stores/personalWorkspace';
import { t } from '$lib/i18n/ns/chat-settings';
import { ApiError } from '../errors';
import { ChatHttpError } from '../chatStream';
import { dashboardCreditMessage, isDomainCreditInsufficient } from '../chatDomainBilling';

const personal = { id: 'personal', name: 'Personal', kind: 'personal' as const };
const organization = { id: 'dmslab', name: 'dmslab', kind: 'organization' as const };

function workIn(domainId: string) {
	auth.set({ ...get(auth), token: 'token', domainId, availableDomains: [personal, organization] });
}

afterEach(() => clearAuth());

describe('personal workspace detection', () => {
	it('follows the current working domain kind only', () => {
		expect(isPersonalWorkspace({ domainId: 'personal', availableDomains: [personal, organization] })).toBe(true);
		expect(isPersonalWorkspace({ domainId: 'dmslab', availableDomains: [personal, organization] })).toBe(false);
		expect(isPersonalWorkspace({ domainId: 'legacy', availableDomains: [{ id: 'legacy', name: 'Legacy' }] })).toBe(false);
		expect(isPersonalWorkspace({ domainId: null, availableDomains: [personal] })).toBe(false);
		workIn('personal');
		expect(get(personalWorkspace)).toBe(true);
		workIn('dmslab');
		expect(get(personalWorkspace)).toBe(false);
	});
});

describe('domain_credit_insufficient mapping', () => {
	const refusals = [
		['chat admission code', new ChatHttpError('Request failed', 402, 'domain_credit_insufficient')],
		['Studio 402 detail', new ApiError(402, 'domain_credit_insufficient')],
		['Studio 429 detail', new ApiError(429, 'domain_credit_insufficient')],
		['pool 409 detail', new ApiError(409, 'domain_credit_insufficient', 'domain_credit_insufficient')],
		['run error code', 'domain_credit_insufficient']
	] as const;

	it.each(refusals)('guides personal projects to an organization for a %s', (_label, cause) => {
		workIn('personal');
		expect(isDomainCreditInsufficient(cause)).toBe(true);
		expect(dashboardCreditMessage(cause)).toBe(t('dashboardChat.personalUnavailable'));
		expect(t('dashboardChat.personalUnavailable')).toBe('개인 프로젝트에서는 대시보드 채팅을 사용할 수 없습니다. 조직(도메인)을 만들거나 조직 프로젝트로 전환해 사용하세요.');
	});

	it.each(refusals)('asks organization members to request a top-up for a %s', (_label, cause) => {
		workIn('dmslab');
		expect(dashboardCreditMessage(cause)).toBe(t('dashboardChat.organizationCreditInsufficient'));
		expect(t('dashboardChat.organizationCreditInsufficient')).toBe('도메인 크레딧이 부족합니다. 도메인 관리자 또는 시스템 관리자에게 충전을 요청하세요.');
	});

	it('leaves other billing and quota failures to their existing messages', () => {
		workIn('personal');
		for (const cause of [new ApiError(402, '월 사용 한도를 초과했습니다'), new ChatHttpError('Request failed', 409, 'domain_credit_limit_exceeds_ceiling'), 'quota_exceeded', null, undefined]) {
			expect(isDomainCreditInsufficient(cause)).toBe(false);
			expect(dashboardCreditMessage(cause)).toBeUndefined();
		}
	});
});
