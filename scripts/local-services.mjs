#!/usr/bin/env node
/**
 * Run one current-source local stack on the conventional Afterglow ports.
 * Private volumes and keys remain scoped to the same Compose project.
 *
 * This script intentionally has no dependency on dotenv: Docker Compose reads
 * .env for containers, while this process only checks that the file exists and
 * never prints its contents.
 */
import { chmodSync, constants, copyFileSync, existsSync, mkdirSync, readFileSync, statSync, writeFileSync } from 'node:fs';
import { randomBytes } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import http from 'node:http';

const PROJECT = 'afterglow-local-services';
const LOCAL_DIR = '.local-services';
const LOCAL_PORTS = { frontend: 3080, backend: 8000, redis: 6379, 'waygate-api': 8010, 'drover-api': 8011, 'lumen-api': 8012, 'palimpsest-api': 8020 };
let composeEnvironment;
let composeInputs;
const COMPOSE_FILE = 'docker-compose.dev.yml';
const SERVICES = [
	'backend',
	'frontend',
	'redis',
	'service-mariadb',
	'afterglow-mariadb',
	'lumen-postgres',
	'waygate-api',
	'waygate-worker',
	'drover-api',
	'drover-worker',
	'lumen-api',
	'lumen-worker',
	'palimpsest-api',
	'palimpsest-worker'
];
const ONE_OFF_SERVICES = ['waygate-migrate', 'drover-migrate', 'lumen-migrate', 'palimpsest-bootstrap'];
const RUNNING_SERVICES = [
	'backend',
	'frontend',
	'redis',
	'service-mariadb',
	'afterglow-mariadb',
	'lumen-postgres',
	'waygate-api',
	'waygate-worker',
	'drover-api',
	'drover-worker',
	'lumen-api',
	'lumen-worker',
	'palimpsest-api',
	'palimpsest-worker'
];
const SIBLING_BUILDS = [
	['Lumen', '../lumen/Dockerfile'],
	['Drover', '../drover/Dockerfile'],
	['Waygate', '../waygate/Dockerfile'],
	['Palimpsest Hub', '../palimpsest/hub/Dockerfile']
];

function fail(message) {
	console.error(`\nlocal-services: ${message}`);
	process.exitCode = 1;
	throw new Error(message);
}

function run(command, args, { capture = false } = {}) {
	const result = spawnSync(command, args, {
		cwd: process.cwd(),
		env: composeEnvironment,
		encoding: 'utf8',
		stdio: capture ? ['ignore', 'pipe', 'pipe'] : 'inherit'
	});
	if (result.error) fail(`could not run ${command}: ${result.error.message}`);
	if (result.status !== 0) {
		const detail = capture ? (result.stderr || '').trim() : '';
		fail(`${command} ${args.join(' ')} failed${detail ? `: ${detail}` : ''}`);
	}
	return capture ? result.stdout.trim() : '';
}

function composeArgs() {
	return [
		'compose',
		...(existsSync('.env') ? ['--env-file', '.env'] : []),
		'--project-name', PROJECT,
		'-f', COMPOSE_FILE
	];
}

function compose(args, options = {}) {
	return run('docker', [...composeArgs(), ...args], options);
}

function assertDockerCompose() {
	const version = run('docker', ['compose', 'version', '--short'], { capture: true });
	const match = version.match(/(\d+)\.(\d+)\.(\d+)/);
	if (!match) fail(`could not determine Docker Compose version from ${JSON.stringify(version)}`);
	const [, major, minor] = match.map(Number);
	if (major < 2 || (major === 2 && minor < 24)) {
		fail(`Docker Compose ${version} is too old; 2.24+ is required for optional env files.`);
	}
}

function assertLocalPrerequisites() {
	assertDockerCompose();
	for (const path of ['.env', 'afterglow.conf']) {
		if (!existsSync(path)) {
			fail(
				`${path} is missing. Create it from its tracked example before starting local services.`
			);
		}
	}
	prepareLocalConfiguration();
}

