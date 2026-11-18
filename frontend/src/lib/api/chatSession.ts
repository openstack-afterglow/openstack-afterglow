const PREFIX = 'afterglow:chat:active-conversation:';

function storage(): Storage | null {
	return typeof window === 'undefined' ? null : window.sessionStorage;
}

function key(owner: string): string {
	return `${PREFIX}${owner}`;
}

/** Persistent chat IDs are non-secret routing state; message content is never stored here. */
export function loadActiveConversationId(owner: string): string | null {
	try {
		return storage()?.getItem(key(owner)) || null;
	} catch {
		return null;
	}
}

export function saveActiveConversationId(owner: string, conversationId: string): void {
	try {
		storage()?.setItem(key(owner), conversationId);
	} catch {
		// Private browsing/storage policy must not block chat navigation.
	}
}

export function clearActiveConversationId(owner: string): void {
	try {
		storage()?.removeItem(key(owner));
	} catch {
		// Private browsing/storage policy must not block chat navigation.
	}
}
