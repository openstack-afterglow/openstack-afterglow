// Needs a local Chrome/Chromium (AFTERGLOW_LATENCY_CHROME or a standard install). Run via `npm run test:latency`.
import { describe, it, before, after } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { setTimeout as delay } from 'node:timers/promises';
import { CdpConnection, MeasuredPage, launchChrome, resolveChrome, runBrowserLane } from './browser-lane.mjs';

const PAGES = {
	'/login': `<!doctype html><title>login</title>
<form class="login-form"><input id="login-username"><input id="login-password" type="password"><button type="submit">Sign in</button></form>
<script>
document.querySelector('form.login-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const res = await fetch('/api/v1/auth/login', { method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ username: document.getElementById('login-username').value, password: document.getElementById('login-password').value }) });
  if (!res.ok) { document.body.append('rejected'); return; }
  sessionStorage.setItem('afterglow_auth', JSON.stringify({ token: (await res.json()).token }));
  location.href = '/app';
});
</script>`,
	'/app': `<!doctype html><title>app</title><main><div id="out">loading</div><a href="/items/item-42">item 42</a></main>
<script>
setTimeout(async () => {
  const res = await fetch('/api/v1/late');
  document.getElementById('out').textContent = 'loaded ' + res.status;
}, 100);
</script>`,
	'/hang': `<!doctype html><title>hang</title><main>polling</main>
<script>setInterval(() => fetch('/api/v1/poll').catch(() => {}), 100);</script>`,
	'/redirect': `<!doctype html><script>location.replace('/login');</script>`,
	'/blank': ``,
	'/broken-api': `<!doctype html><title>broken</title><main>content</main>
<script>fetch('/api/v1/fail').catch(() => {});</script>`,
	'/telemetry-page': `<!doctype html><title>telemetry</title><main>content</main>
<script>
setTimeout(() => {
  fetch('/api/v1/activity/experience-events', { method: 'POST', body: '{}' }).catch(() => {});
}, 50);
</script>`,
	'/items/item-42': `<!doctype html><title>detail</title><main>item 42 details</main>`
};

let site;
let origin;
let chrome;
let cdp;
let page;

before(async () => {
	site = http.createServer(async (req, res) => {
		for await (const _chunk of req) {
			// drain request bodies
		}
		const url = new URL(req.url, 'http://fixture.invalid');
		if (req.method === 'POST' && url.pathname === '/api/v1/auth/login') {
			await delay(300);
			res.writeHead(200, { 'content-type': 'application/json' });
			return res.end(JSON.stringify({ token: 'fixture-token' }));
		}
		if (req.method === 'GET' && url.pathname === '/api/v1/late') {
			await delay(400);
			res.setHeader('server-timing', 'app;dur=385.2');
			res.writeHead(200, { 'content-type': 'application/json' });
			return res.end('{"ok":true}');
		}
		if (req.method === 'POST' && url.pathname === '/api/v1/activity/experience-events') {
			await delay(600);
			res.writeHead(200, { 'content-type': 'application/json' });
			return res.end('{"schema_version":2,"accepted":1}');
		}
		if (req.method === 'GET' && url.pathname === '/api/v1/poll') {
			res.writeHead(200, { 'content-type': 'application/json' });
			return res.end('{}');
		}
		if (req.method === 'GET' && url.pathname === '/api/v1/fail') {
			res.writeHead(500, { 'content-type': 'application/json' });
			return res.end('{}');
		}
		if (req.method === 'GET' && PAGES[url.pathname] !== undefined) {
			res.writeHead(200, { 'content-type': 'text/html; charset=utf-8' });
			return res.end(PAGES[url.pathname]);
		}
		res.writeHead(404);
		res.end();
	});
	await new Promise((resolve) => site.listen(0, '127.0.0.1', resolve));
	origin = `http://127.0.0.1:${site.address().port}`;
	chrome = await launchChrome(resolveChrome());
	cdp = await new CdpConnection(chrome.wsUrl).open();
	page = await MeasuredPage.open(cdp);
});

after(async () => {
	cdp?.close();
	await chrome?.close();
	await new Promise((resolve) => site.close(resolve));
});

