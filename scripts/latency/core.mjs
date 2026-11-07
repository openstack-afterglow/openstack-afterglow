// Shared primitives for the latency harness: statistics, SvelteKit route inventory and planning,
// URL redaction/templating, and the safety policy (target allow-list, read-only methods).
import { readdirSync } from 'node:fs';
import { join } from 'node:path';
import { isIP } from 'node:net';

export function check(condition, message) {
	if (!condition) throw new Error(message);
}

// ---------------------------------------------------------------- statistics

/** Linear-interpolation percentile (type 7, the numpy/Excel default) of an ascending array. */
export function percentile(sortedAscending, p) {
	const n = sortedAscending.length;
	if (n === 0) return null;
	if (n === 1) return sortedAscending[0];
	const rank = (Math.min(100, Math.max(0, p)) / 100) * (n - 1);
	const low = Math.floor(rank);
	const high = Math.ceil(rank);
	return sortedAscending[low] + (sortedAscending[high] - sortedAscending[low]) * (rank - low);
}

export function round(value, digits = 1) {
	if (typeof value !== 'number' || !Number.isFinite(value)) return null;
	const factor = 10 ** digits;
	return Math.round(value * factor) / factor;
}

/** count/min/mean/p50/p90/p95/p99/max over the finite numbers; `{count: 0}` when there are none. */
export function summarize(values, digits = 1) {
	const sorted = values.filter((v) => typeof v === 'number' && Number.isFinite(v)).sort((a, b) => a - b);
	if (sorted.length === 0) return { count: 0 };
	const sum = sorted.reduce((acc, v) => acc + v, 0);
	return {
		count: sorted.length,
		min: round(sorted[0], digits),
		mean: round(sum / sorted.length, digits),
		p50: round(percentile(sorted, 50), digits),
		p90: round(percentile(sorted, 90), digits),
		p95: round(percentile(sorted, 95), digits),
		p99: round(percentile(sorted, 99), digits),
		max: round(sorted[sorted.length - 1], digits)
	};
}

// ------------------------------------------------------------ route inventory

const PARAM_SEGMENT = /^\[(\[)?(\.\.\.)?([A-Za-z_]\w*)(?:=\w+)?\]\]?$/;

/**
 * Every `+page.svelte` under a SvelteKit routes directory, as a URL pattern.
 * Route groups `(name)` are not part of the URL. `[x]`, `[[x]]` and `[...x]` stay as patterns.
 */
export function listPageRoutes(routesDir) {
	const found = [];
	const walk = (dir, segments) => {
		const entries = readdirSync(dir, { withFileTypes: true });
		if (entries.some((entry) => entry.isFile() && entry.name === '+page.svelte')) {
			found.push({
				pattern: `/${segments.filter((segment) => !/^\(.*\)$/.test(segment)).join('/')}`,
				file: [...segments, '+page.svelte'].join('/')
			});
		}
		for (const entry of entries) {
			if (entry.isDirectory()) walk(join(dir, entry.name), [...segments, entry.name]);
		}
	};
	walk(routesDir, []);
	return found.sort((a, b) => a.pattern.localeCompare(b.pattern));
}

export function routeParams(pattern) {
	return pattern.split('/').filter(Boolean).flatMap((segment) => {
		const match = PARAM_SEGMENT.exec(segment);
		return match ? [{ name: match[3], optional: Boolean(match[1]), rest: Boolean(match[2]) }] : [];
	});
}

export const isDynamicRoute = (pattern) => routeParams(pattern).length > 0;

const escapeRegExp = (text) => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

/** Regular expression matching a concrete pathname for a route pattern. */
export function routeRegExp(pattern) {
	const segments = pattern.split('/').filter(Boolean);
	if (segments.length === 0) return /^\/$/;
	let source = '^';
	for (const segment of segments) {
		const match = PARAM_SEGMENT.exec(segment);
		if (!match) source += `/${escapeRegExp(segment)}`;
		else if (match[2]) source += '/.+';
		else if (match[1]) source += '(?:/[^/]+)?';
		else source += '/[^/]+';
	}
	return new RegExp(`${source}/?$`);
}

/**
 * Routes that cannot be measured by loading them, with the reason shown in the report.
 * Skipping is explicit, so measured + skipped always equals the inventory.
 */
export const UNMEASURABLE_ROUTES = new Map([
	['/logout', 'session-destructive: loading it signs the measuring session out'],
	['/auth/callback', 'needs an identity-provider callback state'],
	['/oauth/mcp/authorize', 'needs an OAuth authorization request'],
	['/oauth/claude/authorize', 'needs an OAuth authorization request']
]);

/**
 * Decide what each page route will load. Dynamic routes need an explicit concrete path from
 * `fixtures` (pattern -> path); a fixture that does not match its pattern is a configuration error.
 */
export function planRoutes(routes, { fixtures = {}, filter = null, unmeasurable = UNMEASURABLE_ROUTES } = {}) {
	const measured = [];
	const skipped = [];
	for (const route of routes) {
		if (filter && !filter.test(route.pattern)) {
			skipped.push({ pattern: route.pattern, reason: 'excluded by --route-filter' });
			continue;
		}
		if (unmeasurable.has(route.pattern)) {
			skipped.push({ pattern: route.pattern, reason: unmeasurable.get(route.pattern) });
			continue;
		}
		if (!isDynamicRoute(route.pattern)) {
			measured.push({ pattern: route.pattern, file: route.file, path: route.pattern });
			continue;
		}
		const concrete = fixtures[route.pattern];
		if (!concrete) {
			skipped.push({ pattern: route.pattern, reason: 'dynamic route without a --route-fixtures entry' });
			continue;
		}
		const pathname = new URL(concrete, 'http://fixture.invalid').pathname;
		check(routeRegExp(route.pattern).test(pathname), `Fixture for ${route.pattern} does not match that route: ${pathname}`);
		measured.push({ pattern: route.pattern, file: route.file, path: pathname });
	}
	check(measured.length + skipped.length === routes.length, 'Route accounting broke: measured + skipped must equal the inventory.');
	return { total: routes.length, measured, skipped };
}

