#!/usr/bin/env node
// Entry point: `npm run latency -- --target http://localhost:3080 --api-base http://localhost:8000`.
// Credentials come only from AFTERGLOW_LATENCY_USERNAME / AFTERGLOW_LATENCY_PASSWORD, never from argv.
import { parseArgs } from 'node:util';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { assertTargetAllowed, check, harvestDynamicRoutes, listPageRoutes, planRoutes } from './core.mjs';
import { DEFAULT_LEVELS, DEFAULT_PROBE, discoverGetEndpoints, fetchOpenApi, measureAuth, measureEndpoints, signIn, signOut } from './api-lane.mjs';
import { resolveChrome, runBrowserLane } from './browser-lane.mjs';
import { buildReport, renderMarkdown } from './report.mjs';

export const REPO_ROUTES_DIR = fileURLToPath(new URL('../../frontend/src/routes', import.meta.url));
const LANES = ['api', 'browser'];

function intOption(name, raw, { min, max }) {
	const value = Number(raw);
	check(Number.isInteger(value) && value >= min && value <= max, `--${name} must be an integer from ${min} to ${max}.`);
	return value;
}

function optionalNumber(name, raw) {
	if (raw === undefined) return undefined;
	const value = Number(raw);
	check(Number.isFinite(value) && value > 0, `--${name} must be a positive number.`);
	return value;
}

export function parseOptions(argv, env = process.env) {
	const { values } = parseArgs({
		args: argv,
		allowPositionals: false,
		strict: true,
		options: {
			target: { type: 'string' },
			'api-base': { type: 'string' },
			'allow-remote': { type: 'string', multiple: true, default: [] },
			lanes: { type: 'string', default: 'api,browser' },
			'routes-dir': { type: 'string', default: REPO_ROUTES_DIR },
			'route-fixtures': { type: 'string' },
			'route-filter': { type: 'string' },
			passes: { type: 'string', default: '2' },
			'quiet-ms': { type: 'string', default: '500' },
			'ready-timeout-ms': { type: 'string', default: '30000' },
			endpoint: { type: 'string', multiple: true, default: [] },
			'endpoint-filter': { type: 'string' },
			'endpoint-exclude': { type: 'string' },
			'max-endpoints': { type: 'string', default: '200' },
			samples: { type: 'string', default: '10' },
			levels: { type: 'string', default: DEFAULT_LEVELS.join(',') },
			rounds: { type: 'string', default: '3' },
			'auth-samples': { type: 'string', default: '5' },
			'auth-probe': { type: 'string', default: DEFAULT_PROBE },
			'timeout-ms': { type: 'string', default: '30000' },
			chrome: { type: 'string' },
			out: { type: 'string' },
			'budget-ready-p95-ms': { type: 'string' },
			'budget-api-p95-ms': { type: 'string' },
			interactive: { type: 'boolean', default: false },
			headful: { type: 'boolean', default: false },
			'dry-run': { type: 'boolean', default: false },
			help: { type: 'boolean', short: 'h', default: false }
		}
	});
	const target = values.target ?? env.AFTERGLOW_LATENCY_TARGET;
	const lanes = values.lanes.split(',').map((lane) => lane.trim()).filter(Boolean);
	check(lanes.length > 0 && lanes.every((lane) => LANES.includes(lane)), `--lanes must be a comma list of ${LANES.join(', ')}.`);
	const levels = values.levels.split(',').map((level) => intOption('levels', level.trim(), { min: 1, max: 100 }));
	const authSamples = intOption('auth-samples', values['auth-samples'], { min: 1, max: 9 });
	const budgets = {};
	const readyBudget = optionalNumber('budget-ready-p95-ms', values['budget-ready-p95-ms']);
	const apiBudget = optionalNumber('budget-api-p95-ms', values['budget-api-p95-ms']);
	if (readyBudget !== undefined) budgets.readyP95Ms = readyBudget;
	if (apiBudget !== undefined) budgets.apiP95Ms = apiBudget;
	return {
		help: values.help,
		target,
		apiBase: values['api-base'] ?? env.AFTERGLOW_LATENCY_API_BASE ?? target,
		allowRemote: values['allow-remote'],
		lanes,
		routesDir: resolve(values['routes-dir']),
		routeFixtures: values['route-fixtures'] ? resolve(values['route-fixtures']) : null,
		routeFilter: values['route-filter'] ? new RegExp(values['route-filter']) : null,
		passes: intOption('passes', values.passes, { min: 1, max: 10 }),
		quietMs: intOption('quiet-ms', values['quiet-ms'], { min: 50, max: 10000 }),
		readyTimeoutMs: intOption('ready-timeout-ms', values['ready-timeout-ms'], { min: 1000, max: 600000 }),
		endpoints: values.endpoint,
		endpointFilter: values['endpoint-filter'] ? new RegExp(values['endpoint-filter']) : null,
		endpointExclude: values['endpoint-exclude'] ? new RegExp(values['endpoint-exclude']) : null,
		maxEndpoints: intOption('max-endpoints', values['max-endpoints'], { min: 1, max: 10000 }),
		samples: intOption('samples', values.samples, { min: 1, max: 1000 }),
		levels,
		rounds: intOption('rounds', values.rounds, { min: 1, max: 100 }),
		authSamples,
		authProbe: values['auth-probe'] || null,
		timeoutMs: intOption('timeout-ms', values['timeout-ms'], { min: 100, max: 600000 }),
		chrome: values.chrome,
		out: values.out ? resolve(values.out) : null,
		budgets,
		interactive: values.interactive || values.headful,
		dryRun: values['dry-run']
	};
}

