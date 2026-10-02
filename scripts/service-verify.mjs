#!/usr/bin/env node
import { pathToFileURL } from 'node:url';
import { check, createClient, required } from './service-verify-http.mjs';
import { verifyLumen } from './service-verify-lumen.mjs';
import { verifyWaygate } from './service-verify-waygate.mjs';
import { verifyPalimpsest } from './service-verify-palimpsest.mjs';

const services = {
	lumen: { url: 'http://127.0.0.1:8012', verify: verifyLumen },
	waygate: { url: 'http://127.0.0.1:8010', verify: verifyWaygate },
	palimpsest: { url: 'http://127.0.0.1:8020', verify: verifyPalimpsest }
};

function help() {
	console.log(`Usage: npm run services:verify -- <lumen|waygate|palimpsest> [--exercise]

No Docker, full-stack config, Drover or remote dashboard preflight is required.
Without --exercise: authenticated read-only connection check, NOT logic acceptance.
With --exercise: actual HTTP service logic; may incur Lumen provider charges.

Manual inputs (environment variables; secrets are never printed or persisted):
  <SERVICE>_API_BASE_URL          HTTP(S) origin or /v1 base; defaults to loopback
  LUMEN_API_KEY                   Scoped ordinary Lumen API key, or
  LUMEN_SMOKE_TOKEN               Keystone token (not an Afterglow JWT)
  WAYGATE_SMOKE_TOKEN             Keystone token
  PALIMPSEST_SMOKE_TOKEN          Keystone token
  <SERVICE>_SMOKE_PROJECT_ID      Optional authorized project scope
  LUMEN_SMOKE_MODEL_ID            Active text model for --exercise
  LUMEN_SMOKE_PROMPT              Optional short text input
  LUMEN_SMOKE_EXPECT_TEXT         Optional expected output substring
  WAYGATE_SMOKE_SERVER_ID         Exclusively reserved ACTIVE source, no clients
  WAYGATE_SMOKE_IMPORT_SERVER_ID  Distinct owned ACTIVE target, no clients
  PALIMPSEST_SMOKE_BLOB           Local real .sqsh; system-admin cleanup required
  PALIMPSEST_SMOKE_BUNDLE         Optional 1: validate downloaded OCI bundle

Example: LUMEN_API_BASE_URL=http://127.0.0.1:18013/v1 npm run services:verify -- lumen --exercise
Only the chosen service is contacted. Redirects/auth bypass/provider fallback are forbidden.
Cloud provisioning, callback routing, VPN data plane and provider authenticity are separate acceptance boundaries.`);
}

export async function main(args = process.argv.slice(2), env = process.env) {
	if (!args.length || (args.length === 1 && ['help', '--help'].includes(args[0]))) { help(); return; }
	const [name, ...options] = args;
	check(Object.hasOwn(services, name) && (options.length === 0 || (options.length === 1 && options[0] === '--exercise')),
		'Choose one of lumen|waygate|palimpsest and optional --exercise. Credentials are accepted only via environment.');
	const prefix = name.toUpperCase();
	const key = name === 'lumen' ? env.LUMEN_API_KEY?.trim() : undefined;
	check(!(key && env.LUMEN_SMOKE_TOKEN?.trim()), 'Choose LUMEN_API_KEY or LUMEN_SMOKE_TOKEN, not both.');
	const headers = key ? { Authorization: `Bearer ${key}` } : { 'X-Auth-Token': required(env, `${prefix}_SMOKE_TOKEN`) };
	const project = env[`${prefix}_SMOKE_PROJECT_ID`]?.trim();
	if (project) headers['X-Project-Id'] = project;
	const client = createClient({ url: env[`${prefix}_API_BASE_URL`] || services[name].url, headers });
	const exercise = options.includes('--exercise');
	console.log(`${name}: ${client.origin}; ${exercise ? 'service-real exercise (explicit mutation/provider opt-in)' : 'read-only connection check'}`);
	const evidence = await services[name].verify(client, { env, exercise });
	for (const line of evidence) console.log(`${name}: ${line}`);
	console.log(`${name}: ${exercise ? 'service-real scenario passed; unexercised upstream/cloud boundaries are not promoted' : 'connection passed; real logic was not exercised'}`);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
	main().catch((error) => { console.error(`service-verify: ${error.message}`); process.exitCode = 1; });
}
