import { afterEach, describe, expect, it } from 'vitest';
import {
	beginClaudeGatewayAuthorization,
	clearClaudeGatewayAuthorization,
	clearMcpConsentTicket,
	pendingClaudeGatewayUserCode,
	pendingMcpConsentTicket,
	postAuthDestination,
	storeClaudeGatewayUserCode,
	storeMcpConsentTicket,
} from './mcpConsent';

const ticket = 'A'.repeat(43);

afterEach(() => {
	sessionStorage.clear();
});

describe('MCP OAuth consent handoff', () => {
	it('persists only a valid ticket long enough to return after authentication', () => {
		expect(storeMcpConsentTicket(ticket)).toBe(true);
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