const USAGE = `Usage: npm run latency -- --target <frontend-origin> [options]

Credentials: AFTERGLOW_LATENCY_USERNAME and AFTERGLOW_LATENCY_PASSWORD (or use --interactive to log in manually in a Chrome window).
Environment: AFTERGLOW_LATENCY_TARGET, AFTERGLOW_LATENCY_API_BASE, AFTERGLOW_LATENCY_CHROME.

Interactive:     --interactive / --headful (opens visible Chrome window for manual sign-in, reuses session token)
Lanes:           --lanes api,browser (default both)
Routes:          --route-fixtures <json: {"/pattern/[id]": "/concrete/path"}> --route-filter <regex>
                 --passes 2 (pass 1 cold cache, later passes warm) --quiet-ms 500 --ready-timeout-ms 30000
API:             --endpoint <path> (repeatable) | from /openapi.json with --endpoint-filter/--endpoint-exclude
                 --max-endpoints 200 --samples 10 --levels 1,5,10,20 --rounds 3
                 --auth-samples 5 (max 9; login is rate-limited) --auth-probe /api/v1/auth/me
Safety:          non-loopback/private targets need --allow-remote <origin>
Output:          --out <dir> (default latency-reports/<timestamp>), --dry-run prints the plan only
Budgets:         --budget-ready-p95-ms <ms> --budget-api-p95-ms <ms> (fail when exceeded)
`;

function credentials(env, { interactive = false } = {}) {
	const username = env.AFTERGLOW_LATENCY_USERNAME || null;
	const password = env.AFTERGLOW_LATENCY_PASSWORD || null;
	if (!interactive) {
		check(username && password, 'AFTERGLOW_LATENCY_USERNAME and AFTERGLOW_LATENCY_PASSWORD must be set for automated sign-in. Or run with --interactive to sign in manually in the browser.');
	}
	return { username, password };
}

