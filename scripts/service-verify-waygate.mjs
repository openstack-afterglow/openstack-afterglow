import { createDecipheriv, createPrivateKey, createPublicKey, randomBytes, randomUUID, scryptSync } from 'node:crypto';
import { isIP } from 'node:net';
import { check, required, withCleanup } from './service-verify-http.mjs';

// Public contracts: waygate/api/{clients,migration}.py, models/schemas.py,
// services/{config_render,migration,ipam}.py. No server/default/network writes.
// Exercise requires exclusive disposable servers: public APIs cannot lock a
// server for the whole smoke run. Recheck inventories before export/import.
// Runtime setup: owner supplies two existing, registered ACTIVE disposable
// servers, empty client inventories and genuine project-scoped Keystone auth.
// Source-owned test_waygate_clients.py/test_waygate_migration.py patterns are
// isolated synthetic test references only, not live auth/callback substitutes.
const boundary = 'no VM provisioning/callback/data-plane';
const clientFields = ['id', 'server_id', 'project_id', 'name', 'enabled', 'public_key', 'tunnel_ip',
	'allowed_ips', 'dns', 'mtu', 'persistent_keepalive', 'inherit_dns', 'inherit_persistent_keepalive', 'psk_enabled'];
const serverFields = ['id', 'project_id', 'status', 'server_public_key', 'endpoint_ip', 'listen_port',
	'tunnel_cidr', 'dns', 'persistent_keepalive'];
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const serverPath = (id) => `/v1/servers/${encodeURIComponent(id)}`;
const clientPath = (serverId, id) => `${serverPath(serverId)}/clients/${encodeURIComponent(id)}`;

function keyBytes(value) {
	check(typeof value === 'string', 'Waygate returned a missing WireGuard key.');
	const bytes = Buffer.from(value, 'base64');
	check(bytes.length === 32 && bytes.toString('base64') === value, 'Waygate returned an invalid WireGuard key.');
	return bytes;
}

function publicKey(privateKey) {
	const key = createPrivateKey({ format: 'der', type: 'pkcs8',
		key: Buffer.concat([Buffer.from('302e020100300506032b656e04220420', 'hex'), keyBytes(privateKey)]) });
	return createPublicKey(key).export({ format: 'der', type: 'spki' }).subarray(-32).toString('base64');
}

function ipNumber(value) {
	const version = isIP(value);
	check(version, 'Waygate returned an invalid tunnel address.');
	if (version === 4) return value.split('.').reduce((n, part) => (n << 8n) + BigInt(part), 0n);
	// IPv4-mapped IPv6 is valid to Python ipaddress too.
	if (value.includes('.')) {
		const split = value.lastIndexOf(':');
		const v4 = ipNumber(value.slice(split + 1));
		value = `${value.slice(0, split)}:${(v4 >> 16n).toString(16)}:${(v4 & 65535n).toString(16)}`;
	}
	const halves = value.split('::').map((part) => part ? part.split(':') : []);
	const parts = halves.length === 1 ? halves[0] : [...halves[0], ...Array(8 - halves[0].length - halves[1].length).fill('0'), ...halves[1]];
	return parts.reduce((n, part) => (n << 16n) + BigInt(`0x${part}`), 0n);
}

function firstClientIP(cidr) {
	check(typeof cidr === 'string', 'Waygate server has no tunnel CIDR.');
	const [address, prefix, extra] = cidr.split('/');
	const version = isIP(address);
	const bits = version === 4 ? 32 : 128;
	const length = Number(prefix);
	check(version && prefix !== undefined && /^\d+$/.test(prefix) && !extra && length >= 0 && length < bits,
		'Prerequisite: each disposable server needs a tunnel CIDR with room for a client; no writes performed.');
	const hostBits = BigInt(bits - length);
	const network = (ipNumber(address) >> hostBits) << hostBits;
	// Python ip_network.hosts(): /31 and /127 include both addresses;
	// otherwise reserve the first host for the gateway and issue the second.
	return network + (length === bits - 1 ? 1n : 2n);
}

function ready(server, id, project) {
	check(server?.id === id && typeof server.project_id === 'string' && server.project_id,
		'Prerequisite: designated server must be owned by the authenticated project; no writes performed.');
	if (project) check(server.project_id === project, 'Prerequisite: designated server project does not match the explicit scope; no writes performed.');
	check(server.status === 'ACTIVE' && server.server_public_key && server.endpoint_ip,
		'Prerequisite: both disposable servers must be ACTIVE with registered public keys and endpoints; no writes performed.');
	keyBytes(server.server_public_key);
	check(Number.isInteger(server.listen_port) && server.listen_port > 0 && server.listen_port <= 65535,
		'Prerequisite: disposable server has an invalid WireGuard listen port; no writes performed.');
	check((server.dns === null || typeof server.dns === 'string') && Number.isInteger(server.persistent_keepalive)
		&& server.persistent_keepalive >= 0 && server.persistent_keepalive <= 65535,
		'Waygate server did not expose effective DNS/keepalive defaults.');
	firstClientIP(server.tunnel_cidr);
}

