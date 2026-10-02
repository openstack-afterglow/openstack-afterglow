import { randomUUID } from 'node:crypto';
import { check, poll, required, withCleanup } from './service-verify-http.mjs';

export function parseJournal(text, runId, lastSeq) {
	const events = text.split(/\r?\n\r?\n/).flatMap((block) => {
		const data = block.split(/\r?\n/).filter((line) => line.startsWith('data:')).map((line) => line.slice(5).trimStart()).join('\n');
		if (!data) return [];
		try { return [JSON.parse(data)]; } catch { throw new Error('Lumen journal returned malformed SSE data.'); }
	});
	check(events.every((event, index) => event.run_id === runId && event.seq === index + 1), 'Lumen journal has a foreign run, gap or duplicate sequence.');
	check(events.at(-1)?.seq === lastSeq && events.at(-1)?.type === 'run.completed', 'Lumen journal does not reconcile with the completed run.');
	return events;
}

export async function verifyLumen(client, { env, exercise }) {
	const models = await client.request('/v1/chat/models');
	check(Array.isArray(models), 'Lumen did not return a native model catalogue.');
	if (!exercise) return ['authenticated model catalogue; connection-only (worker/provider not exercised)'];
	const modelId = required(env, 'LUMEN_SMOKE_MODEL_ID');
	const model = models.find((row) => [String(row.id), row.model_name, row.api_model_name].includes(modelId));
	check(model, 'LUMEN_SMOKE_MODEL_ID is not an active model in the authenticated catalogue.');
	// Check usage authority before starting a potentially billable operation.
	await client.request('/v1/usage/records?limit=1');
	const idempotencyKey = randomUUID();
	const json = {
		model_id: model.model_name,
		parts: [{ type: 'text', text: env.LUMEN_SMOKE_PROMPT || 'Reply exactly LUMEN_VERIFY_OK.' }],
		features: { memory: false, tool_policy: { mode: 'none' } }
	};
	const options = { method: 'POST', json, headers: { 'Idempotency-Key': idempotencyKey }, expected: [202] };
	let runId;
	let terminal = false;
	return withCleanup(async () => {
		const admitted = await client.request('/v1/temp-completions', options);
		check(typeof admitted.run_id === 'string' && admitted.temp_thread_id, 'Lumen admission did not return a temporary durable run.');
		runId = admitted.run_id;
		const replayed = await client.request('/v1/temp-completions', options);
		check(replayed.run_id === runId, 'Lumen idempotent admission created a second run.');
		const runPath = `/v1/runs/${encodeURIComponent(runId)}`;
		const run = await poll(() => client.request(runPath), (value) => value.terminal === true, { label: 'Lumen worker completion' });
		terminal = true;
		check(run.status === 'completed', `Lumen worker reached ${run.status}, not completed. No provider fallback was attempted.`);
		const events = parseJournal(await client.request(`${runPath}/events?after_seq=0`, { format: 'text' }), runId, run.last_seq);
		// Temporary runs emit text deltas; part.completed is conversation-only.
		const deltas = events.filter((event) => event.type === 'part.delta' && event.payload?.part_type === 'text').map((event) => event.payload.delta);
		check(deltas.every((delta) => typeof delta === 'string'), 'Lumen text delta has an invalid payload.');
		const text = deltas.join('');
		check(text.trim(), 'Completed Lumen run has no journal text output.');
		if (env.LUMEN_SMOKE_EXPECT_TEXT) check(text.includes(env.LUMEN_SMOKE_EXPECT_TEXT), 'Lumen output does not match the explicitly configured expected text.');
		const usage = events.findLast((event) => event.type === 'usage.updated')?.payload;
		check(usage && Number.isInteger(usage.prompt_tokens) && Number.isInteger(usage.completion_tokens), 'Lumen journal has no token accounting.');
		let before;
		let record;
		const seen = new Set();
		do {
			const page = await client.request(`/v1/usage/records?limit=100${before ? `&before_id=${before}` : ''}`);
			check(Array.isArray(page.records), 'Lumen usage page is invalid.');
			record = page.records.find((row) => row.run_id === runId);
			before = page.next_before_id;
			if (before) {
				check(Number.isInteger(before) && before > 0 && !seen.has(before), 'Lumen usage cursor did not progress.');
				seen.add(before);
			}
		} while (!record && before);
		check(record && record.prompt_tokens === usage.prompt_tokens && record.completion_tokens === usage.completion_tokens && record.total_tokens === usage.prompt_tokens + usage.completion_tokens,
			'Lumen run-attributed ledger does not reconcile with journal usage.');
		const history = await client.request(`/v1/temp-threads/${encodeURIComponent(admitted.temp_thread_id)}`);
		const savedText = history.public_history?.filter((message) => message.role === 'assistant').flatMap((message) => message.parts ?? []).filter((part) => part.type === 'text').map((part) => part.text).join('');
		check(savedText === text && history.latest_run?.run_id === runId && history.active_run === null, 'Lumen temporary history did not reconcile with the completed run.');
		return [`native admission/idempotency → worker completed → ${events.length} contiguous journal events → history/usage reconciled (${record.total_tokens} tokens)`,
			`run ${runId}: journal/ledger retained under service retention; provider authenticity is determined by the configured upstream`];
	}, async () => {
		if (runId && !terminal) {
			await client.request(`/v1/runs/${encodeURIComponent(runId)}/cancel`, { method: 'POST' });
			await poll(() => client.request(`/v1/runs/${encodeURIComponent(runId)}`), (value) => value.terminal === true, { label: 'Lumen cancellation' });
		}
	});
}
