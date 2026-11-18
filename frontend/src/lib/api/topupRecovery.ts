import { validDomainCredit } from './chatDomainBilling';

/**
 * A top-up whose outcome is unknown. It holds only the operation identity (no
 * credential), so a reload or later visit can retry with the SAME idempotency
 * key instead of minting a new one and applying the money write twice.
 */
export interface PendingTopup {
	v: 1;
	userId: string;
	domainId: string;
	key: string;
	amount_credits: string;
	note: string | null;
	created_at: string;
}

const prefix = 'afterglow:lumen-topup:v1:';
const ownerPrefix = (userId: string) => `${prefix}${encodeURIComponent(userId)}:`;
const storageKey = (userId: string, domainId: string) => `${ownerPrefix(userId)}${encodeURIComponent(domainId)}`;

function parse(raw: string | null, userId: string, domainId: string): PendingTopup | null {
	try {
		const value: unknown = JSON.parse(raw ?? 'null');
		if (!value || typeof value !== 'object') return null;
		const record = value as Record<string, unknown>;
		const valid = record.v === 1 && record.userId === userId && record.domainId === domainId
			&& typeof record.key === 'string' && /^[\w-]{1,120}$/.test(record.key)
			&& typeof record.amount_credits === 'string' && validDomainCredit(record.amount_credits, true)
			&& (record.note === null || (typeof record.note === 'string' && record.note.length <= 1000))
			&& typeof record.created_at === 'string' && Number.isFinite(Date.parse(record.created_at));
		return valid ? record as unknown as PendingTopup : null;
	} catch {
		return null;
	}
}

/** Persist and read back before dispatch; false means the caller must not send the money write. */
export function savePendingTopup(record: PendingTopup): boolean {
	try {
		const name = storageKey(record.userId, record.domainId);
		const serialized = JSON.stringify(record);
		localStorage.setItem(name, serialized);
		return localStorage.getItem(name) === serialized;
	} catch {
		return false;
	}
}

export function pendingTopups(userId: string): PendingTopup[] {
	const records: PendingTopup[] = [];
	try {
		const owner = ownerPrefix(userId);
		for (let index = 0; index < localStorage.length; index += 1) {
			const name = localStorage.key(index);
			if (!name?.startsWith(owner)) continue;
			const record = parse(localStorage.getItem(name), userId, decodeURIComponent(name.slice(owner.length)));
			if (record) records.push(record);
		}
	} catch {
		// Storage is unavailable; only in-memory recovery remains.
	}
	return records;
}

export function clearPendingTopup(record: Pick<PendingTopup, 'userId' | 'domainId'>): void {
	try {
		localStorage.removeItem(storageKey(record.userId, record.domainId));
	} catch {
		// Nothing persisted to clear.
	}
}