async function listClients(client, serverId) {
	const rows = await client.request(`${serverPath(serverId)}/clients`);
	check(Array.isArray(rows), 'Waygate clients response must be a native array.');
	check(rows.every((row) => row && typeof row.id === 'string' && row.id && row.server_id === serverId),
		'Waygate client inventory has invalid identities.');
	check(new Set(rows.map((row) => row.id)).size === rows.length, 'Waygate client inventory contains duplicate IDs.');
	return rows;
}

async function networks(client, serverId) {
	const rows = await client.request(`${serverPath(serverId)}/networks`);
	check(Array.isArray(rows), 'Waygate network attachments response must be a native array.');
	return rows;
}

function assertFields(actual, expected, fields, message) {
	check(actual && fields.every((field) => same(actual[field], expected[field])), message);
}

function parseConfig(text) {
	check(typeof text === 'string', 'Waygate config download must be plaintext.');
	const sections = {};
	let current;
	for (const raw of text.split(/\r?\n/)) {
		const line = raw.trim();
		if (!line) continue;
		const section = /^\[(Interface|Peer)\]$/.exec(line);
		if (section) {
			check(!sections[section[1]], 'Waygate config contains duplicate sections.');
			current = sections[section[1]] = {};
			continue;
		}
		const field = /^([A-Za-z]+)\s*=\s*(.*)$/.exec(line);
		check(current && field && !Object.hasOwn(current, field[1]), 'Waygate config contains an invalid or duplicate directive.');
		current[field[1]] = field[2];
	}
	check(sections.Interface && sections.Peer, 'Waygate config lacks Interface/Peer sections.');
	return sections;
}

function verifyConfig(text, row, server, attachments, identity) {
	const { Interface: iface, Peer: peer } = parseConfig(text);
	keyBytes(iface.PrivateKey);
	keyBytes(peer.PresharedKey);
	check(publicKey(iface.PrivateKey) === row.public_key && row.psk_enabled === true,
		'Waygate config key does not match the persisted client identity or generated PSK presence.');
	const allowed = [...new Set([...row.allowed_ips, ...attachments.filter((a) => a.status === 'ACTIVE').map((a) => a.cidr)].filter(Boolean))];
	assertFields(iface, { PrivateKey: iface.PrivateKey, Address: `${row.tunnel_ip}/32`,
		DNS: row.dns || undefined, MTU: row.mtu === null ? undefined : String(row.mtu) },
		['Address', 'DNS', 'MTU'], 'Waygate config address/effective DNS/MTU mismatch.');
	assertFields(peer, { PublicKey: server.server_public_key, Endpoint: `${server.endpoint_ip}:${server.listen_port}`,
		AllowedIPs: allowed.join(', '), PersistentKeepalive: String(row.persistent_keepalive) },
		['PublicKey', 'Endpoint', 'AllowedIPs', 'PersistentKeepalive'], 'Waygate config server key/endpoint/routes/keepalive mismatch.');
	if (identity) check(iface.PrivateKey === identity.privateKey && peer.PresharedKey === identity.psk,
		'Waygate PATCH/import changed the client private key or PSK.');
	return { privateKey: iface.PrivateKey, psk: peer.PresharedKey };
}

function unwrap(blob, passphrase) {
	// Exact wgm1 wire format: scrypt(N=16384,r=8,p=1), salt16, nonce12,
	// AES-256-GCM ciphertext followed by tag16. Only held in memory.
	try {
		check(typeof blob === 'string' && blob.startsWith('wgm1:'), 'Invalid wrapped key.');
		const payload = Buffer.from(blob.slice(5), 'base64');
		check(payload.length > 44 && payload.toString('base64') === blob.slice(5), 'Invalid wrapped key.');
		const key = scryptSync(passphrase, payload.subarray(0, 16), 32, { N: 16384, r: 8, p: 1 });
		const decipher = createDecipheriv('aes-256-gcm', key, payload.subarray(16, 28));
		decipher.setAuthTag(payload.subarray(-16));
		return Buffer.concat([decipher.update(payload.subarray(28, -16)), decipher.final()]).toString('utf8');
	} catch {
		throw new Error('Waygate export key is not a valid passphrase-encrypted wgm1 payload.');
	}
}

