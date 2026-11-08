import { api } from './client';

/** CIDRs that tenant and provider subnets of the domain may not overlap (VPN tunnel ranges). */
export interface VpnReservedRanges {
	domain_id: string;
	vpn_reserved_cidrs: string[];
	default_vpn_reserved_cidrs: string[];
	revision: number;
	configured: boolean;
	max_ranges: number;
}
export interface VpnReservedRangesAuthority {
	token: () => string;
	projectId: () => string | undefined;
	isCurrent: () => boolean;
	canSubmit: () => boolean;
}

/** Domain managers address only their session domain; system admins address an explicit domain. */
export function vpnReservedRanges(domainId: string, adminMode: boolean, authority: VpnReservedRangesAuthority) {
	const root = adminMode ? `/api/v1/admin/domains/${encodeURIComponent(domainId)}/vpn-reserved-ranges` : '/api/v1/iam/vpn-reserved-ranges';
	const dispatch = async <T>(send: () => Promise<T>, mutation = false): Promise<T> => {
		if (!authority.isCurrent() || (mutation && !authority.canSubmit())) throw new DOMException('', 'AbortError');
		try {
			const result = await send();
			if (!authority.isCurrent()) throw new DOMException('', 'AbortError');
			return result;
		} catch (cause) {
			if (!authority.isCurrent()) throw new DOMException('', 'AbortError');
			throw cause;
		}
	};
	const beforeDispatch = () => {
		if (!authority.isCurrent() || !authority.canSubmit()) throw new DOMException('', 'AbortError');
	};
	return {
		load: () => dispatch(() => api.get<VpnReservedRanges>(root, authority.token(), authority.projectId(), { cache: 'no-store' })),
		save: (revision: number, cidrs: string[]) => dispatch(() => api.put<VpnReservedRanges>(root, { revision, vpn_reserved_cidrs: cidrs }, authority.token(), authority.projectId(), { replayOnUnauthorized: false, beforeDispatch }), true)
	};
}

/** One CIDR per line or comma separated; blank entries are ignored. The server canonicalizes and validates. */
export function parseReservedRanges(text: string): string[] {
	return text.split(/[\s,]+/).map(value => value.trim()).filter(Boolean);
}