function assertSiblingSources() {
	const missing = SIBLING_BUILDS.filter(([, path]) => !existsSync(path));
	if (missing.length === 0) return;
	const names = missing.map(([name, path]) => `${name} (${path})`).join(', ');
	fail(`current sibling source is unavailable: ${names}. Nothing was started. Restore the source checkouts; published-image deployment belongs to docker-compose.prod.yml.`);
}

function prepareLocalConfiguration() {
	mkdirSync(LOCAL_DIR, { recursive: true, mode: 0o700 });
	chmodSync(LOCAL_DIR, 0o700);
	const configPath = `${LOCAL_DIR}/afterglow.conf`;
	if (!existsSync(configPath)) copyFileSync('afterglow.conf', configPath, constants.COPYFILE_EXCL);
	chmodSync(configPath, 0o640);
	const secretPath = `${LOCAL_DIR}/secrets.json`;
	const secretNames = ['AFTERGLOW_LOCAL_SECRET_KEY', 'AFTERGLOW_LOCAL_ENCRYPTION_KEY', 'AFTERGLOW_LOCAL_SERVICE_TOKEN'];
	if (!existsSync(secretPath)) {
		writeFileSync(secretPath, JSON.stringify(Object.fromEntries(secretNames.map((key) => [key, randomBytes(32).toString('hex')]))), { flag: 'wx', mode: 0o600 });
	}
	let secrets;
	try { secrets = JSON.parse(readFileSync(secretPath, 'utf8')); } catch { fail('Local secrets.json is unreadable; its contents were not printed.'); }
	if (secretNames.some((key) => !/^[a-f0-9]{64}$/.test(secrets[key] ?? ''))) fail('Local secrets.json must contain the three generated 32-byte keys.');
	const python = existsSync('backend/.venv/bin/python') ? 'backend/.venv/bin/python' : 'python3';
	const credentials = JSON.parse(run(python, ['-c', `
import json, tomllib
from pathlib import Path
with Path('.local-services/afterglow.conf').open('rb') as handle:
    config = tomllib.load(handle)
openstack = config.get('openstack', {})
services = config.get('services', {})
fields = {'AUTH_URL': ('auth_url', ''), 'USERNAME': ('username', ''), 'PASSWORD': ('password', ''), 'PROJECT_NAME': ('project_name', 'admin'), 'USER_DOMAIN_NAME': ('user_domain_name', 'Default'), 'PROJECT_DOMAIN_NAME': ('project_domain_name', 'Default'), 'REGION_NAME': ('region_name', 'RegionOne'), 'INTERFACE': ('interface', 'internal')}
fields['SERVICE_PROJECT_ID'] = ('service_project_id', '')
private_endpoints = {
    'AFTERGLOW_LOCAL_' + key: value.strip()
    for key, field in {'WAYGATE_INTERNAL_URL': 'waygate_internal_url', 'DROVER_INTERNAL_URL': 'drover_internal_url', 'LUMEN_INTERNAL_URL': 'lumen_internal_url', 'PALIMPSEST_INTERNAL_URL': 'palimpsest_internal_url'}.items()
    if isinstance(value := services.get(field), str) and value.strip()
}
print(json.dumps({'AFTERGLOW_LOCAL_OS_' + key: str(openstack.get(field, default)) for key, (field, default) in fields.items()} | private_endpoints, allow_nan=False))
`], { capture: true }));
	if (['AUTH_URL', 'USERNAME', 'PASSWORD'].some((key) => !credentials[`AFTERGLOW_LOCAL_OS_${key}`])) fail('The local afterglow.conf needs OpenStack auth_url, username and password.');
	composeInputs = { ...credentials, ...secrets, AFTERGLOW_LOCAL_CONFIG_GID: String(statSync(configPath).gid) };
	composeEnvironment = { ...process.env, ...composeInputs };
}

