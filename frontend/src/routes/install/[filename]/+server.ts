import { env } from 'node:process';
import { error } from '@sveltejs/kit';
import type { RequestHandler } from './$types';

export const GET: RequestHandler = async ({ params, request }) => {
	const filename = params.filename;
	if (filename !== 'lumen.sh' && filename !== 'lumen.ps1') error(404);

	const headers = new Headers();
	const etag = request.headers.get('if-none-match');
	if (etag !== null) headers.set('if-none-match', etag);

	let upstream: Response;
	try {
		// Never derive the upstream from the browser origin or forward its credentials.
		const url = new URL(`/api/v1/install/${filename}`, env.BACKEND_INTERNAL_ORIGIN || 'http://127.0.0.1:8000');
		upstream = await fetch(url, { method: request.method, headers, redirect: 'error', signal: AbortSignal.timeout(5000) });
	} catch {
		error(502, 'Lumen installer service unavailable');
	}
	if (upstream.status !== 304 && (upstream.status !== 200 || upstream.headers.get('content-type') !== 'text/plain; charset=utf-8')) {
		await upstream.body?.cancel();
		error(502, 'Lumen installer service unavailable');
	}

	const responseHeaders = new Headers({ 'Cache-Control': 'no-cache', 'X-Content-Type-Options': 'nosniff' });
	for (const name of ['content-type', 'etag']) {
		const value = upstream.headers.get(name);
		if (value !== null) responseHeaders.set(name, value);
	}
	return new Response(upstream.body, { status: upstream.status, headers: responseHeaders });
};

export const HEAD = GET;
