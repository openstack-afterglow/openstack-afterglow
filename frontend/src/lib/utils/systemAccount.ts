import type { SystemAccountIdentity } from '$lib/types/common';

// Native identity/domain validation belongs to the backend. Names are not identity proof.
export function isSystemAccount(identity: SystemAccountIdentity | null | undefined): boolean {
	return identity?.system_account?.kind === 'auto_backup';
}
