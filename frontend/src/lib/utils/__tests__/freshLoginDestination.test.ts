import { beforeEach, describe, expect, it } from 'vitest';
import { freshLoginDestination, storeMcpConsentTicket, pendingMcpConsentTicket } from '../mcpConsent';
import { storePendingInvitation, takePendingInvitationPath } from '../domainLogin';

beforeEach(() => sessionStorage.clear());
describe('fresh established login continuation', () => {
	it('goes straight to an established project without explicit intent', () => {
		expect(freshLoginDestination('/dashboard')).toBe('/dashboard');
	});
	it.each(['/select-domain', '/select-project'])('retains every intent until a project is established at %s', target => {
		storePendingInvitation('i'.repeat(32)); storeMcpConsentTicket('m'.repeat(32));
		expect(freshLoginDestination(target)).toBe(target);
		expect(takePendingInvitationPath()).toBe(`/invitations/${'i'.repeat(32)}`);
		expect(pendingMcpConsentTicket()).toBe('m'.repeat(32));
	});
	it('resumes invitation once before the preserved MCP continuation', () => {
		storePendingInvitation('i'.repeat(32)); storeMcpConsentTicket('m'.repeat(32));
		expect(freshLoginDestination('/dashboard')).toBe(`/invitations/${'i'.repeat(32)}`);
		expect(takePendingInvitationPath()).toBeNull();
		expect(freshLoginDestination('/dashboard')).toBe('/oauth/mcp/authorize');
		expect(pendingMcpConsentTicket()).toBe('m'.repeat(32));
	});
});