async function runApiLane(options, { creds = {}, sessionToken = null, projectId = null, discoveredEndpoints = [], log = console.log } = {}) {
	const { apiBase, timeoutMs } = options;
	let activeToken = sessionToken;
	let activeProject = projectId;
	let createdSession = false;
	if (!activeToken) {
		check(creds.username && creds.password, 'API lane requires credentials or an active browser session.');
		const session = await signIn({ apiBase, ...creds, timeoutMs });
		activeToken = session.token;
		activeProject = session.projectId;
		createdSession = true;
	} else {
		log('  api lane: using session token from browser login');
	}
	try {
		let endpoints;
		let skipped = [];
		let truncated = 0;
		if (options.endpoints.length > 0) {
			endpoints = options.endpoints.map((path) => ({ method: 'GET', path }));
		} else if (discoveredEndpoints.length > 0) {
			log(`  api lane: measuring ${discoveredEndpoints.length} GET endpoints captured during page loads`);
			endpoints = discoveredEndpoints.slice(0, options.maxEndpoints);
			truncated = Math.max(0, discoveredEndpoints.length - options.maxEndpoints);
		} else {
			const discovered = discoverGetEndpoints(await fetchOpenApi({ apiBase, timeoutMs }), {
				include: options.endpointFilter,
				exclude: options.endpointExclude,
				max: options.maxEndpoints
			});
			endpoints = discovered.measurable;
			skipped = discovered.skipped;
			truncated = discovered.truncated;
		}
		check(endpoints.length > 0, 'No GET endpoints selected for the API lane.');
		// With credentials an expired token is renewed by signing in again; a browser-session token
		// cannot be renewed here (its refresh cookie lives in the closed browser profile).
		const renewedTokens = [];
		const refreshAuth =
			creds.username && creds.password
				? async () => {
						const session = await signIn({ apiBase, ...creds, timeoutMs });
						renewedTokens.push(session.token);
						return { token: session.token, projectId: session.projectId };
					}
				: null;
		let measured;
		try {
			measured = await measureEndpoints({
				apiBase,
				token: activeToken,
				projectId: activeProject,
				endpoints,
				samples: options.samples,
				levels: options.levels,
				rounds: options.rounds,
				timeoutMs,
				refreshAuth
			});
		} finally {
			for (const renewed of renewedTokens) await signOut({ apiBase, token: renewed, timeoutMs }).catch(() => {});
		}
		if (measured.aborted) log(`  api lane aborted (${measured.aborted.reason}, ${measured.aborted.stage}): the access token was rejected; samples after that point are not latency data`);
		let auth = null;
		if (!measured.aborted && creds.username && creds.password) {
			auth = await measureAuth({ apiBase, ...creds, samples: options.authSamples, probe: options.authProbe, timeoutMs });
		}
		return { endpoints: measured.perEndpoint, ramp: measured.ramp, auth, skipped, truncated, aborted: measured.aborted };
	} finally {
		if (createdSession && activeToken) {
			await signOut({ apiBase, token: activeToken, timeoutMs }).catch(() => {});
		}
	}
}

