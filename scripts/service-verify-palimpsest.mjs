import { createHash, randomUUID } from 'node:crypto';
import { open } from 'node:fs/promises';
import { check, required, withCleanup } from './service-verify-http.mjs';

// Public Hub only; never creates VMs or OpenStack image exports.
// --exercise requires a caller-provided real .sqsh and project-scoped Keystone
// credentials whose user has a system-admin assignment. Optional bundle scope:
// PALIMPSEST_SMOKE_BUNDLE=1 (unset/0 skips it). No payloads or credentials are logged.
// Contract: ../palimpsest/hub/src/palimpsest_hub/api/hub.py:1011-1374,1648-1672
// Digest invariant: docs/palimpsest.md:39-74 (root chain_id = byte digest).
const CHUNK = 1024 * 1024;
const MAX_JSON = 4 * CHUNK;
const SQUASHFS = 'application/vnd.afterglow.palimpsest.layer.squashfs.v1';
const CONFIG = 'application/vnd.afterglow.palimpsest.layer.config.v1+json';
const MANIFEST = 'application/vnd.oci.image.manifest.v1+json';
const INDEX = 'application/vnd.oci.image.index.v1+json';
const DIGEST = /^sha256:[0-9a-f]{64}$/;
const ANNOTATION = 'dev.afterglow.palimpsest.';
const sources = {
	upload: '../palimpsest/hub/src/palimpsest_hub/api/hub.py#L1155-L1362',
	admin: '../palimpsest/hub/src/palimpsest_hub/auth.py#L57-L123',
	cleanup: '../palimpsest/hub/src/palimpsest_hub/api/hub.py#L1648-L1672',
	gc: '../palimpsest/hub/src/palimpsest_hub/services/image_exports.py#L1268-L1343',
	bundle: '../palimpsest/hub/src/palimpsest_hub/services/hub_bundle.py#L169-L274',
	digest: 'docs/palimpsest.md#L39-L74'
};

function sha256(bytes) { return `sha256:${createHash('sha256').update(bytes).digest('hex')}`; }
function canonical(value) {
	return JSON.stringify(Object.fromEntries(Object.keys(value).sort().map((key) => [key, value[key]])));
}
async function jsonResponse(response, label) {
	try { return await response.json(); } catch { throw new Error(`${label} returned invalid JSON.`); }
}
function parseJson(bytes) {
	try { return JSON.parse(bytes.toString('utf8')); } catch { throw new Error('Bundle metadata is not valid JSON.'); }
}
async function readFileChunk(file, position, size) {
	const bytes = Buffer.allocUnsafe(size);
	let offset = 0;
	while (offset < size) {
		let result;
		try { result = await file.read(bytes, offset, size - offset, position + offset); }
		catch { throw new Error('Could not read PALIMPSEST_SMOKE_BLOB.'); }
		check(result.bytesRead > 0, 'PALIMPSEST_SMOKE_BLOB changed or was truncated during verification.');
		offset += result.bytesRead;
	}
	return bytes;
}
async function fileStat(file) {
	try { return await file.stat(); } catch { throw new Error('Could not inspect PALIMPSEST_SMOKE_BLOB.'); }
}
function sameFile(before, after) {
	check(before.size === after.size && before.mtimeMs === after.mtimeMs && before.ctimeMs === after.ctimeMs,
		'PALIMPSEST_SMOKE_BLOB changed during verification.');
}

async function compareDownload(response, file, size, digest) {
	check(response.body, 'Hub returned no blob body.');
	const hash = createHash('sha256');
	let offset = 0;
	for await (const bytes of response.body) {
		check(offset + bytes.length <= size, 'Downloaded blob exceeds the supplied file size.');
		check(Buffer.from(bytes).equals(await readFileChunk(file, offset, bytes.length)), 'Downloaded blob bytes differ from the supplied file.');
		hash.update(bytes);
		offset += bytes.length;
	}
	check(offset === size && `sha256:${hash.digest('hex')}` === digest, 'Downloaded blob size/digest does not match the supplied file.');
}