export async function verifyWaygate(client, { env, exercise }) {
	const servers = await client.request('/v1/servers');
	check(Array.isArray(servers), 'Waygate servers response must be a native array.');
	if (!exercise) return [`authenticated server inventory; connection-only (${boundary})`];
	const sourceId = required(env, 'WAYGATE_SMOKE_SERVER_ID');
	// Migration imports into an existing server; importing back into source
	// would conflict with its issued client, so a distinct target is mandatory.
	const targetId = required(env, 'WAYGATE_SMOKE_IMPORT_SERVER_ID');
	check(sourceId !== targetId, 'Prerequisite: WAYGATE_SMOKE_IMPORT_SERVER_ID must designate a distinct owned ready empty disposable server; no writes performed.');
	check([sourceId, targetId].every((id) => servers.filter((row) => row?.id === id).length === 1),
		'Prerequisite: both explicitly designated disposable servers must appear in the authenticated inventory; no writes performed.');
	const source = await client.request(serverPath(sourceId));
	const target = await client.request(serverPath(targetId));
	const project = env.WAYGATE_SMOKE_PROJECT_ID?.trim();
	ready(source, sourceId, project);
	ready(target, targetId, source.project_id);
	check((await listClients(client, sourceId)).length === 0 && (await listClients(client, targetId)).length === 0,
		'Prerequisite: source and import target must have no pre-existing clients (including disabled clients); no writes performed.');
	const sourceNetworks = await networks(client, sourceId);
	const targetNetworks = await networks(client, targetId);
	const name = `waygate-smoke-${randomUUID()}`;
	const editedName = `${name}-edit`;
	const sourceCreated = new Set();
	const targetCreated = new Set();
	let issuing = false;
	let importing = false;
	let identity;
	let created;
	const download = (sid, cid) => client.request(`${clientPath(sid, cid)}/config`, { format: 'text' });
	const persisted = async (sid, expected) => {
		const rows = await listClients(client, sid);
		check(rows.length === 1 && rows[0].id === expected.id, 'Waygate disposable inventory contains unexpected clients.');
		assertFields(rows[0], expected, clientFields, 'Waygate persisted client does not reconcile with the mutation response.');
		return rows[0];
	};
	const discover = async () => {
		// POST may commit before a timeout/invalid response. Never delete a
		// foreign row: recover only this run's unique name and owned identity.
		if (issuing && sourceCreated.size === 0) {
			for (const row of await listClients(client, sourceId)) {
				if ([name, editedName].includes(row.name) && row.project_id === source.project_id) sourceCreated.add(row.id);
			}
		}
		if (importing && created) {
			for (const row of await listClients(client, targetId)) {
				if (row.name === editedName && row.public_key === created.public_key && row.project_id === target.project_id) targetCreated.add(row.id);
			}
		}
	};
	return withCleanup(async () => {
		issuing = true;
		created = await client.request(`${serverPath(sourceId)}/clients`, {
			method: 'POST', expected: [201], json: { name, mtu: 1380 }
		});
		if (typeof created?.id === 'string' && created.id) sourceCreated.add(created.id);
		check(sourceCreated.size === 1, 'Waygate client issuance did not return a created client ID.');
		assertFields(created, { name, server_id: sourceId, project_id: source.project_id, enabled: true,
			dns: source.dns, mtu: 1380, persistent_keepalive: source.persistent_keepalive,
			inherit_dns: true, inherit_persistent_keepalive: true, psk_enabled: true, allowed_ips: [source.tunnel_cidr] },
			['name', 'server_id', 'project_id', 'enabled', 'dns', 'mtu', 'persistent_keepalive', 'inherit_dns', 'inherit_persistent_keepalive', 'psk_enabled', 'allowed_ips'],
			'Waygate issuance did not apply server inheritance, per-client MTU and generated PSK.');
		check(ipNumber(created.tunnel_ip) === firstClientIP(source.tunnel_cidr), 'Waygate issuance did not allocate the first free client tunnel address.');
		await persisted(sourceId, created);
		identity = verifyConfig(created.tunnel_conf, created, source, sourceNetworks);
		verifyConfig(await download(sourceId, created.id), created, source, sourceNetworks, identity);
		const patch = { name: editedName, enabled: false, dns: source.dns === '1.1.1.1, 8.8.8.8' ? '9.9.9.9, 149.112.112.112' : '1.1.1.1, 8.8.8.8',
			mtu: 1420, persistent_keepalive: source.persistent_keepalive === 0 ? 1 : 0 };
		const updated = await client.request(clientPath(sourceId, created.id), { method: 'PATCH', json: patch });
		const expected = { ...created, ...patch, inherit_dns: false, inherit_persistent_keepalive: false };
		assertFields(updated, expected, clientFields, 'Waygate PATCH did not preserve identity and persist meaningful client overrides.');
		await persisted(sourceId, updated);
		verifyConfig(await download(sourceId, created.id), updated, source, sourceNetworks, identity);
		// Export is server-wide: do not export a newly arrived foreign client.
		await persisted(sourceId, updated);
		check((await listClients(client, targetId)).length === 0, 'Import prerequisite changed: target is no longer empty; import refused.');
		const passphrase = randomBytes(32).toString('base64url');
		const response = await client.request(`${serverPath(sourceId)}/export`, { method: 'POST', json: { passphrase }, format: 'response' });
		check(response.headers.get('cache-control') === 'no-store', 'Waygate export must be marked no-store.');
		let bundle;
		try { bundle = await response.json(); } catch { throw new Error('Waygate export returned invalid JSON.'); }
		check(bundle?.version === 1 && Array.isArray(bundle.clients) && bundle.clients.length === 1,
			'Waygate export omitted the created client or included foreign clients; import refused.');
		const entry = bundle.clients[0];
		assertFields(entry, updated, ['name', 'enabled', 'public_key', 'tunnel_ip', 'allowed_ips', 'dns', 'mtu', 'persistent_keepalive'],
			'Waygate export did not preserve the created client identity and effective custom settings; import refused.');
		check(unwrap(entry.private_key_wrapped, passphrase) === identity.privateKey && unwrap(entry.preshared_key_wrapped, passphrase) === identity.psk,
			'Waygate encrypted export did not preserve private key/PSK; import refused.');
		const serialized = JSON.stringify(bundle);
		check(![identity.privateKey, identity.psk, passphrase].some((secret) => serialized.includes(secret)),
			'Waygate export leaked plaintext secret material; import refused.');
		check(Array.isArray(bundle.network_attachments), 'Waygate export lacks network attachment metadata.');
		// No attachment is recreated by import; config uses target attachments.
		assertFields(await client.request(serverPath(targetId)), target, serverFields, 'Import prerequisite changed: target readiness/defaults changed; import refused.');
		check((await listClients(client, targetId)).length === 0, 'Import prerequisite changed: target is no longer empty; import refused.');
		importing = true;
		const result = await client.request(`${serverPath(targetId)}/import`, { method: 'POST', json: { passphrase, bundle } });
		await discover();
		check(result?.imported === 1 && Array.isArray(result.skipped) && result.skipped.length === 0,
			'Waygate import must import exactly one client with no skipped entries.');
		check(targetCreated.size === 1, 'Waygate import did not expose exactly one run-owned persisted client.');
		const rows = await listClients(client, targetId);
		const imported = rows.find((row) => targetCreated.has(row.id));
		check(imported && imported.id !== created.id && rows.length === 1, 'Waygate import inventory has an invalid or foreign client identity.');
		assertFields(imported, { ...updated, server_id: targetId, project_id: target.project_id },
			clientFields.filter((field) => !['id', 'tunnel_ip'].includes(field)), 'Waygate imported client did not preserve cryptographic identity and explicit custom settings.');
		check(ipNumber(imported.tunnel_ip) === firstClientIP(target.tunnel_cidr), 'Waygate import did not reallocate the target tunnel address.');
		verifyConfig(await download(targetId, imported.id), imported, target, targetNetworks, identity);
		return ['owned ready empty source/target preflight → client issued (201) → persisted list/plaintext download/key/address/endpoint/effective DNS/MTU/keepalive/PSK verified',
			'meaningful PATCH (200) → persisted overrides/config/unchanged keys verified → passphrase-encrypted export (200, no-store) → import (200, 1 imported, 0 skipped) → target config/identity/custom settings verified',
			`run-created clients deleted (204), absent from lists and config returns 404; server defaults/attachments unchanged; ${boundary}`];
	}, async () => {
		const failures = [];
		try { await discover(); } catch (error) { failures.push(error.message); }
		for (const [sid, ids] of [[targetId, targetCreated], [sourceId, sourceCreated]]) {
			for (const id of ids) {
				try {
					await client.request(clientPath(sid, id), { method: 'DELETE', expected: [204], format: 'empty' });
					check(!(await listClients(client, sid)).some((row) => row.id === id), 'Deleted Waygate client remains in inventory.');
					await client.request(`${clientPath(sid, id)}/config`, { expected: [404], format: 'empty' });
				} catch (error) { failures.push(error.message); }
			}
		}
		for (const [server, attachments] of [[source, sourceNetworks], [target, targetNetworks]]) {
			try {
				assertFields(await client.request(serverPath(server.id)), server, serverFields, 'Waygate server readiness/defaults changed during verification.');
				check(same(await networks(client, server.id), attachments), 'Waygate network attachments changed during verification.');
			} catch (error) { failures.push(error.message); }
		}
		check(failures.length === 0, failures.join('; '));
	});
}
