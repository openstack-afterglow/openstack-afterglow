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

type Slot = Pick<PendingTopup, 'userId' | 'domainId'>;

/** True when a `storage` event may have changed any tab's pending top-ups (`null` = cleared). */
export function affectsPendingTopups(storageName: string | null): boolean {
	return storageName === null || storageName.startsWith(prefix);
}

/** Serializes every claim and release of one admin+domain slot across tabs. */
function withSlotLock<T>(slot: Slot, critical: () => T): Promise<T> {
	const locks = typeof navigator === 'undefined' ? undefined : navigator.locks;
	// Without Web Locks the read → write → read-back compare-and-set inside `critical` is the guard.
	if (!locks?.request) return Promise.resolve().then(critical);
	return locks.request(`afterglow-topup:${encodeURIComponent(slot.userId)}:${encodeURIComponent(slot.domainId)}`, critical) as Promise<T>;
}

export type TopupClaim = { status: 'claimed' } | { status: 'held'; existing: PendingTopup } | { status: 'unavailable' };

/**
 * Claim the admin+domain slot for this exact operation before dispatch. `held` is another
 * tab's uncertain operation, which must be recovered first instead of being replaced by a
 * fresh key; `unavailable` means the record is not durable, so nothing may be sent.
 */
export async function claimPendingTopup(record: PendingTopup): Promise<TopupClaim> {
	try {
		return await withSlotLock(record, (): TopupClaim => {
			const name = storageKey(record.userId, record.domainId);
			const existing = parse(localStorage.getItem(name), record.userId, record.domainId);
			if (existing && existing.key !== record.key) return { status: 'held', existing };
			const serialized = JSON.stringify(record);
			localStorage.setItem(name, serialized);
			const stored = localStorage.getItem(name);
			if (stored === serialized) return { status: 'claimed' };
			const winner = parse(stored, record.userId, record.domainId);
			return winner && winner.key !== record.key ? { status: 'held', existing: winner } : { status: 'unavailable' };
		});
	} catch {
		return { status: 'unavailable' };
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

/** Compare-and-delete: removes the slot only while it still holds this exact key. */
export async function releasePendingTopup(record: Pick<PendingTopup, 'userId' | 'domainId' | 'key'>): Promise<void> {
	try {
		await withSlotLock(record, () => {
			const name = storageKey(record.userId, record.domainId);
			if (parse(localStorage.getItem(name), record.userId, record.domainId)?.key === record.key) localStorage.removeItem(name);
		});
	} catch {
		// Nothing persisted to clear.
	}
}