// Bounded streaming parser for the service's plain OCI tar, not an extractor.
// Python TarInfo uses local PAX size records when a blob exceeds the octal field.
// Reject links, duplicate members, unexpected paths and damaged/truncated headers.
function tarReader(body) {
	check(body, 'Hub returned no bundle body.');
	const iterator = body[Symbol.asyncIterator]();
	let pending = Buffer.alloc(0);
	let cursor = 0;
	return {
		async read(size) {
			const result = Buffer.allocUnsafe(size);
			let offset = 0;
			while (offset < size) {
				if (cursor === pending.length) {
					const next = await iterator.next();
					check(!next.done, 'Hub bundle is truncated.');
					pending = Buffer.from(next.value);
					cursor = 0;
				}
				const count = Math.min(size - offset, pending.length - cursor);
				pending.copy(result, offset, cursor, cursor + count);
				cursor += count;
				offset += count;
			}
			return result;
		},
		async finish() {
			check(pending.subarray(cursor).every((byte) => byte === 0), 'Bundle has trailing nonzero bytes.');
			for (;;) {
				const next = await iterator.next();
				if (next.done) return;
				check(Buffer.from(next.value).every((byte) => byte === 0), 'Bundle has trailing nonzero bytes.');
			}
		}
	};
}
function tarText(bytes) { return bytes.toString('ascii').split('\0')[0]; }
function tarOctal(bytes) {
	const text = tarText(bytes).trim();
	check(/^[0-7]+$/.test(text), 'Bundle has an invalid tar number.');
	const value = Number.parseInt(text, 8);
	check(Number.isSafeInteger(value) && value >= 0, 'Bundle tar number exceeds safe integer range.');
	return value;
}
function paxFields(bytes) {
	const fields = {};
	let offset = 0;
	while (offset < bytes.length) {
		const space = bytes.indexOf(32, offset);
		check(space > offset, 'Bundle has an invalid PAX record.');
		const lengthText = bytes.subarray(offset, space).toString('ascii');
		check(/^[1-9][0-9]*$/.test(lengthText), 'Bundle has an invalid PAX length.');
		const length = Number(lengthText);
		check(Number.isSafeInteger(length) && length > space - offset + 2 && offset + length <= bytes.length && bytes[offset + length - 1] === 10,
			'Bundle has a truncated PAX record.');
		const record = bytes.subarray(space + 1, offset + length - 1).toString('utf8');
		const equals = record.indexOf('=');
		check(equals > 0, 'Bundle has an invalid PAX field.');
		const key = record.slice(0, equals);
		check(!Object.hasOwn(fields, key) && ['size', 'path'].includes(key), 'Bundle has an unexpected PAX field.');
		fields[key] = record.slice(equals + 1);
		offset += length;
	}
	return fields;
}