export async function runLatency(options, { env = process.env, log = console.log } = {}) {
	const target = assertTargetAllowed(options.target ?? '', { allowRemote: options.allowRemote });
	const apiBase = assertTargetAllowed(options.apiBase ?? '', { allowRemote: options.allowRemote });
	const fixtures = options.routeFixtures ? JSON.parse(await readFile(options.routeFixtures, 'utf8')) : {};
	const routes = planRoutes(listPageRoutes(options.routesDir), { fixtures, filter: options.routeFilter });
	log(`routes: ${routes.total} page routes, ${routes.measured.length} measured, ${routes.skipped.length} skipped`);
	if (options.dryRun) {
		for (const skip of routes.skipped) log(`  skip ${skip.pattern}: ${skip.reason}`);
		return { dryRun: true, routes };
	}
	const interactive = options.interactive;
	const creds = credentials(env, { interactive });

	const meta = { target, apiBase, lanes: options.lanes, passes: options.passes, levels: options.levels, samples: options.samples, rounds: options.rounds, authSamples: options.authSamples, interactive, nodeVersion: process.version, platform: process.platform };
	let browser = null;
	let api = null;
	let effectiveRoutes = routes;
	let browserAuthToken = null;
	let browserAuthProject = null;
	if (options.lanes.includes('browser')) {
		const executable = resolveChrome({ env: { ...env, AFTERGLOW_LATENCY_CHROME: options.chrome ?? env.AFTERGLOW_LATENCY_CHROME } });
		const pendingDynamic = routes.skipped.filter((s) => /dynamic route/.test(s.reason));
		log(`browser lane: ${routes.measured.length} routes x ${options.passes} passes (${pendingDynamic.length} dynamic routes eligible for link harvesting, headless=${!interactive})`);
		const result = await runBrowserLane({
			origin: target,
			username: creds.username,
			password: creds.password,
			routes: routes.measured,
			pendingDynamicRoutes: pendingDynamic,
			passes: options.passes,
			quietMs: options.quietMs,
			readyTimeoutMs: options.readyTimeoutMs,
			headless: !interactive,
			interactiveLogin: interactive,
			executable,
			onProgress: (p) => {
				if (p.message) log(`  ${p.message}`);
				else log(`  [pass ${p.pass}] ${p.pattern} -> ${p.status} ready=${p.ready_ms ?? '–'}ms`);
			}
		});
		browserAuthToken = result.token;
		browserAuthProject = result.projectId;
		// Keep browserAuthToken active so API lane can reuse the authenticated session without redundant login
		if (result.discoveredDynamic?.length > 0) {
			effectiveRoutes = harvestDynamicRoutes(routes, result.allHarvestedLinks);
			log(`  discovered ${result.discoveredDynamic.length} dynamic routes from on-page links:`);
			for (const d of result.discoveredDynamic) log(`    ${d.pattern} -> ${d.path}`);
		}
		browser = { login: result.login, visits: result.visits, discoveredDynamic: result.discoveredDynamic ?? [] };
	}
	const outDir = options.out ?? join('latency-reports', new Date().toISOString().replace(/[:.]/g, '-'));
	await mkdir(outDir, { recursive: true });

	const persistReport = async (label) => {
		const report = buildReport({ meta, routes: effectiveRoutes, browser, api, budgets: options.budgets });
		await writeFile(join(outDir, 'report.json'), `${JSON.stringify(report, null, 2)}\n`);
		await writeFile(join(outDir, 'report.md'), `${renderMarkdown(report)}\n`);
		if (label) log(`saved ${label} to ${join(outDir, 'report.md')}`);
		return report;
	};

	// Persist browser results immediately so a later API issue never discards browser data
	if (browser) await persistReport('interim browser report');

	if (options.lanes.includes('api')) {
		log('api lane');
		const capturedGetEndpoints = [];
		if (browser?.visits) {
			const seenPaths = new Set();
			for (const v of browser.visits) {
				for (const c of v.api) {
					if (c.method === 'GET' && c.path && !c.stream) {
						if (!seenPaths.has(c.path)) {
							seenPaths.add(c.path);
							capturedGetEndpoints.push({ method: 'GET', path: c.path });
						}
					}
				}
			}
		}
		try {
			api = await runApiLane(options, { creds, sessionToken: browserAuthToken, projectId: browserAuthProject, discoveredEndpoints: capturedGetEndpoints, log });
		} catch (error) {
			log(`  api lane failed: ${error.message} (browser results preserved)`);
			api = { error: error.message, endpoints: [], ramp: [], skipped: [] };
		}
	}
	let finalReport;
	try {
		finalReport = await persistReport('final report');
	} finally {
		if (!interactive && browserAuthToken) {
			await signOut({ apiBase, token: browserAuthToken, timeoutMs: options.timeoutMs }).catch(() => {});
		}
	}
	return { dryRun: false, report: finalReport, outDir };
}

async function main(argv = process.argv.slice(2)) {
	const options = parseOptions(argv);
	if (options.help) {
		process.stdout.write(USAGE);
		return 0;
	}
	check(options.target, '--target (or AFTERGLOW_LATENCY_TARGET) is required.');
	const result = await runLatency(options);
	if (result.dryRun) return 0;
	if (!result.report.budgets.passed) {
		for (const violation of result.report.budgets.violations) console.error(`FAIL: ${violation}`);
		return 1;
	}
	return 0;
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
	main().then(
		(code) => {
			process.exitCode = code;
		},
		(error) => {
			console.error(`latency: ${error.message}`);
			process.exitCode = 2;
		}
	);
}
