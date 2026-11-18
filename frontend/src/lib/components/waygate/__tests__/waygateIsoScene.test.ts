import { describe, expect, it } from 'vitest';
import { t } from '$lib/i18n/ns/waygate';
import { getStatusLabel } from '$lib/config/statusColors';
import type { WaygateClient, WaygateNetworkAttachment, WaygateServer } from '$lib/types/waygate';
import { buildWaygateIsoScene } from '../waygateIsoScene';

const report = '2026-11-18T11:00:00Z';
const server: WaygateServer = {
	id: 'gw', project_id: 'p', name: 'VPN Gateway', status: 'ACTIVE', status_reason: null,
	server_vm_id: 'vm', endpoint_ip: '2001:db8::10', listen_port: 51820, tunnel_cidr: '10.70.0.0/24',
	dns: null, persistent_keepalive: 25, server_public_key: null, created_at: null, updated_at: null,
	last_status_reported_at: report, peer_count: 0,
};
const client = (id: string, overrides: Partial<WaygateClient> = {}): WaygateClient => ({
	id, server_id: server.id, project_id: 'p', name: id, enabled: true, public_key: 'public-key', tunnel_ip: '10.70.0.12',
	allowed_ips: ['10.70.0.0/24'], dns: null, mtu: null, persistent_keepalive: 25, psk_enabled: false,
	created_at: null, updated_at: null, online: true, last_handshake_at: report, last_reported_at: report,
	rx_bytes: null, tx_bytes: null, ...overrides,
});
const attachment = (id: number, network_id: string, nat_mode: string): WaygateNetworkAttachment => ({
	id, network_id, nat_mode, server_id: server.id, project_id: 'p', subnet_id: null, port_id: null,
	cidr: '192.0.2.0/24', status: 'ACTIVE', created_at: null, updated_at: null,
});
const input = { server, clients: [], attachments: [], networks: [], now: Date.parse(report) + 2000, pollSeconds: 5, locale: 'en-US' };

describe('buildWaygateIsoScene', () => {
	it('distinguishes online, offline, disabled, unreported, and stale peers', () => {
		const clients = [client('online'), client('offline', { online: false }), client('disabled', { enabled: false }),
			client('unknown', { last_reported_at: null, last_handshake_at: null, online: null }),
			client('stale', { last_reported_at: '2026-11-18T10:59:00Z' }),
			client('no-handshake', { last_handshake_at: null })];
		const { scene, targets } = buildWaygateIsoScene({ ...input, clients });
		const peer = (id: string) => scene.nodes.find(node => node.id === `peer:${id}`);
		const edge = (id: string) => scene.edges.find(edge => edge.from === `peer:${id}`);
		expect(peer('online')).toMatchObject({ status: 'ok', ariaLabel: expect.stringContaining(t('project.client.lastHandshake')), badges: [
			{ text: t('project.status.online') }, { text: new Date(report).toLocaleString(input.locale, { dateStyle: 'short', timeStyle: 'short' }) },
		] });
		expect(edge('online')).toMatchObject({ kind: 'tunnel', inactive: false, bidirectional: true, to: 'server:gw' });
		expect(peer('offline')).toMatchObject({ status: undefined, badges: [{ text: t('project.status.offline') }, expect.anything()] });
		expect(peer('disabled')).toMatchObject({ status: undefined, badges: [{ text: t('project.status.disabled') }, expect.anything()] });
		expect(peer('stale')?.status).toBe('warning');
		expect(peer('unknown')).toMatchObject({ status: 'unknown', badges: [{ text: t('project.status.unknown') }] });
		expect(peer('no-handshake')?.badges).toHaveLength(1);
		for (const id of ['offline', 'disabled', 'unknown', 'stale', 'no-handshake']) expect(edge(id)).toMatchObject({ inactive: true });
		expect(targets.get('peer:online')).toEqual({ kind: 'peer', id: 'online' });
	});

	it('shows endpoint, tunnel CIDR, observed peer count, and only attached networks with their NAT modes', () => {
		const networks = [
			{ id: 'private', name: 'tenant', is_shared: false, is_external: false },
			{ id: 'other', name: 'unattached', is_shared: false, is_external: false },
		];
		const attachments = [attachment(7, 'private', 'snat'), { ...attachment(12, 'catalog-missing', 'none'), cidr: null },
			{ ...attachment(13, 'other', 'snat'), server_id: 'not-this-gateway' }];
		const { scene, targets } = buildWaygateIsoScene({ ...input, networks, attachments });
		expect(scene.nodes[0]).toMatchObject({ kind: 'vpn-server', sublabel: '[2001:db8::10]:51820', status: 'ok',
			badges: [expect.anything(), { text: t('project.iso.reportedPeers', { count: 0 }) }] });
		expect(scene.platforms).toEqual([
			expect.objectContaining({ id: 'tunnel', sublabel: '10.70.0.0/24' }),
			expect.objectContaining({ id: 'attachment:7', label: 'tenant', sublabel: '192.0.2.0/24' }),
			expect.objectContaining({ id: 'attachment:12', label: 'catalog-missing', sublabel: undefined }),
		]);
		expect(scene.edges.map(edge => edge.label)).toEqual(['snat', 'none']);
		expect(targets.get('attachment:12')).toEqual({ kind: 'attachment', id: 12 });
	});

	it.each(['CREATING', 'ERROR', 'DELETING'])('shows reported %s attachment status as text', (status) => {
		const { scene } = buildWaygateIsoScene({ ...input, attachments: [{ ...attachment(7, 'private', 'snat'), status }] });
		expect(scene.platforms.find(platform => platform.id === 'attachment:7')?.sublabel).toBe(`192.0.2.0/24 · ${getStatusLabel(status)}`);
		expect(scene.edges[0]).toMatchObject({ label: 'snat', inactive: true });
	});

	it('collapses many peers by profile count, not the server-reported count', () => {
		const clients = Array.from({ length: 8 }, (_, i) => client(`client-${i}`, { online: false }));
		const { scene, targets } = buildWaygateIsoScene({ ...input, clients });
		expect(scene.nodes).toHaveLength(2);
		expect(scene.nodes[1]).toMatchObject({ kind: 'peer-group', label: t('project.iso.profileCount', { count: 8 }) });
		expect(scene.nodes[1].status).toBeUndefined();
		expect(scene.edges).toEqual([expect.objectContaining({ kind: 'tunnel', inactive: true })]);
		expect(targets.get('peer-group')).toEqual({ kind: 'peers' });
	});

	it.each([['BUILD', 'pending'], ['ERROR', 'error'], ['UNRECOGNIZED', 'unknown']])('maps %s without fabricating an endpoint or peer count', (status, mark) => {
		const { scene } = buildWaygateIsoScene({ ...input, server: { ...server, status, endpoint_ip: null, peer_count: null } });
		expect(scene.nodes[0]).toMatchObject({ status: mark, sublabel: undefined });
		expect(scene.nodes[0].badges).toHaveLength(1);
		expect(scene.edges).toHaveLength(0);
	});
});