async function verifyBundle(response, file, size, digest, name, configDigest, config) {
	const reader = tarReader(response.body);
	const members = new Map();
	let pax;
	let terminated = false;
	for (let count = 0; count < 64; count++) {
		const header = await reader.read(512);
		if (header.every((byte) => byte === 0)) {
			check(!pax && (await reader.read(512)).every((byte) => byte === 0), 'Bundle has an invalid tar terminator.');
			await reader.finish();
			terminated = true;
			break;
		}
		check(header.subarray(257, 262).toString('ascii') === 'ustar', 'Bundle is not the Hub plain OCI tar format.');
		let checksum = 0;
		for (let index = 0; index < 512; index++) checksum += index >= 148 && index < 156 ? 32 : header[index];
		check(tarOctal(header.subarray(148, 156)) === checksum, 'Bundle tar header checksum differs.');
		const type = header[156];
		let memberSize = tarOctal(header.subarray(124, 136));
		let memberName = tarText(header.subarray(0, 100));
		const prefix = tarText(header.subarray(345, 500));
		if (prefix) memberName = `${prefix}/${memberName}`;
		if (type === 120) {
			check(!pax && memberSize <= MAX_JSON, 'Bundle has an oversized/nested PAX extension.');
			pax = paxFields(await reader.read(memberSize));
			check((await reader.read((512 - memberSize % 512) % 512)).every((byte) => byte === 0), 'Bundle has invalid tar padding.');
			continue;
		}
		check(type === 48 || type === 0, 'Bundle contains a non-regular member.');
		if (pax) {
			if (pax.path !== undefined) memberName = pax.path;
			if (pax.size !== undefined) {
				check(/^(0|[1-9][0-9]*)$/.test(pax.size), 'Bundle has an invalid PAX size.');
				memberSize = Number(pax.size);
			}
			pax = undefined;
		}
		check(Number.isSafeInteger(memberSize) && memberSize >= 0, 'Bundle member exceeds safe integer range.');
		check(!members.has(memberName) && /^(oci-layout|index\.json|blobs\/sha256\/[0-9a-f]{64})$/.test(memberName),
			'Bundle contains a duplicate or unexpected member.');
		const isLayer = memberName === `blobs/sha256/${digest.slice(7)}`;
		check(isLayer ? memberSize === size : memberSize <= MAX_JSON, 'Bundle member size does not match the scenario.');
		const hash = createHash('sha256');
		const jsonChunks = [];
		for (let offset = 0; offset < memberSize;) {
			const bytes = await reader.read(Math.min(CHUNK, memberSize - offset));
			hash.update(bytes);
			if (isLayer) check(bytes.equals(await readFileChunk(file, offset, bytes.length)), 'Bundled layer bytes differ from the supplied file.');
			else jsonChunks.push(bytes);
			offset += bytes.length;
		}
		const actualDigest = `sha256:${hash.digest('hex')}`;
		if (memberName.startsWith('blobs/')) check(memberName === `blobs/sha256/${actualDigest.slice(7)}`, 'OCI member bytes do not match their digest path.');
		members.set(memberName, { size: memberSize, json: isLayer ? undefined : parseJson(Buffer.concat(jsonChunks)) });
		check((await reader.read((512 - memberSize % 512) % 512)).every((byte) => byte === 0), 'Bundle has invalid tar padding.');
	}
	check(terminated, 'Bundle exceeds the single-root scenario member limit.');
	check(members.get('oci-layout')?.json?.imageLayoutVersion === '1.0.0', 'Bundle is missing its OCI layout version.');
	const index = members.get('index.json')?.json;
	check(index?.schemaVersion === 2 && index.mediaType === INDEX && Array.isArray(index.manifests) && index.manifests.length === 1,
		'Bundle index does not describe exactly one manifest.');
	function resolve(descriptor, mediaType) {
		check(descriptor && DIGEST.test(descriptor.digest) && descriptor.mediaType === mediaType && Number.isSafeInteger(descriptor.size),
			'Bundle has an invalid OCI descriptor.');
		const member = members.get(`blobs/sha256/${descriptor.digest.slice(7)}`);
		check(member && member.size === descriptor.size, 'OCI descriptor does not resolve to matching bytes/size.');
		return member;
	}
	const manifest = resolve(index.manifests[0], MANIFEST).json;
	check(manifest?.schemaVersion === 2 && manifest.mediaType === MANIFEST && Array.isArray(manifest.layers) && manifest.layers.length === 1,
		'Bundle manifest does not describe the complete single-root chain.');
	const layer = manifest.layers[0];
	resolve(layer, SQUASHFS);
	check(layer.digest === digest && layer.size === size && layer.annotations?.[`${ANNOTATION}name`] === name &&
		layer.annotations?.[`${ANNOTATION}config-digest`] === configDigest, 'Bundle layer descriptor differs from registered metadata.');
	const bundledConfig = resolve(manifest.config, CONFIG).json;
	check(manifest.config.digest === configDigest && canonical(bundledConfig) === canonical(config), 'Bundle config differs from registered metadata.');
	for (const annotations of [manifest.annotations, index.manifests[0].annotations]) {
		check(annotations?.[`${ANNOTATION}name`] === name && annotations?.[`${ANNOTATION}chain-id`] === digest, 'Bundle manifest/index annotations do not identify the root chain.');
	}
	check(members.size === 5, 'Bundle contains unreferenced entries outside the single-root scenario.');
}