/**
 * Matches discovered on-page links against unresolved dynamic routes and promotes matches to measured.
 * Leaves unresolvable dynamic routes in skipped with an updated descriptive reason.
 */
export function harvestDynamicRoutes(planned, discoveredLinks) {
	const linkSet = Array.isArray(discoveredLinks) ? new Set(discoveredLinks) : discoveredLinks;
	const newlyMeasured = [];
	const remainingSkipped = [];
	for (const item of planned.skipped) {
		if (!isDynamicRoute(item.pattern) || item.reason === 'excluded by --route-filter') {
			remainingSkipped.push(item);
			continue;
		}
		const regex = routeRegExp(item.pattern);
		let matched = null;
		for (const link of linkSet) {
			if (regex.test(link)) {
				matched = link;
				break;
			}
		}
		if (matched) {
			newlyMeasured.push({ pattern: item.pattern, file: item.file, path: matched, discovered: true });
		} else {
			remainingSkipped.push({ pattern: item.pattern, file: item.file, reason: 'dynamic route without fixture or on-page links' });
		}
	}
	const measured = [...planned.measured, ...newlyMeasured];
	check(measured.length + remainingSkipped.length === planned.total, 'Dynamic route harvesting broke route accounting.');
	return { total: planned.total, measured, skipped: remainingSkipped, newlyMeasured };
}

// ----------------------------------------------------------------- URL hygiene

const SENSITIVE_QUERY_KEY = /(^|[_-])(token|secret|password|passwd|key|signature|sig|code|authorization|auth|credential|session|jwt|state)($|[_-])/i;

/** Origin + path + query with credential-like values replaced; userinfo and fragments removed. */
export function redactUrl(raw) {
	let url;
	try {
		url = new URL(raw);
	} catch {
		return '[unparseable-url]';
	}
	url.username = '';
	url.password = '';
	url.hash = '';
	for (const key of [...url.searchParams.keys()]) {
		if (SENSITIVE_QUERY_KEY.test(key)) url.searchParams.set(key, '[redacted]');
	}
	return url.toString();
}

const OPAQUE_SEGMENT = [
	/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i,
	/^\d+$/,
	/^[0-9a-f]{16,}$/i,
	/^(?=.*\d)[A-Za-z0-9_-]{24,}$/
];

/** Aggregation key for a path: opaque identifiers become `:id`, so per-resource calls group together. */
export function templatePath(pathname) {
	return pathname
		.split('/')
		.map((segment) => (segment && OPAQUE_SEGMENT.some((re) => re.test(segment)) ? ':id' : segment))
		.join('/');
}

/** `METHOD /templated/path`; the query string is dropped because it can carry values the report must not hold. */
export function endpointKey(method, raw) {
	try {
		return `${method.toUpperCase()} ${templatePath(new URL(raw).pathname)}`;
	} catch {
		return `${method.toUpperCase()} [unparseable-url]`;
	}
}

// ---------------------------------------------------------------- safety policy

export function isLocalOrPrivateHost(hostname) {
	const host = hostname.replace(/^\[|\]$/g, '').toLowerCase();
	if (host === 'localhost' || host.endsWith('.localhost')) return true;
	const family = isIP(host);
	if (family === 4) {
		const [a, b] = host.split('.').map(Number);
		return a === 127 || a === 10 || (a === 172 && b >= 16 && b <= 31) || (a === 192 && b === 168) || (a === 169 && b === 254);
	}
	if (family === 6) return host === '::1' || /^f[cd]/.test(host) || host.startsWith('fe80:');
	return false;
}

/**
 * Parse a target origin. Loopback and private addresses are accepted; any other host needs its
 * exact origin in `allowRemote`, so a measurement cannot reach a public site by accident.
 */
export function assertTargetAllowed(raw, { allowRemote = [] } = {}) {
	let url;
	try {
		url = new URL(raw);
	} catch {
		throw new Error(`Target "${raw}" is not an absolute URL.`);
	}
	check(['http:', 'https:'].includes(url.protocol), 'Target must use http or https.');
	check(!url.username && !url.password, 'Target URL must not embed credentials; use environment variables.');
	if (!isLocalOrPrivateHost(url.hostname)) {
		const allowed = allowRemote.map((value) => new URL(value).origin);
		check(
			allowed.includes(url.origin),
			`Refusing ${url.origin}: not loopback/private. Pass --allow-remote ${url.origin} to acknowledge measuring that environment.`
		);
	}
	return url.origin;
}

// The harness reads. Its only writes are its own sign-in and sign-out, which create and remove the
// sessions it measures with; nothing else is mutated.
const READ_METHODS = new Set(['GET', 'HEAD']);
export const SESSION_WRITES = new Set(['POST /api/v1/auth/login', 'POST /api/v1/auth/logout']);

export function assertMethodAllowed(method, pathname) {
	const upper = method.toUpperCase();
	check(
		READ_METHODS.has(upper) || SESSION_WRITES.has(`${upper} ${pathname}`),
		`${upper} ${pathname} refused: the latency harness only issues GET/HEAD plus its own sign-in and sign-out.`
	);
}
