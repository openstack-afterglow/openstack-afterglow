/** Cinder volume attached to an instance, as reported by `GET /instances/{id}/volumes`. */
export interface VolumeAttachment {
	volume_id: string;
	name?: string | null;
	device?: string | null;
	delete_on_termination?: boolean;
	size?: number | null;
	status?: string | null;
}

/**
 * Manila share associated with an instance by `GET /instances/{id}/storage-attachments`.
 * This is the access-rule association Afterglow tracks, not proof that the guest mounted the share.
 */
export interface StorageAttachment {
	file_storage_id: string;
	name: string | null;
	share_proto: string | null;
	status: string;
	access_to?: string | null;
	access_level?: string | null;
	/** Provider rule state (`active`, `queued_to_apply`, `missing`, `untracked`, `unknown`, ...). */
	state?: string;
	/** `tracked`, `untracked`, `mismatch` or `unknown`. */
	association_state?: string | null;
	managed?: boolean;
	exports?: unknown[];
}