export async function verifyPalimpsest(client, { env, exercise }) {
	for (const path of ['/v1/layers', '/v1/images', '/v1/image-exports']) {
		check(Array.isArray(await client.request(path)), 'Palimpsest did not return a native catalogue array.');
	}
	if (!exercise) return ['authenticated layers/images/image-exports catalogues; read-only connection only (no byte-integrity or cloud export acceptance)'];
	const input = required(env, 'PALIMPSEST_SMOKE_BLOB');
	check(input.endsWith('.sqsh'), 'PALIMPSEST_SMOKE_BLOB must be a real locally supplied .sqsh file; no synthetic blob is generated.');
	const bundleOption = env.PALIMPSEST_SMOKE_BUNDLE?.trim() || '0';
	check(['0', '1'].includes(bundleOption), 'PALIMPSEST_SMOKE_BUNDLE must be 0 or 1.');
	let file;
	try { file = await open(input, 'r'); } catch { throw new Error('Could not open PALIMPSEST_SMOKE_BLOB; supply a readable real local .sqsh.'); }
	return withCleanup(async () => {
		const initial = await fileStat(file);
		check(initial.isFile() && Number.isSafeInteger(initial.size) && initial.size >= 96, 'PALIMPSEST_SMOKE_BLOB must be a regular SquashFS file.');
		const superblock = await readFileChunk(file, 0, 96);
		check(superblock.subarray(0, 4).toString('ascii') === 'hsqs' && superblock.readUInt16LE(28) === 4 && superblock.readUInt16LE(30) === 0 &&
			superblock.readBigUInt64LE(40) >= 96n && superblock.readBigUInt64LE(40) <= BigInt(initial.size),
			'Input lacks a valid SquashFS v4 superblock; caller must supply a real .sqsh, not renamed arbitrary bytes.');
		const hash = createHash('sha256');
		for (let offset = 0; offset < initial.size; offset += CHUNK) hash.update(await readFileChunk(file, offset, Math.min(CHUNK, initial.size - offset)));
		const digest = `sha256:${hash.digest('hex')}`;
		sameFile(initial, await fileStat(file));
		const layerPath = `/v1/layers/${digest}`;
		const visible = await client.request(layerPath, { expected: [200, 404], format: 'response' });
		await visible.arrayBuffer();
		check(visible.status === 404, 'Supplied digest is already visible; refusing to delete, replace or reuse another registration. Supply a different real .sqsh.');
		// Invalid syntax can never identify a catalogue row. FastAPI runs require_admin
		// before the handler, so 422 proves DELETE authority without deleting anything.
		// Do NOT probe an absent valid digest: an invisible row could actually exist.
		const authority = await client.request('/v1/layers/not-a-sha256-digest', { method: 'DELETE', expected: [401, 403, 422], format: 'response' });
		await authority.arrayBuffer();
		check(authority.status === 422, `Cleanup requires project-scoped Keystone auth plus a system-admin assignment; safe DELETE preflight refused (HTTP ${authority.status}). Source: ${sources.admin}`);
		const name = `service-verify-${randomUUID()}`;
		const config = {
			name, kind: 'squashfs', ubuntu_base: null, python_version: null, parent_digest: null,
			chain_id: digest, blob_digest: digest, disk_format: null, arch: null, os_variant: null, base_image_digest: null
		};
		const configDigest = sha256(Buffer.from(canonical(config)));
		let sessionId;
		let owner;
		let finalizeAttempted = false;
		let shared = false;
		return withCleanup(async () => {
			const started = await client.request('/v1/uploads', { method: 'POST', json: { digest } });
			// A concurrent registration may win after the visibility check. Never own it.
			shared = started.completed === true || started.already_present === true || started.registered === true;
			if (!shared && /^[0-9a-f]{32}$/.test(started.session_id)) sessionId = started.session_id;
			check(!shared, 'Upload reports a shared/already-present registration; refusing reuse or layer deletion.');
			check(sessionId && started.completed === false && started.received_bytes === 0, 'Hub did not create an empty upload session.');
			const uploadPath = `/v1/uploads/${sessionId}`;
			owner = await client.request(uploadPath);
			check(owner.session_id === sessionId && owner.declared_digest === digest && owner.received_bytes === 0 &&
				typeof owner.project_id === 'string' && owner.project_id && typeof owner.created_by === 'string' && owner.created_by,
				'Hub upload status did not identify the owned empty session.');
			// At least two nonempty PATCHes, even for a very small legitimate input.
			const chunkSize = Math.min(CHUNK, Math.ceil(initial.size / 2));
			let chunks = 0;
			for (let offset = 0; offset < initial.size;) {
				const bytes = await readFileChunk(file, offset, Math.min(chunkSize, initial.size - offset));
				const response = await client.request(uploadPath, {
					method: 'PATCH', body: bytes, headers: { 'Content-Type': 'application/octet-stream', 'Upload-Offset': String(offset) }, format: 'response'
				});
				const progress = await jsonResponse(response, 'Upload PATCH');
				offset += bytes.length;
				check(progress.session_id === sessionId && progress.received_bytes === offset && response.headers.get('Upload-Offset') === String(offset),
					'Hub PATCH progress/Upload-Offset does not match the actual appended bytes.');
				chunks++;
			}
			check(chunks >= 2, 'Upload did not exercise multiple chunks.');
			const status = await client.request(uploadPath);
			check(status.session_id === sessionId && status.declared_digest === digest && status.received_bytes === initial.size &&
				status.project_id === owner.project_id && status.created_by === owner.created_by, 'Hub upload status does not reconcile with all chunks.');
			sameFile(initial, await fileStat(file));
			finalizeAttempted = true;
			const finalized = await client.request(uploadPath, {
				method: 'PUT', headers: { 'Upload-Offset': String(initial.size) },
				json: { name, kind: 'squashfs', parent_digest: null, chain_id: digest, is_published: false, media_type: SQUASHFS }
			});
			shared = finalized.already_present === true;
			check(finalized.already_present === false, 'Finalize reports shared/already-present or ambiguous ownership; shared layers are never deleted.');
			check(finalized.blob_digest === digest && finalized.size_bytes === initial.size, 'Finalize digest/size differs from the actual supplied bytes.');
			const detail = await client.request(layerPath);
			check(detail.blob_digest === digest && detail.size_bytes === initial.size && detail.name === name && detail.kind === 'squashfs' &&
				detail.media_type === SQUASHFS && detail.chain_id === digest && detail.parent_digest === null && detail.is_published === false &&
				detail.project_id === owner.project_id && detail.created_by === owner.created_by && detail.config_digest === configDigest &&
				canonical(detail.config_json) === canonical(config) && detail.chain_complete === true && Array.isArray(detail.ancestors) && detail.ancestors.length === 0,
				'Hub detail does not match the owned byte digest, size, metadata or complete root chain.');
			const ancestors = await client.request(`${layerPath}/ancestors`);
			check(Array.isArray(ancestors) && ancestors.length === 1 && ancestors[0].blob_digest === digest && ancestors[0].chain_id === digest && ancestors[0].parent_digest === null,
				'Hub ancestor endpoint does not return the complete single-root chain.');
			await compareDownload(await client.request(`${layerPath}/blob`, { format: 'response' }), file, initial.size, digest);
			if (bundleOption === '1') {
				const bundle = await client.request('/v1/bundles', { method: 'POST', json: { refs: [digest], include_base_image: false }, format: 'response' });
				await verifyBundle(bundle, file, initial.size, digest, name, configDigest, config);
			}
			sameFile(initial, await fileStat(file));
			return [
				`declared byte SHA-256 → ${chunks} offset-checked PATCH chunks → finalized metadata/complete root chain → download SHA-256 and byte-for-byte equality (${initial.size} bytes)`,
				bundleOption === '1' ? `OCI tar blob bytes/digests, config and index/manifest references verified; source: ${sources.bundle}` : 'OCI bundle scope not requested (set PALIMPSEST_SMOKE_BUNDLE=1); not exercised',
				`own upload/catalogue registration cleaned; detail/search absent after DELETE; physical CAS retained for deferred service GC, not erased or GC-verified; sources: ${sources.cleanup}, ${sources.gc}`,
				`prerequisites: caller-supplied real .sqsh, enabled writable Hub store, project-scoped Keystone token with system-admin DELETE authority; sources: ${sources.admin}, ${sources.upload}, ${sources.digest}`,
				'boundaries: one private root layer only; no multi-layer ancestry, visibility isolation, range/resume faults, bundle import, base cloud image, KVM, VM boot or OpenStack image export acceptance'
			];
		}, async () => {
			const failures = [];
			// The random metadata marker plus the captured project/user is also used
			// after a lost PUT response; digest absence alone never proves ownership.
			if (finalizeAttempted && !shared && owner) {
				try {
					const response = await client.request(layerPath, { expected: [200, 404], format: 'response' });
					if (response.status === 200) {
						const row = await jsonResponse(response, 'Cleanup detail');
						check(row.blob_digest === digest && row.name === name && row.config_json?.name === name && row.project_id === owner.project_id && row.created_by === owner.created_by,
							'Catalogue ownership is not this run; refusing layer deletion.');
						await client.request(layerPath, { method: 'DELETE', expected: [204], format: 'empty' });
						await client.request(layerPath, { expected: [404], format: 'empty' });
						const catalogue = await client.request(`/v1/layers?digest=${encodeURIComponent(digest)}`);
						check(Array.isArray(catalogue) && catalogue.length === 0, 'Deleted layer remains in the visible catalogue.');
					} else await response.arrayBuffer();
				} catch (error) { failures.push(error.message); }
			}
			if (sessionId) {
				try {
					await client.request(`/v1/uploads/${sessionId}`, { method: 'DELETE', expected: [204, 404], format: 'empty' });
					await client.request(`/v1/uploads/${sessionId}`, { expected: [404], format: 'empty' });
				} catch (error) { failures.push(error.message); }
			}
			check(failures.length === 0, failures.join('; '));
		});
	}, async () => {
		try { await file.close(); } catch { throw new Error('Could not close the local smoke blob.'); }
	});
}