function assertIsolatedConfiguration() {
	const config = JSON.parse(compose(['config', '--format', 'json'], { capture: true }));
	if (config.name !== PROJECT) fail('Compose project isolation was lost.');
	const configSnapshotSource = `${process.cwd()}/${LOCAL_DIR}/afterglow.conf`;
	const snapshotReaderGid = composeInputs.AFTERGLOW_LOCAL_CONFIG_GID;
	for (const name of [...RUNNING_SERVICES, ...ONE_OFF_SERVICES]) {
		const service = config.services[name];
		if (!service || service.container_name) fail(`${name} must use project-scoped containers.`);
		const environment = service.environment ?? {};
		if (environment.DATABASE_URL) {
			const database = new URL(environment.DATABASE_URL);
			const schema = name === 'backend' ? 'afterglow' : name.split('-')[0];
			if (database.hostname !== (name === 'backend' ? 'afterglow-mariadb' : 'service-mariadb') || database.pathname !== `/${schema}`) fail(`${name} is not isolated to its local database.`);
		}
		if (environment.REDIS_URL && new URL(environment.REDIS_URL).hostname !== 'redis') fail(`${name} is not isolated to the local Redis.`);
		const ports = service.ports ?? [];
		const expectedPort = LOCAL_PORTS[name];
		if (ports.length !== (expectedPort ? 1 : 0) || ports.some((port) => port.host_ip !== '127.0.0.1' || Number(port.published) !== expectedPort || Number(port.target) !== expectedPort)) fail(`${name} must expose only its canonical loopback port.`);
		for (const mount of service.volumes ?? []) {
			if (mount.type === 'volume') {
				const volume = config.volumes[mount.source];
				if (volume.external || !volume.name.startsWith(`${PROJECT}_`)) fail(`${name} would reuse a non-local volume.`);
			} else if (!mount.source.startsWith(`${process.cwd()}/${LOCAL_DIR}/`) && name !== 'service-mariadb') {
				fail(`${name} would mount files outside the isolated configuration directory.`);
			}
		}
		for (const networkName of Object.keys(service.networks ?? {})) {
			const network = config.networks[networkName];
			if (network.external || !network.name.startsWith(`${PROJECT}_`)) fail(`${name} would join a non-local network.`);
		}
	}
	for (const [name, service] of Object.entries(config.services)) {
		const readsSnapshot = (service.volumes ?? []).some((mount) => mount.type === 'bind' && mount.source === configSnapshotSource);
		const groupAdds = (service.group_add ?? []).map(String);
		if (readsSnapshot && !groupAdds.includes(snapshotReaderGid)) fail(`${name} must receive the local configuration snapshot reader group.`);
		if (!readsSnapshot && groupAdds.includes(snapshotReaderGid)) fail(`${name} must not receive the local configuration snapshot reader group.`);
	}
	if (String(config.services.backend.environment.SENTINEL_ENABLED) !== 'false') fail('The backend must not discover a remote Sentinel master.');
	if (!config.services['drover-api'].environment.OS_SERVICE_PROJECT_ID) fail('Drover readiness requires [openstack] service_project_id in .local-services/afterglow.conf or OS_SERVICE_PROJECT_ID in .env. Select the dedicated service project; no admin-project fallback is allowed.');
	for (const name of ['drover-api', 'drover-worker', 'drover-migrate']) {
		const environment = config.services[name].environment ?? {};
		if (String(environment.SENTINEL_ENABLED) !== 'false' || String(environment.SENTINEL_HOSTS) !== '') fail(`${name} must not discover a remote Sentinel master.`);
	}
	for (const name of ['lumen-api', 'lumen-worker', 'lumen-migrate']) {
		if (new URL(config.services[name].environment.CHAT_CHECKPOINTER_POSTGRES_URL).hostname !== 'lumen-postgres') fail(`${name} would reuse a non-local checkpointer.`);
	}
	console.log(`Isolation checked: ${PROJECT}; local databases, cache, volumes, network and loopback ports.`);
	composeInputs.AFTERGLOW_LOCAL_OS_SERVICE_PROJECT_ID = config.services['drover-api'].environment.OS_SERVICE_PROJECT_ID;
	for (const name of ['SERVICE_WAYGATE_INTERNAL_URL', 'SERVICE_DROVER_INTERNAL_URL', 'SERVICE_LUMEN_INTERNAL_URL', 'SERVICE_PALIMPSEST_INTERNAL_URL']) {
		composeInputs[name] = config.services.backend.environment[name] ?? '';
	}
	composeInputs.LUMEN_MCP_CONTROL_PLANE_URL = config.services['lumen-api'].environment.MCP_CONTROL_PLANE_URL ?? '';
	const envPath = `${LOCAL_DIR}/compose.env`;
	const contents = Object.entries(composeInputs)
		.map(([name, value]) => `${name}=${JSON.stringify(String(value).replaceAll('$', '$$'))}`)
		.join('\n') + '\n';
	writeFileSync(envPath, contents, { mode: 0o600 });
	chmodSync(envPath, 0o600);
}

