const CONSENT_TICKET_KEY = 'afterglow_mcp_oauth_consent_ticket';
const TICKET_PATTERN = /^[A-Za-z0-9_-]{32,128}$/;
const CLAUDE_GATEWAY_AUTH_KEY = 'afterglow_claude_gateway_authorization';
const CLAUDE_GATEWAY_CODE_KEY = 'afterglow_claude_gateway_user_code';
const CLAUDE_GATEWAY_CODE_PATTERN = /^[A-HJ-NP-Z2-9]{4}-?[A-HJ-NP-Z2-9]{4}$/;

function storage(): Storage | null {
	if (typeof window === 'undefined') return null;
	return window.sessionStorage;
}

export function storeMcpConsentTicket(ticket: string): boolean {
	if (!TICKET_PATTERN.test(ticket)) return false;
	storage()?.setItem(CONSENT_TICKET_KEY, ticket);
	return true;
}

export function pendingMcpConsentTicket(): string | null {
	const ticket = storage()?.getItem(CONSENT_TICKET_KEY) ?? null;
	return ticket && TICKET_PATTERN.test(ticket) ? ticket : null;
}

export function clearMcpConsentTicket(): void {
	storage()?.removeItem(CONSENT_TICKET_KEY);
}
export function beginClaudeGatewayAuthorization(): void {
	storage()?.setItem(CLAUDE_GATEWAY_AUTH_KEY, '1');
}

export function storeClaudeGatewayUserCode(value: string): boolean {
	const candidate = value.trim().toUpperCase();
	if (!CLAUDE_GATEWAY_CODE_PATTERN.test(candidate)) return false;
	const compact = candidate.replace('-', '');
	storage()?.setItem(CLAUDE_GATEWAY_CODE_KEY, `${compact.slice(0, 4)}-${compact.slice(4)}`);
	return true;
}

export function pendingClaudeGatewayUserCode(): string | null {
	const code = storage()?.getItem(CLAUDE_GATEWAY_CODE_KEY) ?? null;
	return code && CLAUDE_GATEWAY_CODE_PATTERN.test(code) ? code : null;
}

export function clearClaudeGatewayAuthorization(): void {
	storage()?.removeItem(CLAUDE_GATEWAY_AUTH_KEY);
	storage()?.removeItem(CLAUDE_GATEWAY_CODE_KEY);
}

export function hasPendingClaudeGatewayAuthorization(): boolean {
	return storage()?.getItem(CLAUDE_GATEWAY_AUTH_KEY) === '1';
}

export function postAuthDestination(fallback: string): string {
	if (pendingMcpConsentTicket()) return '/oauth/mcp/authorize';
	return hasPendingClaudeGatewayAuthorization() ? '/oauth/claude/authorize' : fallback;
}
