export interface ProviderEntryTicket {
	entry_token: string;
	domain_id: string;
	action: 'connect' | 'create';
	email: string;
	username?: string;
	transfer_existing?: boolean;
}

/** Decode only the bounded callback metadata; bearer tickets never become error text. */
export function decodeProviderCallbackError(body: unknown): {
	code?: string;
	linkTicket?: { link_token: string; domain_id: string };
	entryTicket?: ProviderEntryTicket;
} {
	if (!body || typeof body !== 'object') return {};
	const root = body as Record<string, unknown>;
	const nested = root.detail && typeof root.detail === 'object' ? root.detail as Record<string, unknown> : null;
	const code = typeof root.code === 'string' ? root.code : typeof nested?.code === 'string' ? nested.code : undefined;
	const payload = typeof root.code === 'string' ? root : nested ?? root;
	const nonempty = (value: unknown): value is string => typeof value === 'string' && !!value.trim();
	if (code === 'account_link_required' && nonempty(payload.link_token) && nonempty(payload.domain_id)) {
		return { code, linkTicket: { link_token: payload.link_token, domain_id: payload.domain_id } };
	}
	if (code === 'account_entry_required' && nonempty(payload.entry_token) && nonempty(payload.domain_id)
		&& nonempty(payload.email) && (payload.action === 'connect' || payload.action === 'create')
		&& (payload.action !== 'connect' || nonempty(payload.username))
		&& (payload.transfer_existing === undefined || typeof payload.transfer_existing === 'boolean')) {
		return { code, entryTicket: {
			entry_token: payload.entry_token, domain_id: payload.domain_id, action: payload.action, email: payload.email,
			...(nonempty(payload.username) ? { username: payload.username } : {}),
			...(typeof payload.transfer_existing === 'boolean' ? { transfer_existing: payload.transfer_existing } : {}),
		} };
	}
	return { code };
}

export class ApiError extends Error {
	status: number;
	/** Stable JSON `code`, including known signup-approval codes returned as HTTP 403 `detail`. */
	code?: string;

	constructor(status: number, message: string, code?: string, public linkTicket?: { link_token: string; domain_id: string }, public entryTicket?: ProviderEntryTicket) {
		super(message);
		this.status = status;
		this.code = code;
	}
}
