// Report assembly: a redacted JSON record of everything measured, plus a Markdown rendering for reading.
import { round, summarize } from './core.mjs';

const count = (rows, predicate) => rows.filter(predicate).length;

function statusTally(values) {
	const tally = {};
	for (const value of values) tally[String(value)] = (tally[String(value)] ?? 0) + 1;
	return tally;
}

/** Aggregate browser visits: readiness by cache state, slowest pages, and API calls grouped by endpoint. */
export function summarizeBrowser({ login, visits }) {
	const byCache = (cache, key) => visits.filter((v) => v.cache === cache && v[key] !== null && v[key] !== undefined).map((v) => v[key]);
	const endpoints = new Map();
	for (const visit of visits) {
		for (const call of visit.api) {
			const entry = endpoints.get(call.endpoint) ?? { calls: 0, pages: new Set(), statuses: [], ttfb: [], total: [], server_dur: [], download: [], pending: 0, streams: 0 };
			entry.calls++;
			entry.pages.add(visit.pattern);
			entry.statuses.push(call.status);
			if (call.stream) entry.streams++;
			else if (call.pending) entry.pending++;
			if (call.ttfb_ms !== null) entry.ttfb.push(call.ttfb_ms);
			if (call.total_ms !== null && !call.stream) entry.total.push(call.total_ms);
			if (call.server_dur_ms !== null && call.server_dur_ms !== undefined) entry.server_dur.push(call.server_dur_ms);
			if (call.download_ms !== null && call.download_ms !== undefined) entry.download.push(call.download_ms);
			endpoints.set(call.endpoint, entry);
		}
	}
	const tele = new Map();
	for (const visit of visits) {
		for (const call of visit.telemetry ?? []) {
			const entry = tele.get(call.endpoint) ?? { calls: 0, statuses: [], total: [] };
			entry.calls++;
			entry.statuses.push(call.status);
			if (call.total_ms !== null) entry.total.push(call.total_ms);
			tele.set(call.endpoint, entry);
		}
	}
	return {
		login_ms: login.login_ms,
		visits: visits.length,
		status: statusTally(visits.map((v) => v.status)),
		ready_ms: { cold: summarize(byCache('cold', 'ready_ms')), warm: summarize(byCache('warm', 'ready_ms')) },
		load_ms: { cold: summarize(byCache('cold', 'load_ms')), warm: summarize(byCache('warm', 'load_ms')) },
		not_ready: visits.filter((v) => v.status === 'not_ready').map((v) => ({ pattern: v.pattern, pass: v.pass, api_pending_at_end: v.api_pending_at_end })),
		failures: visits.filter((v) => v.status === 'error').map((v) => ({ pattern: v.pattern, pass: v.pass, error: v.error })),
		slowest_pages: visits
			.filter((v) => v.ready_ms !== null)
			.sort((a, b) => b.ready_ms - a.ready_ms)
			.slice(0, 10)
			.map((v) => ({ pattern: v.pattern, pass: v.pass, cache: v.cache, status: v.status, ready_ms: v.ready_ms, api_calls: v.api.length })),
		api_by_endpoint: [...endpoints.entries()]
			.map(([endpoint, e]) => ({
				endpoint,
				calls: e.calls,
				pages: e.pages.size,
				status: statusTally(e.statuses),
				ttfb_ms: summarize(e.ttfb),
				total_ms: summarize(e.total),
				server_dur_ms: summarize(e.server_dur),
				download_ms: summarize(e.download),
				streams: e.streams,
				pending: e.pending
			}))
			.sort((a, b) => (b.total_ms.p95 ?? 0) - (a.total_ms.p95 ?? 0)),
		telemetry_by_endpoint: [...tele.entries()].map(([endpoint, e]) => ({
			endpoint,
			calls: e.calls,
			status: statusTally(e.statuses),
			total_ms: summarize(e.total)
		}))
	};
}

