import { describe, expect, it } from 'vitest';
import type { WaygateClient } from '$lib/types/waygate';
import {
	emptyWaygateClientDraft,
	waygateClientCreateBody,
	waygateClientDraft,
	waygateClientUpdateBody,
} from '../waygateClientSettings';

const client = {
	name: 'laptop',
	dns: '1.1.1.1',
	mtu: 1380,
	persistent_keepalive: 0,
	psk_enabled: false,
} as WaygateClient;

describe('Waygate client settings', () => {
	it('issues with the default keepalive and automatic DNS/MTU', () => {
		expect(waygateClientCreateBody({ ...emptyWaygateClientDraft(), name: 'phone' })).toEqual({
			ok: true,
			body: { name: 'phone', dns: null, mtu: null, persistent_keepalive: 25 },
		});
	});

	it('retains disabled keepalive and sends blank DNS/MTU as explicit clears', () => {
		const draft = waygateClientDraft(client);
		expect(draft.persistentKeepalive).toBe('0');
		expect(waygateClientUpdateBody(client, { ...draft, dns: ' ', mtu: '' })).toEqual({
			ok: true,
			body: { dns: null, mtu: null, persistent_keepalive: 0 },
		});
	});

	it('normalizes two DNS servers and renames only when changed', () => {
		expect(waygateClientUpdateBody(client, { ...waygateClientDraft(client), name: 'desk', dns: '1.1.1.1,2606:4700:4700::1111' })).toEqual({
			ok: true,
			body: { name: 'desk', dns: '1.1.1.1, 2606:4700:4700::1111', mtu: 1380, persistent_keepalive: 0 },
		});
	});

	it.each([
		['mtu', '575'],
		['mtu', '9001'],
		['mtu', '1400.5'],
		['persistentKeepalive', ''],
		['persistentKeepalive', '65536'],
		['dns', '1.1.1.1, 8.8.8.8, 9.9.9.9'],
		['dns', '1.1.1.1;reboot'],
		['name', '-bad'],
	] as const)('rejects invalid %s value %s before sending', (field, value) => {
		const result = waygateClientCreateBody({ ...emptyWaygateClientDraft(), name: 'ok', [field]: value });
		expect(result.ok).toBe(false);
		if (!result.ok) expect(Object.keys(result.errors)).toEqual([field]);
	});

	it('accepts boundary MTU and keepalive values', () => {
		expect(waygateClientCreateBody({ name: 'a', dns: '', mtu: '576', persistentKeepalive: '65535' }).ok).toBe(true);
		expect(waygateClientCreateBody({ name: 'a', dns: '', mtu: '9000', persistentKeepalive: '0' }).ok).toBe(true);
	});
});
