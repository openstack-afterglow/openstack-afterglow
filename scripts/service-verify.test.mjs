import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { once } from 'node:events';
import { test } from 'node:test';
import { createClient, serviceOrigin, withCleanup } from './service-verify-http.mjs';
import { parseJournal } from './service-verify-lumen.mjs';

function journal(events) {
	return events.map((event) => `data: ${JSON.stringify(event)}\n\n`).join('');
}

test('journal acceptance rejects missing, duplicate, foreign and nonterminal results', () => {
	const started = { run_id: 'owned-run', seq: 1, type: 'run.started' };
	const completed = { run_id: 'owned-run', seq: 2, type: 'run.completed' };
	assert.deepEqual(parseJournal(journal([started, completed]), 'owned-run', 2), [started, completed]);
	for (const events of [
		[started], [started, started, completed],
		[started, { ...completed, seq: 3 }],
		[started, { ...completed, run_id: 'foreign-run' }],
		[started, { ...completed, type: 'run.failed' }]
	]) assert.throws(() => parseJournal(journal(events), 'owned-run', 2));
	assert.throws(() => parseJournal('data: not-json\n\n', 'owned-run', 2), /malformed SSE/);
});

test('cleanup runs on failure and cannot turn either failure into success', async () => {
	let cleaned = false;
	await assert.rejects(withCleanup(async () => { throw new Error('digest mismatch'); }, async () => { cleaned = true; }), /digest mismatch/);
	assert.equal(cleaned, true);
	await assert.rejects(withCleanup(async () => 'verified', async () => { throw new Error('resource not removed'); }), /cleanup failed: resource not removed/);
	await assert.rejects(withCleanup(async () => { throw new Error('digest mismatch'); }, async () => { throw new Error('resource not removed'); }), /digest mismatch; cleanup failed: resource not removed/);
});

test('manual endpoint cannot embed credentials or override the service path with a query', () => {
	assert.equal(serviceOrigin('https://service.example/v1/'), 'https://service.example');
	for (const url of ['https://user:secret@service.example', 'https://service.example?token=secret', 'https://service.example#secret', 'file:///tmp/key', 'https://service.example/api/v1/chat']) {
		assert.throws(() => serviceOrigin(url));
	}
});

test('HTTP verifier fails on upstream errors without leaking response credentials or following redirects', async (t) => {
	let redirected = false;
	const server = createServer((request, response) => {
		if (request.url === '/v1/redirect') {
			response.writeHead(302, { Location: '/v1/credential-sink' }).end();
		} else if (request.url === '/v1/credential-sink') {
			redirected = true;
			response.end('{}');
		} else {
			response.writeHead(503, { 'Content-Type': 'application/json' }).end(JSON.stringify({ secret: 'upstream-private-key-sentinel' }));
		}
	});
	server.listen(0, '127.0.0.1');
	await once(server, 'listening');
	t.after(() => { server.closeAllConnections(); server.close(); });
	const client = createClient({ url: `http://127.0.0.1:${server.address().port}`, headers: { 'X-Auth-Token': 'private-caller-token' } });
	await assert.rejects(client.request('/v1/unavailable'), (error) => {
		assert.match(error.message, /HTTP 503/);
		assert.doesNotMatch(error.message, /upstream-private-key-sentinel|private-caller-token/);
		return true;
	});
	await assert.rejects(client.request('/v1/redirect'), /redirects are not followed/);
	assert.equal(redirected, false);
});