/** Budgets are opt-in; a violated budget fails the run. Latency gates are never enabled by default. */
export function evaluateBudgets({ budgets, browser, api }) {
	const violations = [];
	if (budgets.readyP95Ms !== undefined && browser) {
		const p95 = browser.ready_ms.cold.p95 ?? null;
		if (p95 !== null && p95 > budgets.readyP95Ms) violations.push(`cold page ready p95 ${p95}ms > ${budgets.readyP95Ms}ms`);
	}
	if (budgets.apiP95Ms !== undefined) {
		const worst = [
			...(browser?.api_by_endpoint ?? []).map((e) => ({ source: 'browser', endpoint: e.endpoint, p95: e.total_ms.p95 })),
			...(api?.endpoints ?? []).map((e) => ({ source: 'api', endpoint: e.endpoint, p95: e.total_ms.p95 }))
		].filter((row) => typeof row.p95 === 'number' && row.p95 > budgets.apiP95Ms);
		for (const row of worst) violations.push(`${row.source} ${row.endpoint} p95 ${row.p95}ms > ${budgets.apiP95Ms}ms`);
		if (api?.aborted) violations.push(`api lane aborted (${api.aborted.reason}, ${api.aborted.stage}): API budget was not fully evaluated`);
	}
	return { passed: violations.length === 0, violations };
}

export function buildReport({ meta, routes, browser, api, budgets }) {
	const summary = { browser: browser ? summarizeBrowser(browser) : null, api: api ?? null };
	return {
		schema_version: 1,
		generated_at: new Date().toISOString(),
		meta,
		routes: {
			total: routes.total,
			measured: routes.measured.length,
			skipped: routes.skipped.length,
			measured_patterns: routes.measured.map((r) => r.pattern),
			skipped_detail: routes.skipped
		},
		...summary,
		budgets: evaluateBudgets({ budgets, browser: summary.browser, api: summary.api })
	};
}

const cell = (value) => (value === null || value === undefined ? '–' : String(value).replace(/\|/g, '\\|'));
const row = (values) => `| ${values.map(cell).join(' | ')} |`;
const table = (header, rows) => [row(header), row(header.map(() => '---')), ...rows.map(row)].join('\n');
const dist = (s) => (s && s.count ? [s.count, s.p50, s.p90, s.p95, s.max] : [0, null, null, null, null]);

