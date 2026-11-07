import assert from 'node:assert/strict';
import test from 'node:test';
import { buildReport, evaluateBudgets, renderMarkdown } from './report.mjs';

const meta = { target: 'http://127.0.0.1:1', apiBase: 'http://127.0.0.1:1', lanes: ['api'] };
const aborted = { reason: 'auth_rejected', stage: 'endpoints', endpoint: 'GET /api/v1/protected', measured_endpoints: 1 };
const api = {
	endpoints: [
		{ endpoint: 'GET /api/v1/fast', samples: 2, status_counts: { 200: 2 }, ttfb_ms: { p50: 5 }, server_dur_ms: { p50: 4 }, total_ms: { count: 2, p50: 6, p90: 7, p95: 7, max: 7 } },
		{ endpoint: 'GET /api/v1/protected', samples: 2, status_counts: { 401: 2 }, ttfb_ms: { count: 0 }, server_dur_ms: { count: 0 }, total_ms: { count: 0 }, invalid: 'auth_rejected' }
	],
	ramp: [{ concurrency: 3, rounds: 1, requests: 3, status_counts: { 401: 3 }, invalid: 'auth_rejected' }],
	skipped: [],
	truncated: 0,
	auth: null,
	aborted
};

test('an aborted API lane is announced and its 401 rows are marked INVALID, never shown as latency', () => {
	const markdown = renderMarkdown(buildReport({ meta, routes: { total: 0, measured: [], skipped: [] }, browser: null, api, budgets: {} }));
	assert.match(markdown, /API lane aborted \(auth_rejected, endpoints\)/);
	assert.match(markdown, /rejected \(HTTP 401\) at `GET \/api\/v1\/protected`/);
	assert.match(markdown, /401×2 \(INVALID\)/);
	const rampRow = markdown.split('\n').find((line) => line.startsWith('| 3 |'));
	assert.match(rampRow, /INVALID/);
});

test('an API p95 budget cannot pass when the API lane aborted', () => {
	const result = evaluateBudgets({ budgets: { apiP95Ms: 1000 }, browser: null, api });
	assert.equal(result.passed, false);
	assert.match(result.violations.join('\n'), /api lane aborted/);
});

test('without a budget an aborted lane does not fail the run by itself', () => {
	assert.equal(evaluateBudgets({ budgets: {}, browser: null, api }).passed, true);
});
