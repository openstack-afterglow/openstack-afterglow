import { t } from '$lib/i18n/ns/waygate';

/** Mirrors Waygate attachment routing validation; the service remains authoritative. */
export const WAYGATE_ALLOWED_IPS_MAX = 64;

interface ParsedCidr {
	version: 4 | 6;
	network: bigint;
	prefix: number;
}

const IPV4_OCTET = /^(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)$/;
const HEXTET = /^[0-9a-fA-F]{1,4}$/;

function parseIpv4(text: string): bigint | null {
	const parts = text.split('.');
	if (parts.length !== 4 || !parts.every((part) => IPV4_OCTET.test(part))) return null;
	return parts.reduce((value, part) => (value << 8n) | BigInt(Number(part)), 0n);
}

function parseIpv6(text: string): bigint | null {
	let head = text;
	let tail: number[] = [];
	// An embedded dotted IPv4 suffix occupies the last two hextets.
	const lastColon = head.lastIndexOf(':');
	if (head.includes('.')) {
		const ipv4 = parseIpv4(head.slice(lastColon + 1));
		if (ipv4 === null || lastColon < 0) return null;
		tail = [Number(ipv4 >> 16n), Number(ipv4 & 0xffffn)];
		head = head.slice(0, lastColon + 1);
		if (head.endsWith(':') && !head.endsWith('::')) head = head.slice(0, -1);
	}
	const halves = head.split('::');
	if (halves.length > 2) return null;
	const groups = (part: string) => (part === '' ? [] : part.split(':'));
	const left = groups(halves[0]);
	const right = halves.length === 2 ? groups(halves[1]) : [];
	if (![...left, ...right].every((group) => HEXTET.test(group))) return null;
	const explicit = left.length + right.length + tail.length;
	if (halves.length === 1 ? explicit !== 8 : explicit > 7) return null;
	const hextets = [
		...left.map((group) => parseInt(group, 16)),
		...Array<number>(8 - explicit).fill(0),
		...right.map((group) => parseInt(group, 16)),
		...tail,
	];
	return hextets.reduce((value, hextet) => (value << 16n) | BigInt(hextet), 0n);
}

function bitsOf(version: 4 | 6): number {
	return version === 4 ? 32 : 128;
}

function parseCidr(raw: string): ParsedCidr | null {
	const slash = raw.indexOf('/');
	if (slash < 0 || raw.indexOf('/', slash + 1) >= 0) return null;
	const address = raw.slice(0, slash);
	const prefixText = raw.slice(slash + 1);
	if (!/^\d{1,3}$/.test(prefixText)) return null;
	const prefix = Number(prefixText);
	const ipv4 = address.includes(':') ? null : parseIpv4(address);
	const ipv6 = ipv4 === null && address.includes(':') ? parseIpv6(address) : null;
	const version: 4 | 6 | null = ipv4 !== null ? 4 : ipv6 !== null ? 6 : null;
	if (version === null || prefix > bitsOf(version)) return null;
	const bits = bitsOf(version);
	const value = (ipv4 ?? ipv6)!;
	const hostMask = (1n << BigInt(bits - prefix)) - 1n;
	// strict=False: host bits are dropped exactly as Waygate normalizes them.
	return { version, network: value & ~hostMask & ((1n << BigInt(bits)) - 1n), prefix };
}

function formatIpv6(value: bigint): string {
	const hextets = Array.from({ length: 8 }, (_, index) => Number((value >> BigInt(112 - index * 16)) & 0xffffn));
	let bestStart = -1;
	let bestLength = 0;
	for (let index = 0; index < 8; ) {
		if (hextets[index] !== 0) { index++; continue; }
		let end = index;
		while (end < 8 && hextets[end] === 0) end++;
		if (end - index > bestLength) { bestStart = index; bestLength = end - index; }
		index = end;
	}
	const text = hextets.map((hextet) => hextet.toString(16));
	if (bestLength < 2) return text.join(':');
	return `${text.slice(0, bestStart).join(':')}::${text.slice(bestStart + bestLength).join(':')}`;
}

function formatCidr(cidr: ParsedCidr): string {
	const address = cidr.version === 4
		? [24n, 16n, 8n, 0n].map((shift) => String((cidr.network >> shift) & 0xffn)).join('.')
		: formatIpv6(cidr.network);
	return `${address}/${cidr.prefix}`;
}

function overlaps(a: ParsedCidr, b: ParsedCidr): boolean {
	if (a.version !== b.version) return false;
	const prefix = Math.min(a.prefix, b.prefix);
	const shift = BigInt(bitsOf(a.version) - prefix);
	return a.network >> shift === b.network >> shift;
}

export type WaygateAllowedIpsResult = { ok: true; value: string[] } | { ok: false; error: string };

/**
 * Parses a comma/whitespace/newline separated CIDR list into Waygate's canonical
 * order-preserving, de-duplicated form. Empty input is a valid empty routing list.
 */
export function parseWaygateAllowedIps(raw: string, tunnelCidr?: string | null): WaygateAllowedIpsResult {
	const entries = raw.split(/[\s,]+/).filter(Boolean);
	const tunnel = tunnelCidr ? parseCidr(tunnelCidr) : null;
	const seen = new Set<string>();
	const value: string[] = [];
	for (const entry of entries) {
		const cidr = parseCidr(entry);
		if (!cidr) return { ok: false, error: t('validation.allowedIps.invalid', { value: entry }) };
		if (cidr.prefix === 0) return { ok: false, error: t('validation.allowedIps.defaultRoute', { value: entry }) };
		if (tunnel && overlaps(cidr, tunnel)) {
			return { ok: false, error: t('validation.allowedIps.tunnelOverlap', { value: entry, tunnel: tunnelCidr! }) };
		}
		const canonical = formatCidr(cidr);
		if (seen.has(canonical)) continue;
		seen.add(canonical);
		value.push(canonical);
	}
	if (value.length > WAYGATE_ALLOWED_IPS_MAX) {
		return { ok: false, error: t('validation.allowedIps.tooMany', { max: WAYGATE_ALLOWED_IPS_MAX }) };
	}
	return { ok: true, value };
}