export function renderMarkdown(report) {
	const lines = [];
	lines.push(`# Latency report`, '', `- generated: ${report.generated_at}`, `- target: ${cell(report.meta.target)}`, `- api base: ${cell(report.meta.apiBase)}`, `- lanes: ${report.meta.lanes.join(', ')}`, '');
	lines.push('## Routes', '', table(['total', 'measured', 'skipped'], [[report.routes.total, report.routes.measured, report.routes.skipped]]), '');
	if (report.routes.skipped_detail.length) {
		lines.push(table(['skipped route', 'reason'], report.routes.skipped_detail.map((s) => [`\`${s.pattern}\``, s.reason])), '');
	}
	if (report.browser) {
		const b = report.browser;
		const loginDesc = b.login?.interactive
			? `Interactive sign-in: session detected after ${cell(b.login_ms)} ms.`
			: `Sign-in (POST /api/v1/auth/login): ${cell(b.login_ms)} ms.`;
		lines.push('## Page load (browser)', '', `${loginDesc} Visits: ${b.visits}. Status: ${Object.entries(b.status).map(([k, v]) => `${k}=${v}`).join(', ')}.`, '');
		lines.push(
			table(
				['ready (ms)', 'n', 'p50', 'p90', 'p95', 'max'],
				[['cold', ...dist(b.ready_ms.cold)], ['warm', ...dist(b.ready_ms.warm)]]
			),
			''
		);
		lines.push(table(['load event (ms)', 'n', 'p50', 'p90', 'p95', 'max'], [['cold', ...dist(b.load_ms.cold)], ['warm', ...dist(b.load_ms.warm)]]), '');
		if (b.slowest_pages.length) {
			lines.push('### Slowest pages', '', table(['route', 'pass', 'cache', 'status', 'ready ms', 'API calls'], b.slowest_pages.map((p) => [`\`${p.pattern}\``, p.pass, p.cache, p.status, p.ready_ms, p.api_calls])), '');
		}
		if (b.not_ready.length) lines.push('### Not ready (still busy at timeout)', '', table(['route', 'pass', 'API pending'], b.not_ready.map((p) => [`\`${p.pattern}\``, p.pass, p.api_pending_at_end])), '');
		if (b.failures.length) lines.push('### Navigation failures', '', table(['route', 'pass', 'error'], b.failures.map((f) => [`\`${f.pattern}\``, f.pass, f.error])), '');
		lines.push('### API calls made by pages', '', table(
			['endpoint', 'calls', 'pages', 'statuses', 'TTFB p50', 'server dur p50', 'download p50', 'total p50', 'total p95', 'total max', 'streams', 'pending'],
			b.api_by_endpoint.map((e) => [
				`\`${e.endpoint}\``,
				e.calls,
				e.pages,
				Object.entries(e.status).map(([k, v]) => `${k}×${v}`).join(' '),
				e.ttfb_ms.p50,
				e.server_dur_ms.p50,
				e.download_ms.p50,
				e.total_ms.p50,
				e.total_ms.p95,
				e.total_ms.max,
				e.streams,
				e.pending
			])
		), '');
		if (b.telemetry_by_endpoint && b.telemetry_by_endpoint.length > 0) {
			lines.push('### Background telemetry (excluded from page readiness)', '', table(
				['endpoint', 'calls', 'statuses', 'total p50', 'total p95'],
				b.telemetry_by_endpoint.map((t) => [
					`\`${t.endpoint}\``,
					t.calls,
					Object.entries(t.status).map(([k, v]) => `${k}×${v}`).join(' '),
					t.total_ms.p50,
					t.total_ms.p95
				])
			), '');
		}
	}
	if (report.api) {
		const a = report.api;
		if (a.error) {
			lines.push('## API (direct)', '', `API lane failed: ${a.error}`, '');
		} else {
			lines.push('## API (direct)', '', `Endpoints measured: ${a.endpoints?.length ?? 0}; skipped: ${a.skipped?.length ?? 0}${a.truncated ? `; truncated: ${a.truncated}` : ''}.`, '');
			if (a.aborted) {
				lines.push(
					`> **API lane aborted (${a.aborted.reason}, ${a.aborted.stage}).** The access token was rejected (HTTP 401)${a.aborted.endpoint ? ` at \`${a.aborted.endpoint}\`` : ''} after ${a.aborted.measured_endpoints} validly measured endpoint(s). 401 responses are not latency samples; rows marked INVALID and everything after them were not measured. Re-run while the session is fresh.`,
					''
				);
			}
			if (a.auth) {
				lines.push(
					table(['sign-in (ms)', 'n', 'p50', 'p90', 'p95', 'max'], [['login only', ...dist(a.auth.login_ms)], [`login + GET ${a.auth.probe?.endpoint?.slice(4) ?? '–'}`, ...dist(a.auth.login_plus_probe_ms)]]),
					''
				);
			} else {
				lines.push('Sign-in measurement: skipped (used interactive browser session token).', '');
			}
			if (a.endpoints?.length) {
				lines.push(
					'### Per endpoint (sequential, warm token)',
					'',
					table(
						['endpoint', 'n', 'statuses', 'TTFB p50', 'server dur p50', 'total p50', 'total p90', 'total p95', 'total max'],
						a.endpoints.map((e) => [
							`\`${e.endpoint}\``,
							e.samples,
							`${Object.entries(e.status_counts).map(([k, v]) => `${k}×${v}`).join(' ')}${e.invalid ? ' (INVALID)' : ''}`,
							e.ttfb_ms.p50,
							e.server_dur_ms?.p50,
							e.total_ms.p50,
							e.total_ms.p90,
							e.total_ms.p95,
							e.total_ms.max
						])
					),
					''
				);
			}
			if (a.ramp?.length) {
				lines.push(
					'### Concurrency ramp',
					'',
					table(
						['concurrency', 'rounds', 'requests', 'statuses', 'request p50', 'request p95', 'batch wall p50', 'batch wall p95', 'batch wall max', 'throughput (req/s)'],
						a.ramp.map((r) =>
							r.invalid
								? [r.concurrency, r.rounds, r.requests, Object.entries(r.status_counts).map(([k, v]) => `${k}×${v}`).join(' '), 'INVALID', 'INVALID', 'INVALID', 'INVALID', 'INVALID', 'INVALID']
								: [r.concurrency, r.rounds, r.requests, Object.entries(r.status_counts).map(([k, v]) => `${k}×${v}`).join(' '), r.request_ms.p50, r.request_ms.p95, r.batch_wall_ms.p50, r.batch_wall_ms.p95, r.batch_wall_ms.max, r.throughput_rps]
						)
					),
					''
				);
			}
		}
	}
	lines.push('## Budgets', '', report.budgets.passed ? 'No budget configured or none violated.' : report.budgets.violations.map((v) => `- FAIL: ${v}`).join('\n'), '');
	return lines.join('\n');
}