function assertNoLegacyStack() {
	const containers = run('docker', ['ps', '--all', '--filter', 'label=com.docker.compose.project=afterglow', '--format', '{{.Names}}'], { capture: true });
	if (containers) fail('Legacy afterglow containers still exist. Retire that deployment while preserving its data before starting the canonical local stack; this runner never deletes another project automatically.');
}

function parseComposeRows(output) {
	if (!output) return [];
	try {
		const parsed = JSON.parse(output);
		return Array.isArray(parsed) ? parsed : [parsed];
	} catch {
		try {
			return output
				.split('\n')
				.filter(Boolean)
				.map((line) => JSON.parse(line));
		} catch {
			fail('Docker Compose returned an unreadable service-status document.');
		}
	}
}

function composeRows() {
	const output = compose(['ps', '--all', '--format', 'json'], { capture: true });
	return parseComposeRows(output);
}

function serviceRow(rows, service) {
	const row = rows.find((candidate) => candidate.Service === service || candidate.service === service);
	if (!row) fail(`${service} has no container in the ${PROJECT} project. Run npm run services:up first.`);
	return row;
}

function assertStackState() {
	const rows = composeRows();
	for (const service of ONE_OFF_SERVICES) {
		const row = serviceRow(rows, service);
		const state = String(row.State ?? row.state ?? '').toLowerCase();
		const exitCode = Number(row.ExitCode ?? row.exitCode);
		if (state !== 'exited' || exitCode !== 0) {
			fail(`${service} did not complete successfully (state=${state || 'unknown'}, exit=${Number.isNaN(exitCode) ? 'unknown' : exitCode}).`);
		}
	}
	for (const service of RUNNING_SERVICES) {
		const row = serviceRow(rows, service);
		const state = String(row.State ?? row.state ?? '').toLowerCase();
		if (state !== 'running') fail(`${service} is not running (state=${state || 'unknown'}).`);
	}
}

function requestJson(label, url, headers = {}, body = undefined) {
	return new Promise((resolve, reject) => {
		const target = new URL(url);
		const payload = body === undefined ? undefined : JSON.stringify(body);
		const request = http.request(
			{
				protocol: target.protocol,
				hostname: target.hostname,
				port: target.port,
				path: `${target.pathname}${target.search}`,
				method: payload === undefined ? 'GET' : 'POST',
				headers: {
					Accept: 'application/json',
					...(payload === undefined ? {} : { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(payload) }),
					...headers
				},
				timeout: 30_000
			},
			(response) => {
				const chunks = [];
				response.on('data', (chunk) => chunks.push(chunk));
				response.on('end', () => {
					const text = Buffer.concat(chunks).toString('utf8');
					let json;
					try {
						json = text ? JSON.parse(text) : null;
					} catch {
						reject(new Error(`${label} returned HTTP ${response.statusCode} with a non-JSON response`));
						return;
					}
					if (response.statusCode !== 200) {
						reject(new Error(`${label} returned HTTP ${response.statusCode}`));
						return;
					}
					resolve(json);
				});
			}
		);
		request.on('timeout', () => request.destroy(new Error(`${label} timed out after 30 seconds`)));
		request.on('error', (error) => reject(new Error(`${label} failed: ${error.message}`)));
		if (payload !== undefined) request.write(payload);
		request.end();
	});
}

function assertStatus(label, json) {
	if (!json || json.status !== 'ok') fail(`${label} did not return a healthy status.`);
}