describe('page readiness', () => {
	it('waits for the API calls a page makes before calling it ready', async () => {
		const visit = await page.navigate(`${origin}/app`, { timeoutMs: 10000, quietMs: 300 });
		assert.equal(visit.status, 'ok');
		assert.equal(visit.final_path, '/app');
		assert.ok(visit.ready_ms >= 450, `ready after ${visit.ready_ms}ms; the page's API call takes ~500ms`);
		const late = visit.api.find((call) => call.endpoint === 'GET /api/v1/late');
		assert.ok(late, 'the page API call is recorded');
		assert.equal(late.status, 200);
		assert.ok(late.total_ms >= 350, `API total ${late.total_ms}ms`);
		assert.ok(late.ttfb_ms <= late.total_ms);
	});

	it('reports a page that keeps polling as not ready, with its pending calls', async () => {
		const visit = await page.navigate(`${origin}/hang`, { timeoutMs: 1500, quietMs: 300 });
		assert.equal(visit.status, 'not_ready');
		assert.equal(visit.ready, false);
		assert.equal(visit.ready_ms, null);
		assert.ok(visit.api.length >= 3, `expected repeated polls, saw ${visit.api.length}`);
	});

	it('reports a client-side redirect instead of treating the destination as the page', async () => {
		const visit = await page.navigate(`${origin}/redirect`, { timeoutMs: 10000, quietMs: 200 });
		assert.equal(visit.status, 'redirected');
		assert.equal(visit.final_path, '/login');
	});

	it('flags a page with no rendered text', async () => {
		const visit = await page.navigate(`${origin}/blank`, { timeoutMs: 10000, quietMs: 200 });
		assert.equal(visit.status, 'blank');
		assert.equal(visit.body_chars, 0);
	});

	it('keeps a failing API call visible on the page record', async () => {
		const visit = await page.navigate(`${origin}/broken-api`, { timeoutMs: 10000, quietMs: 200 });
		assert.equal(visit.status, 'ok');
		assert.deepEqual(visit.api.map((call) => [call.endpoint, call.status]), [['GET /api/v1/fail', 500]]);
	});

	it('excludes background telemetry from page readiness and records it under telemetry', async () => {
		// Telemetry endpoint delays 600ms; page readiness must settle within ~300ms without waiting for telemetry
		const visit = await page.navigate(`${origin}/telemetry-page`, { timeoutMs: 5000, quietMs: 200 });
		assert.equal(visit.status, 'ok');
		assert.ok(visit.ready_ms < 500, `ready_ms ${visit.ready_ms}ms must not wait for the 600ms telemetry flush`);
		assert.equal(visit.api.length, 0, 'telemetry must not appear in page-critical api list');
		assert.equal(visit.telemetry.length, 1, 'telemetry request must be recorded under telemetry bucket');
		assert.equal(visit.telemetry[0].endpoint, 'POST /api/v1/activity/experience-events');
	});

	it('records server_dur_ms and download_ms on page API calls', async () => {
		const visit = await page.navigate(`${origin}/app`, { timeoutMs: 10000, quietMs: 200 });
		const late = visit.api.find((call) => call.endpoint === 'GET /api/v1/late');
		assert.ok(late);
		assert.equal(late.server_dur_ms, 385.2);
		assert.equal(typeof late.download_ms, 'number');
		assert.ok(late.download_ms >= 0);
	});
});

describe('signed-in visit plan', () => {
	it('signs in, visits routes, and automatically harvests dynamic routes from on-page links', async () => {
		const result = await runBrowserLane({
			origin,
			username: 'fixture-user',
			password: 'fixture-pass',
			routes: [{ pattern: '/app', path: '/app' }, { pattern: '/broken-api', path: '/broken-api' }],
			pendingDynamicRoutes: [{ pattern: '/items/[id]', path: null, reason: 'dynamic' }],
			passes: 2,
			quietMs: 200,
			readyTimeoutMs: 10000,
			executable: resolveChrome()
		});
		assert.ok(result.login.login_ms >= 250, `login measured ${result.login.login_ms}ms`);
		assert.equal(result.login.status, 200);
		assert.equal(result.token, 'fixture-token');
		// /app contains <a href="/items/item-42">, matching /items/[id]
		assert.equal(result.discoveredDynamic.length, 1);
		assert.equal(result.discoveredDynamic[0].pattern, '/items/[id]');
		assert.equal(result.discoveredDynamic[0].path, '/items/item-42');
		// Discovered route was visited in pass 1 and pass 2
		const itemVisits = result.visits.filter((v) => v.pattern === '/items/[id]');
		assert.equal(itemVisits.length, 2);
		assert.equal(itemVisits[0].pass, 1);
		assert.equal(itemVisits[1].pass, 2);
	});
});
