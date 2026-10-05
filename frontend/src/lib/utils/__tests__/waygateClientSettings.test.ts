import { describe, expect, it } from 'vitest';
import type { WaygateClient, WaygateServer } from '$lib/types/waygate';
import {
	emptyWaygateClientDraft,
	waygateClientCreateBody,
	waygateClientDraft,
	waygateClientUpdateBody,
	waygateServerCreateBody,
	waygateServerDraft,
	waygateServerUpdateBody,
} from '../waygateClientSettings';

const legacyClient = {
	name: 'laptop',
	dns: '1.1.1.1',
	mtu: 1380,
	persistent_keepalive: 0,
	psk_enabled: false,
} as WaygateClient;

const server: WaygateServer = {
	id: 'server-a', project_id: 'project-a', name: 'office', status: 'ACTIVE', status_reason: null,
	server_vm_id: 'vm-a', endpoint_ip: '203.0.113.5', listen_port: 51820, tunnel_cidr: '10.44.0.0/24',
	dns: '1.1.1.1, 8.8.8.8', persistent_keepalive: 0, server_public_key: 'public-key',
	created_at: null, updated_at: null, last_status_reported_at: null, peer_count: null,
};

describe('Waygate client settings', () => {
	it('creates clients without unsupported inheritance fields while retaining overrides', () => {
		expect(waygateClientCreateBody({ ...emptyWaygateClientDraft(), name: 'pieroot-macbook' })).toEqual({
			ok: true,
			body: { name: 'pieroot-macbook', mtu: null },
		});
		expect(waygateClientCreateBody({ ...emptyWaygateClientDraft(), name: 'pieroot-macbook', inheritDns: false, inheritPersistentKeepalive: false, dns: '1.1.1.1', persistentKeepalive: '0' })).toEqual({
			ok: true,
			body: { name: 'pieroot-macbook', dns: '1.1.1.1', persistent_keepalive: 0, mtu: null },
		});
	});


	it('switches DNS and keepalive inheritance independently without comparing server defaults', () => {
		const draft = { ...emptyWaygateClientDraft(), name: 'phone', dns: server.dns ?? '', persistentKeepalive: '0' };
		draft.inheritDns = false;
		expect(waygateClientCreateBody(draft)).toEqual({
			ok: true,
			body: { name: 'phone', dns: server.dns, mtu: null },
		});
		draft.inheritPersistentKeepalive = false;
		draft.dns = ' ';
		expect(waygateClientCreateBody(draft)).toEqual({
			ok: true,
			body: { name: 'phone', dns: null, persistent_keepalive: 0, mtu: null },
		});
		draft.inheritDns = true;
		expect(waygateClientCreateBody(draft)).toEqual({
			ok: true,
			body: { name: 'phone', persistent_keepalive: 0, mtu: null },
		});
	});

	it('creates servers with optional blank names and only DNS and keepalive defaults', () => {
		expect(waygateServerCreateBody({ ...waygateServerDraft(), name: ' ', mtu: 'invalid' })).toEqual({
			ok: true,
			body: { name: '', dns: null, persistent_keepalive: 25 },
		});
		expect(waygateServerCreateBody({ ...waygateServerDraft(server), name: 'office', dns: '1.1.1.1,8.8.8.8' })).toEqual({
			ok: true,
			body: { name: 'office', dns: '1.1.1.1, 8.8.8.8', persistent_keepalive: 0 },
		});
	});

	it('updates server defaults without name or MTU, including explicit DNS clearing and zero keepalive', () => {
		expect(waygateServerUpdateBody({ ...waygateServerDraft(server), name: '-ignored', dns: '', mtu: '575' })).toEqual({
			ok: true,
			body: { dns: null, persistent_keepalive: 0 },
		});
	});

	it('validates server create names and both server defaults but never server MTU', () => {
		const draft = { ...waygateServerDraft(), name: '-bad', dns: '1.1.1.1;reboot', mtu: '575', persistentKeepalive: '65536' };
		const create = waygateServerCreateBody(draft);
		const update = waygateServerUpdateBody(draft);
		expect(create.ok).toBe(false);
		if (!create.ok) expect(Object.keys(create.errors).sort()).toEqual(['dns', 'name', 'persistentKeepalive']);
		expect(update.ok).toBe(false);
		if (!update.ok) expect(Object.keys(update.errors).sort()).toEqual(['dns', 'persistentKeepalive']);
	});

	it('edits legacy clients with custom values and explicit MTU clearing', () => {
		const draft = waygateClientDraft(legacyClient);
		expect(waygateClientUpdateBody(legacyClient, { ...draft, dns: ' ', mtu: '' })).toEqual({
			ok: true,
			body: { inherit_dns: false, inherit_persistent_keepalive: false, dns: null, persistent_keepalive: 0, mtu: null },
		});
		expect(waygateClientUpdateBody(legacyClient, { ...draft, name: 'desk', dns: '1.1.1.1,2606:4700:4700::1111' })).toEqual({
			ok: true,
			body: { name: 'desk', inherit_dns: false, inherit_persistent_keepalive: false, dns: '1.1.1.1, 2606:4700:4700::1111', persistent_keepalive: 0, mtu: 1380 },
		});
	});

	it('edits inherited clients without sending their cached effective DNS or keepalive', () => {
		const inherited = { ...legacyClient, inherit_dns: true, inherit_persistent_keepalive: true };
		const draft = waygateClientDraft(inherited);
		expect(waygateClientUpdateBody(inherited, { ...draft, dns: 'bad;dns', persistentKeepalive: 'bad' })).toEqual({
			ok: true,
			body: { inherit_dns: true, inherit_persistent_keepalive: true, mtu: 1380 },
		});
		expect(waygateClientUpdateBody(inherited, { ...draft, inheritDns: false, inheritPersistentKeepalive: false })).toEqual({
			ok: true,
			body: { inherit_dns: false, inherit_persistent_keepalive: false, dns: '1.1.1.1', persistent_keepalive: 0, mtu: 1380 },
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
	] as const)('rejects invalid custom %s value %s', (field, value) => {
		const result = waygateClientCreateBody({ ...emptyWaygateClientDraft(), name: 'ok', inheritDns: false, inheritPersistentKeepalive: false, [field]: value });
		expect(result.ok).toBe(false);
		if (!result.ok) expect(Object.keys(result.errors)).toEqual([field]);
	});

	it('accepts MTU and custom keepalive boundaries', () => {
		for (const [mtu, keepalive] of [['576', '65535'], ['9000', '0']]) {
			expect(waygateClientCreateBody({ ...emptyWaygateClientDraft(), name: 'a', mtu, inheritPersistentKeepalive: false, persistentKeepalive: keepalive })).toEqual({
				ok: true,
				body: { name: 'a', persistent_keepalive: Number(keepalive), mtu: Number(mtu) },
			});
		}
	});
});