async function runDirectSmoke() {
	assertStatus('Afterglow backend health', await requestJson('Afterglow backend health', 'http://127.0.0.1:8000/api/v1/health'));
	assertStatus('Afterglow frontend health', await requestJson('Afterglow frontend health', 'http://127.0.0.1:3080/health'));
	assertStatus('Waygate health', await requestJson('Waygate health', 'http://127.0.0.1:8010/v1/health'));
	assertStatus('Drover readiness', await requestJson('Drover readiness', 'http://127.0.0.1:8011/v1/health/ready'));
	assertStatus('Lumen health', await requestJson('Lumen health', 'http://127.0.0.1:8012/v1/health'));
	assertStatus('Palimpsest health', await requestJson('Palimpsest health', 'http://127.0.0.1:8020/v1/health'));
	const schema = await requestJson('Lumen API contract', 'http://127.0.0.1:8012/openapi.json');
	const patchSchema = schema.paths?.['/v1/admin/providers/{provider_id}']?.patch?.requestBody?.content?.['application/json']?.schema;
	const update = schema.components?.schemas?.[patchSchema?.$ref?.split('/').at(-1)];
	if (!schema.paths?.['/v1/admin/providers/billing']?.get || !Object.hasOwn(update?.properties ?? {}, 'billing_admin_key')) fail('The running Lumen API lacks the administrator billing contract. Deploy current API/worker source and its migrations.');
}

function bffHeaders() {
	const token = process.env.AFTERGLOW_SMOKE_TOKEN?.trim();
	if (!token) {
		fail(
			'AFTERGLOW_SMOKE_TOKEN is required for authenticated BFF checks. Supply a short-lived Afterglow access token in your shell; the script never reads or prints it.'
		);
	}
	const headers = { Authorization: `Bearer ${token}` };
	const projectId = process.env.AFTERGLOW_SMOKE_PROJECT_ID?.trim();
	if (projectId) headers['X-Project-Id'] = projectId;
	return headers;
}

async function runBffSmoke() {
	const headers = bffHeaders();
	for (const [label, path] of [
		['Waygate BFF discovery', '/api/v1/waygate'],
		['Drover BFF discovery', '/api/v1/k3s'],
		['Palimpsest BFF discovery', '/api/v1/palimpsest/hub']
	]) {
		const response = await requestJson(label, `http://127.0.0.1:8000${path}`, headers);
		if (!response || typeof response !== 'object' || !response.version) fail(`${label} returned an invalid version document.`);
	}
	for (const [label, path] of [
		['Waygate BFF read check', '/api/v1/waygate/servers'],
		['Drover BFF read check', '/api/v1/k3s/clusters'],
		['Palimpsest BFF read check', '/api/v1/palimpsest/hub/layers']
	]) {
		const response = await requestJson(label, `http://127.0.0.1:8000${path}`, headers);
		if (!Array.isArray(response)) fail(`${label} returned a non-list response.`);
	}


	const models = await requestJson('Lumen model BFF', 'http://127.0.0.1:8000/api/v1/chat/models', headers);
	if (!Array.isArray(models)) fail('Lumen model BFF returned a non-list response.');

	const modelId = process.env.LUMEN_SMOKE_MODEL_ID?.trim();
	const conversationId = process.env.LUMEN_SMOKE_CONVERSATION_ID?.trim();
	if (!modelId || !conversationId) {
		fail(
			'LUMEN_SMOKE_MODEL_ID and LUMEN_SMOKE_CONVERSATION_ID are required for the read-only Lumen context-preview check. Select an active model and a conversation owned by the smoke user.'
		);
	}
	const selectedModel = models.find((model) => [String(model?.id), model?.model_name, model?.api_model_name].includes(modelId));
	if (!selectedModel) {
		fail('LUMEN_SMOKE_MODEL_ID is not present in the authenticated active-model response.');
	}
	const context = await requestJson(
		'Lumen context-preview BFF',
		`http://127.0.0.1:8000/api/v1/chat/conversations/${encodeURIComponent(conversationId)}/context-preview`,
		headers,
		{ model_id: selectedModel.model_name, parts: [] }
	);
	if (!context || typeof context.model_name !== 'string' || typeof context.revision !== 'string') {
		fail('Lumen context-preview BFF returned an invalid context state.');
	}
	if (!context.breakdown || context.breakdown.scope !== 'preview') fail('The running Lumen API did not return the current context inspector contract.');
	if (context.breakdown.complete) {
		const included = context.breakdown.components.filter((component) => component.included);
		if (included.some((component) => component.tokens === null) || included.reduce((sum, component) => sum + component.tokens, 0) !== context.input_tokens) fail('Lumen context components do not reconcile with input tokens.');
	}
	console.log(`Lumen context: ${context.model_name}; window=${context.context_limit ?? 'unknown'}; components=${context.breakdown.components.length}; complete=${context.breakdown.complete}`);
}

