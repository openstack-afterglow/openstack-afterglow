import type {
	WaygateClient,
	WaygateClientCreateRequest,
	WaygateClientUpdateRequest,
	WaygateServer,
	WaygateServerCreateRequest,
	WaygateServerUpdateRequest,
} from '$lib/types/waygate';

export const WAYGATE_MTU_MIN = 576;
export const WAYGATE_MTU_MAX = 9000;
export const WAYGATE_KEEPALIVE_DEFAULT = 25;
export const WAYGATE_KEEPALIVE_MAX = 65535;

export interface WaygateClientDraft {
	name: string;
	dns: string;
	mtu: string;
	persistentKeepalive: string;
	inheritDns: boolean;
	inheritPersistentKeepalive: boolean;
}

export type WaygateClientDraftErrors = Partial<Record<keyof WaygateClientDraft, string>>;

export type WaygateClientSettingsResult<T> =
	| { ok: true; body: T }
	| { ok: false; errors: WaygateClientDraftErrors };

const NAME_RE = /^[a-zA-Z0-9][a-zA-Z0-9_-]{0,62}$/;
const DNS_HOST_RE = /^[A-Za-z0-9.:_-]{1,253}$/;

export function emptyWaygateClientDraft(): WaygateClientDraft {
	return { name: '', dns: '', mtu: '', persistentKeepalive: String(WAYGATE_KEEPALIVE_DEFAULT), inheritDns: true, inheritPersistentKeepalive: true };
}

export function waygateServerDraft(server?: WaygateServer): WaygateClientDraft {
	return {
		name: server?.name ?? '',
		dns: server?.dns ?? '',
		mtu: '',
		persistentKeepalive: String(server?.persistent_keepalive ?? WAYGATE_KEEPALIVE_DEFAULT),
		inheritDns: false,
		inheritPersistentKeepalive: false,
	};
}

export function waygateClientDraft(client: WaygateClient): WaygateClientDraft {
	return {
		name: client.name,
		dns: client.dns ?? '',
		mtu: client.mtu === null ? '' : String(client.mtu),
		persistentKeepalive: String(client.persistent_keepalive),
		inheritDns: client.inherit_dns ?? false,
		inheritPersistentKeepalive: client.inherit_persistent_keepalive ?? false,
	};
}

function integerInRange(raw: string, min: number, max: number): number | null {
	if (!/^\d+$/.test(raw)) return null;
	const value = Number(raw);
	return value >= min && value <= max ? value : null;
}

/** Mirrors Waygate request validation; the service remains authoritative. */
function parseDraft(draft: WaygateClientDraft, nameMode: 'required' | 'optional' | 'none' = 'required', server = false) {
	const errors: WaygateClientDraftErrors = {};
	const name = draft.name.trim();
	if (nameMode !== 'none' && (nameMode === 'required' || name !== '') && !NAME_RE.test(name)) {
		errors.name = '영문/숫자로 시작하고 영문·숫자·하이픈·밑줄만 사용해 최대 63자로 입력하세요.';
	}
	const dnsInput = draft.dns.trim();
	const hosts = dnsInput ? dnsInput.split(',').map((host) => host.trim()) : [];
	if ((server || !draft.inheritDns) && (hosts.length > 2 || dnsInput.length > 255 || hosts.some((host) => !DNS_HOST_RE.test(host)))) {
		errors.dns = '쉼표로 구분한 DNS 주소나 호스트 이름을 최대 두 개 입력하세요.';
	}
	const mtuInput = draft.mtu.trim();
	const mtu = mtuInput ? integerInRange(mtuInput, WAYGATE_MTU_MIN, WAYGATE_MTU_MAX) : null;
	if (!server && mtuInput && mtu === null) errors.mtu = `${WAYGATE_MTU_MIN}–${WAYGATE_MTU_MAX} 사이의 정수를 입력하거나 비워 두세요.`;
	const persistentKeepalive = integerInRange(draft.persistentKeepalive.trim(), 0, WAYGATE_KEEPALIVE_MAX);
	if ((server || !draft.inheritPersistentKeepalive) && persistentKeepalive === null) errors.persistentKeepalive = `0–${WAYGATE_KEEPALIVE_MAX}초 사이의 정수를 입력하세요. 0은 비활성화입니다.`;
	return {
		errors,
		values: { name, dns: hosts.length ? hosts.join(', ') : null, mtu, persistentKeepalive: persistentKeepalive ?? 0 },
	};
}

export function waygateServerCreateBody(draft: WaygateClientDraft): WaygateClientSettingsResult<WaygateServerCreateRequest> {
	const { errors, values } = parseDraft(draft, 'optional', true);
	if (Object.keys(errors).length) return { ok: false, errors };
	return {
		ok: true,
		body: { name: values.name, dns: values.dns, persistent_keepalive: values.persistentKeepalive },
	};
}

export function waygateServerUpdateBody(draft: WaygateClientDraft): WaygateClientSettingsResult<WaygateServerUpdateRequest> {
	const { errors, values } = parseDraft(draft, 'none', true);
	if (Object.keys(errors).length) return { ok: false, errors };
	return { ok: true, body: { dns: values.dns, persistent_keepalive: values.persistentKeepalive } };
}
export function waygateClientCreateBody(draft: WaygateClientDraft): WaygateClientSettingsResult<WaygateClientCreateRequest> {
	const { errors, values } = parseDraft(draft);
	if (Object.keys(errors).length) return { ok: false, errors };
	return {
		ok: true,
		body: {
			name: values.name,
			inherit_dns: draft.inheritDns,
			inherit_persistent_keepalive: draft.inheritPersistentKeepalive,
			...(!draft.inheritDns ? { dns: values.dns } : {}),
			...(!draft.inheritPersistentKeepalive ? { persistent_keepalive: values.persistentKeepalive } : {}),
			mtu: values.mtu,
		},
	};
}

/** Sends explicit MTU on edit so a blank value clears any stored override. */
export function waygateClientUpdateBody(
	client: WaygateClient,
	draft: WaygateClientDraft
): WaygateClientSettingsResult<WaygateClientUpdateRequest> {
	const { errors, values } = parseDraft(draft);
	if (Object.keys(errors).length) return { ok: false, errors };
	const body: WaygateClientUpdateRequest = {
		inherit_dns: draft.inheritDns,
		inherit_persistent_keepalive: draft.inheritPersistentKeepalive,
		...(!draft.inheritDns ? { dns: values.dns } : {}),
		...(!draft.inheritPersistentKeepalive ? { persistent_keepalive: values.persistentKeepalive } : {}),
		mtu: values.mtu,
	};
	if (values.name !== client.name) body.name = values.name;
	return { ok: true, body };
}
