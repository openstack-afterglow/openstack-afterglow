import { afterEach, describe, expect, it } from 'vitest';
import { auth } from '$lib/stores/auth';
import {
	beginClaudeGatewayAuthorization,
	clearClaudeGatewayAuthorization,
	clearMcpConsentTicket,
	pendingClaudeGatewayUserCode,
	pendingMcpConsentTicket,
	postAuthDestination,
	storeClaudeGatewayUserCode,
	storeMcpConsentTicket,
	storeLumenSourceContinuation,
} from './mcpConsent';

const ticket = 'A'.repeat(43);

afterEach(() => {
	sessionStorage.clear();
	auth.update((value) => ({ ...value, projectId: null }));
});

describe('MCP OAuth consent handoff', () => {
	it('persists only a valid ticket long enough to return after authentication', () => {
		expect(storeMcpConsentTicket(ticket)).toBe(true);
		expect(pendingMcpConsentTicket()).toBe(ticket);
		expect(postAuthDestination('/dashboard')).toBe('/oauth/mcp/authorize');
	});

	it('selects a project before returning to a pending OAuth request without losing its ticket', () => {
		storeMcpConsentTicket(ticket);
		expect(postAuthDestination('/select-project')).toBe('/select-project');
		expect(postAuthDestination('/select-domain')).toBe('/select-domain');
		expect(pendingMcpConsentTicket()).toBe(ticket);
		expect(postAuthDestination('/dashboard')).toBe('/oauth/mcp/authorize');
	});

	it('rejects malformed ticket values and clears the route destination after use', () => {
		expect(storeMcpConsentTicket('not a ticket')).toBe(false);
		expect(pendingMcpConsentTicket()).toBeNull();
		clearMcpConsentTicket();
		expect(postAuthDestination('/dashboard')).toBe('/dashboard');
	});
});

describe('Claude gateway authorization handoff', () => {
	it('returns to the public authorization shell and normalizes a device code', () => {
		beginClaudeGatewayAuthorization();
		expect(storeClaudeGatewayUserCode('abcd-2345')).toBe(true);
		expect(pendingClaudeGatewayUserCode()).toBe('ABCD-2345');
		expect(postAuthDestination('/dashboard')).toBe('/oauth/claude/authorize');
		expect(postAuthDestination('/select-domain')).toBe('/select-domain');
		expect(pendingClaudeGatewayUserCode()).toBe('ABCD-2345');
	});

	it('supports manual code entry after login without accepting ambiguous codes', () => {
		beginClaudeGatewayAuthorization();
		expect(storeClaudeGatewayUserCode('ABOI-1234')).toBe(false);
		expect(pendingClaudeGatewayUserCode()).toBeNull();
		expect(postAuthDestination('/dashboard')).toBe('/oauth/claude/authorize');

		clearClaudeGatewayAuthorization();
		expect(postAuthDestination('/dashboard')).toBe('/dashboard');
	});
});

it('preserves source intent while a projectless administrator continues to IAM', () => {
	const path = '/lumen/sources/runs/run-1/source-1';
	auth.update((value) => ({ ...value, projectId: null }));
	expect(storeLumenSourceContinuation(path)).toBe(true);
	expect(postAuthDestination('/dashboard/iam/users')).toBe('/dashboard/iam/users');
	auth.update((value) => ({ ...value, projectId: 'project-1' }));
	expect(postAuthDestination('/dashboard')).toBe(path);
	expect(postAuthDestination('/dashboard')).toBe('/dashboard');
});
