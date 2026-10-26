import { clearPrefetchCache, getBaseUrl } from '$lib/api/client';

export interface TransferAuthority { token: string; projectId?: string }
export interface VolumeTransfer { id: string; name: string; volume_id: string; created_at?: string | null }
export interface IssuedVolumeTransfer extends VolumeTransfer { auth_key: string }
export interface VolumeTransferLookup extends VolumeTransfer {
	volume_name: string; size: number; volume_type: string | null; status: 'awaiting-transfer';
	source_project: { id: string; name: string }; source_domain: { id: string; name: string };
}
export class VolumeTransferError extends Error {
	constructor(public status: number, public uncertain: boolean, public detail = '') {
		super('Volume transfer request did not complete');
	}
}

// Secret-bearing writes never enter the shared response cache, refresh/replay,
// request coalescing or prefetch paths. Explicit new clicks are the only sends.
async function request<T>(path: string, authority: TransferAuthority, method: 'GET' | 'POST' | 'DELETE', body?: unknown): Promise<T> {
	if (method !== 'GET') clearPrefetchCache({ token: authority.token });
	try {
		const response = await fetch(`${getBaseUrl()}/api/v1/${path}`, {
			method, cache: 'no-store', credentials: 'include', redirect: 'error',
			signal: AbortSignal.timeout(90_000),
			headers: { Authorization: `Bearer ${authority.token}`, Accept: 'application/json',
				...(authority.projectId ? { 'X-Project-Id': authority.projectId } : {}),
				...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
				'X-Afterglow-Page': typeof window === 'undefined' ? '/admin/volumes' : window.location.pathname },
			...(body === undefined ? {} : { body: JSON.stringify(body) }),
		});
		if (!response.ok) {
			const envelope = await response.json().catch(() => null);
			// Keys must never be reflected into errors, logs or Error.message.
			const detail = response.status < 500 && typeof envelope?.detail === 'string' ? envelope.detail : '';
			throw new VolumeTransferError(response.status, method !== 'GET' && response.status >= 500, detail);
		}
		return response.status === 204 ? undefined as T : await response.json() as T;
	} catch (error) {
		if (error instanceof VolumeTransferError) throw error;
		throw new VolumeTransferError(503, method !== 'GET');
	} finally {
		if (method !== 'GET') clearPrefetchCache({ token: authority.token });
	}
}
const id = encodeURIComponent;
export const adminVolumeTransfers = {
	create: (authority: TransferAuthority, volumeId: string) => request<IssuedVolumeTransfer>(`admin/volumes/${id(volumeId)}/transfer`, authority, 'POST', {}),
	lookup: (authority: TransferAuthority, transferId: string) => request<VolumeTransferLookup>(`volumes/transfer/${id(transferId)}`, authority, 'GET'),
	accept: (authority: TransferAuthority, transferId: string, key: string, domainId: string, projectId: string) => request<VolumeTransfer>(`admin/volumes/transfer/${id(transferId)}/accept`, authority, 'POST', { auth_key: key, target_domain_id: domainId, target_project_id: projectId }),
	cancel: (authority: TransferAuthority, transferId: string) => request<void>(`admin/volumes/transfer/${id(transferId)}`, authority, 'DELETE'),
	pending: (authority: TransferAuthority, volumeId: string) => request<VolumeTransfer[]>(`admin/volumes/${id(volumeId)}/transfers`, authority, 'GET'),
};