async function runDashboardSmoke() {
	const headers = bffHeaders();
	const checks = [
		['Dashboard instances', '/api/v1/dashboard/summary?view=overview&cache=false', (value) => Number.isInteger(value?.instances?.total) && Array.isArray(value?.recent_instances)],
		['Dashboard Drover stats', '/api/v1/dashboard/k3s-stats?cache=false', (value) => value?.available === true && Number.isInteger(value?.total) && value.total >= 0 && Number.isInteger(value?.active) && value.active >= 0 && value.active <= value.total],
		['Dashboard quotas', '/api/v1/dashboard/quotas?view=overview&cache=false', (value) => value?.compute && value?.storage && value?.network]
	];
	const results = await Promise.allSettled(checks.map(async ([label, path, valid]) => {
		const value = await requestJson(label, `http://127.0.0.1:8000${path}`, headers);
		if (!valid(value)) throw new Error(`${label} returned an invalid overview response`);
		console.log(`${label}: passed`);
	}));
	const failures = results.filter((result) => result.status === 'rejected').map((result) => result.reason.message);
	if (failures.length) throw new Error(failures.join('; '));
}

function printHelp() {
	console.log(`Usage:
  npm run services:config      Prepare private inputs for docker-compose.dev.yml
  npm run services:up          Build current source and start docker-compose.dev.yml
  npm run services:smoke       Check migrations, API contracts, BFFs and live dashboard data
  npm run services:down        Stop only ${PROJECT}; preserve volumes and every other project

Local ports: frontend 3080, backend 8000, Waygate 8010, Drover 8011, Lumen 8012, Palimpsest 8020, Redis 6379.
`);
}

async function main() {
	const [command, option] = process.argv.slice(2);
	if (!command || command === 'help' || command === '--help') {
		printHelp();
		return;
	}
	if (command === 'up') {
		if (option) fail(`unknown option ${option}; dev mode always builds current source.`);
		assertLocalPrerequisites();
		assertSiblingSources();
		assertIsolatedConfiguration();
		assertNoLegacyStack();
		compose(['up', '--build', '--wait', '--wait-timeout', '240', ...SERVICES]);
		console.log(`\nContainers ready: ${PROJECT} at http://localhost:3080. Application verification still requires npm run services:smoke.`);
		return;
	}
	if (command === 'config') {
		assertLocalPrerequisites();
		assertIsolatedConfiguration();
		console.log(`Prepared ${LOCAL_DIR}/compose.env (0600). Use docker compose --env-file ${LOCAL_DIR}/compose.env -f ${COMPOSE_FILE}.`);
		return;
	}
	if (command === 'smoke') {
		assertLocalPrerequisites();
		assertStackState();
		await runDirectSmoke();
		await runBffSmoke();
		await runDashboardSmoke();
		console.log('\nLocal extracted-services smoke checks passed.');
		return;
	}
	if (command === 'down') {
		assertLocalPrerequisites();
		compose(['down', '--timeout', '10']);
		console.log(`\nStopped ${PROJECT}. Named volumes were preserved; no other Compose project was touched.`);
		return;
	}
	fail(`unknown command ${command}; run npm run services:help.`);
}

main().catch((error) => {
	if (process.exitCode) return;
	console.error(`\nlocal-services: ${error.message}`);
	process.exitCode = 1;
});
