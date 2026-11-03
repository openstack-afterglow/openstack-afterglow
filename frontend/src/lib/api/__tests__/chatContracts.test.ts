// @vitest-environment node
import { describe, expect, it } from 'vitest';
import {
	ChatContractError,
	MAX_CANONICAL_CHAT_PARTS,
	parseChatPartsForDisplay,
	parseChatPartsStrict,
	parseChatRunEvent,
	parseContextState
} from '../chatContracts';

describe('portable source and Pi progress contracts', () => {
	const base = { event_id: 'run-1:1', run_id: 'run-1', seq: 1, created_at: '2026-11-02T00:00:00Z' };
	it('parses immediate registered sources and preserves server-issued provenance', () => {
		const citation = { type: 'citation', citation_id: 'c1', source_kind: 'tool_result', source_id: 's1', url: 'https://console.example/lumen/sources/runs/run-1/c1', observed_at: base.created_at, provenance: { tool_name: 'read' } };
		expect(parseChatRunEvent({ ...base, type: 'source.registered', payload: { message_id: 'm1', citation } })).toMatchObject({ type: 'source.registered', payload: { citation } });
		expect(() => parseChatRunEvent({ ...base, type: 'source.registered', payload: { message_id: 'm1', citation: { type: 'text', text: 'not evidence' } } })).toThrow(ChatContractError);
	});
	it.each([null, ''])('accepts native nullable citation metadata (%s) without losing its locator', (metadata) => {
		const citation = { type: 'citation', citation_id: 'c1', source_kind: 'user_input', source_id: 'input-1', url: 'https://console.example/lumen/sources/runs/run-1/c1', title: metadata, snippet: metadata, asset_id: null, document_index: null, start_index: null, end_index: null, observed_at: null, provenance: null };
		expect(parseChatRunEvent({ ...base, type: 'source.registered', payload: { message_id: 'm1', citation } })).toMatchObject({ payload: { citation: { type: 'citation', citation_id: 'c1', source_kind: 'user_input', source_id: 'input-1', url: citation.url } } });
	});
	it('accepts a completed native tool call with null progress', () => {
		const part = { type: 'tool_call', call_id: 't1', name: 'read', arguments: {}, status: 'completed', progress: null };
		expect(parseChatRunEvent({ ...base, type: 'part.completed', payload: { message_id: 'm1', part_index: 0, part } })).toMatchObject({ payload: { part: { type: 'tool_call', call_id: 't1', name: 'read', arguments: {}, status: 'completed' } } });
	});
	it.each(['waiting_children', 'waiting_resource'])('accepts native %s stage without a fabricated tool name', (stage) => {
		expect(parseChatRunEvent({ ...base, type: 'run.stage.changed', payload: { stage, tool_name: null } })).toMatchObject({ payload: { stage, tool_name: null } });
		expect(() => parseChatRunEvent({ ...base, type: 'run.stage.changed', payload: { stage, tool_name: 'read' } })).toThrow(ChatContractError);
	});
	it.each([null, ''])('normalizes nullable image, audio and structured metadata, including nested images (%s)', (metadata) => {
		const image = { type: 'image', asset_id: 'asset-1', mime_type: 'image/png', name: 'chart.png', width: 2, height: 3 };
		const audio = { type: 'audio', asset_id: 'asset-2', mime_type: 'audio/wav', name: 'clip.wav', duration_ms: 250 };
		const structured = { type: 'structured', schema_name: 'summary', schema_version: '1', value: { result: 'ok' }, valid: true };
		const parts = [{ ...image, alt_text: metadata }, { ...audio, transcript: metadata }, { ...structured, validation_error: metadata }];
		expect(parseChatPartsStrict(parts)).toEqual([image, audio, structured]);
		const nested = { type: 'tool_result', call_id: 't1', name: 'read', is_error: false, content: [parts[0]] };
		expect(parseChatPartsStrict([nested])).toEqual([{ ...nested, content: [image] }]);
	});
	it('still rejects null required text and malformed optional metadata or half-ranges', () => {
		expect(() => parseChatPartsStrict([{ type: 'text', text: null }])).toThrow(ChatContractError);
		const citation = { type: 'citation', citation_id: 'c1', source_kind: 'web', url: 'https://example.org' };
		expect(() => parseChatPartsStrict([{ ...citation, title: 3 }])).toThrow(ChatContractError);
		expect(() => parseChatPartsStrict([{ ...citation, start_index: 1, end_index: null }])).toThrow(ChatContractError);
	});
	it.each(['?auth=public', '#api-key', '#section', '#authorization', '#token', '#key', '?q=password+reset'])('keeps backend-valid source URL metadata parseable: %s', (suffix) => {
		const citation = { type: 'citation', citation_id: 'c1', source_kind: 'web', url: `https://example.org/document${suffix}` };
		expect(parseChatRunEvent({ ...base, type: 'source.registered', payload: { message_id: 'm1', citation } })).toMatchObject({ type: 'source.registered', payload: { citation } });
	});
	it.each(['?api-key=secret', '?api%2Dkey=secret', '#api-key=secret'])('rejects native credential-bearing source URL metadata: %s', (suffix) => {
		const citation = { type: 'citation', citation_id: 'c1', source_kind: 'web', url: `https://example.org/document${suffix}` };
		expect(() => parseChatRunEvent({ ...base, type: 'source.registered', payload: { message_id: 'm1', citation } })).toThrow(ChatContractError);
	});
	it.each(['', 'x'.repeat(4001)])('rejects empty or unbounded progress (%s)', (text) => {
		expect(() => parseChatRunEvent({ ...base, type: 'tool.call.progress', payload: { call_id: 't1', name: 'read', text } })).toThrow(ChatContractError);
	});
	it('accepts bounded factual progress with exact keys only', () => {
		expect(parseChatRunEvent({ ...base, type: 'tool.call.progress', payload: { call_id: 't1', name: 'read', text: 'Read 2 files' } })).toMatchObject({ type: 'tool.call.progress' });
		expect(() => parseChatRunEvent({ ...base, type: 'tool.call.progress', payload: { call_id: 't1', name: 'read', text: 'Read 2 files', secret: 'no' } })).toThrow(ChatContractError);
	});
});

describe('bounded canonical assistant history', () => {
	it('retains 40 sources without truncating canonical server parts', () => {
		const parts = Array.from({ length: 40 }, (_, index) => ({ type: 'citation', citation_id: `c${index}`, source_kind: 'web', url: `https://example.org/${index}` }));
		expect(parseChatPartsStrict(parts)).toHaveLength(40);
		expect(parseChatPartsForDisplay(parts)).toHaveLength(40);
		expect(() => parseChatPartsStrict(Array.from({ length: MAX_CANONICAL_CHAT_PARTS + 1 }, () => ({ type: 'text', text: 'x' })))).toThrow(ChatContractError);
	});
	it('accepts the derived legal 64-tool / 128-source response and rejects exactly one part beyond it', () => {
		const parts: unknown[] = [
			{ type: 'text', text: 'Final answer' },
			{ type: 'reasoning', text: 'User-visible reasoning', visibility: 'user' },
			...Array.from({ length: 128 }, (_, index) => ({ type: 'citation', citation_id: `c${index}`, source_kind: 'web', url: `https://example.org/${index}` })),
			...Array.from({ length: 64 }, (_, index) => [
				{ type: 'tool_call', call_id: `t${index}`, name: 'read', arguments: {}, status: 'completed' },
				{ type: 'tool_result', call_id: `t${index}`, name: 'read', content: [], is_error: false }
			]).flat()
		];
		expect(MAX_CANONICAL_CHAT_PARTS).toBe(258);
		expect(parts).toHaveLength(MAX_CANONICAL_CHAT_PARTS);
		expect(parseChatPartsStrict(parts)).toHaveLength(MAX_CANONICAL_CHAT_PARTS);
		expect(parseChatPartsForDisplay(parts)).toHaveLength(MAX_CANONICAL_CHAT_PARTS);
		const overBound = [...parts, { type: 'text', text: 'One extra part' }];
		expect(() => parseChatPartsStrict(overBound)).toThrow(ChatContractError);
		expect(() => parseChatPartsForDisplay(overBound)).toThrow(ChatContractError);
	});
	it('retains bounded historical tool progress and rejects malformed progress', () => {
		const part = { type: 'tool_call', call_id: 't1', name: 'read', arguments: {}, status: 'completed', progress: ['Read file'] };
		expect(parseChatPartsStrict([part])).toEqual([part]);
		expect(() => parseChatPartsStrict([{ ...part, progress: ['x'.repeat(4001)] }])).toThrow(ChatContractError);
		expect(() => parseChatPartsStrict([{ ...part, progress: Array.from({ length: 33 }, () => 'Read file') }])).toThrow(ChatContractError);
	});
});

describe('chatContracts', () => {

	it('rejects unknown input parts but safely degrades display parts', () => {
		expect(() => parseChatPartsStrict([{ type: 'future_provider_block', secret: 'never render' }])).toThrow(ChatContractError);
		expect(parseChatPartsForDisplay([{ type: 'future_provider_block', secret: 'never render' }])).toEqual([
			{ type: 'unknown', original_type: 'future_provider_block' }
		]);
	});

	it('accepts the prompt-cache usage kinds and still rejects unknown kinds', () => {
		const component = (kind: string, source = 'executor') => ({
			segment_id: 'executor:aggregate',
			kind,
			quantity: '10',
			unit: 'token',
			unit_price_usd: '0',
			cost_usd: '0',
			source,
			model_name: 'claude-sonnet-4-6',
			metadata: {}
		});
		const event = (components: unknown[]) => ({
			event_id: 'run-1:3',
			run_id: 'run-1',
			seq: 3,
			type: 'usage.updated',
			created_at: '2026-09-23T00:00:00Z',
			payload: { components, prompt_tokens: 60, completion_tokens: 10, raw_cost: '0', credited_cost: '0' }
		});
		const cacheKinds = ['cache_read_input_tokens', 'cache_creation_5m_input_tokens', 'cache_creation_1h_input_tokens'];
		const advisorCacheKinds = ['advisor_cache_read_tokens', 'advisor_cache_creation_5m_tokens', 'advisor_cache_creation_1h_tokens'];
		const parsed = parseChatRunEvent(event([
			...cacheKinds.map((kind) => component(kind)),
			...advisorCacheKinds.map((kind) => component(kind, 'advisor'))
		]));
		expect(parsed).toMatchObject({ type: 'usage.updated' });
		expect(parsed.type === 'usage.updated' && parsed.payload.components.map((item) => item.kind)).toEqual([...cacheKinds, ...advisorCacheKinds]);
		expect(() => parseChatRunEvent(event([component('future_cache_tokens')]))).toThrow(ChatContractError);
	});

	it.each([
		['image_input_tokens', 'token'], ['image_cache_read_input_tokens', 'token'],
		['image_output_tokens', 'token'], ['audio_input_tokens', 'token'],
		['audio_cache_read_input_tokens', 'token'], ['audio_output_tokens', 'token'],
		['audio_input_characters', 'character'], ['realtime_session_seconds', 'second']
	])('consumes auditable %s ledger events without losing decimal rates', (kind, unit) => {
		const component = {
			segment_id: 'media:1', kind, quantity: '10', unit,
			unit_price_usd: '0.000000000123456789', cost_usd: '0.0000000012',
			source: 'media', model_name: 'configured-model', metadata: {}
		};
		const event = (row = component) => ({
			event_id: 'run-media:1', run_id: 'run-media', seq: 1, type: 'usage.updated',
			created_at: '2026-10-01T00:00:00Z', payload: {
				components: [row], prompt_tokens: 10, completion_tokens: 0,
				raw_cost: '0.0000000012', credited_cost: '0.00000012'
			}
		});
		const parsed = parseChatRunEvent(event());
		if (parsed.type !== 'usage.updated') throw new Error('usage event required');
		expect(parsed.payload.components[0]).toMatchObject({ kind, unit,
			unit_price_usd: '0.000000000123456789', cost_usd: '0.0000000012' });
		expect(() => parseChatRunEvent(event({ ...component, unit: 'hour' }))).toThrow(ChatContractError);
		expect(() => parseChatRunEvent(event({ ...component, cost_usd: '-0.0000000012' }))).toThrow(ChatContractError);
	});

	it('validates a canonical part-completed event and rejects cursor mismatch', () => {
		const event = {
			event_id: 'run-1:1',
			run_id: 'run-1',
			seq: 1,
			type: 'part.completed',
			created_at: '2026-07-21T00:00:00Z',
			payload: { message_id: '1', part_index: 0, part: { type: 'text', text: 'hello' } }
		};
		expect(parseChatRunEvent(event)).toMatchObject({ type: 'part.completed', seq: 1 });
		expect(() => parseChatRunEvent({ ...event, event_id: 'run-1:2' })).toThrow(ChatContractError);
	});

	it('parses a persisted stage event with a tool name only during execution', () => {
		expect(
			parseChatRunEvent({
				event_id: 'run-1:2',
				run_id: 'run-1',
				seq: 2,
				type: 'run.stage.changed',
				created_at: '2026-07-21T00:00:00Z',
				payload: { stage: 'tool_execution', tool_name: 'web_search' }
			})
		).toMatchObject({ type: 'run.stage.changed', payload: { tool_name: 'web_search' } });
		expect(() =>
			parseChatRunEvent({
				event_id: 'run-1:2',
				run_id: 'run-1',
				seq: 2,
				type: 'run.stage.changed',
				created_at: '2026-07-21T00:00:00Z',
				payload: { stage: 'queued', tool_name: 'web_search' }
			})
		).toThrow(ChatContractError);
	});

	it('requires run kind and strictly validates context.updated fields', () => {
		const state = {
			model_name: 'gpt-test',
			context_limit: 16000,
			output_reserve: 4096,
			safety_reserve: 2048,
			input_budget: 9856,
			input_tokens: 9856,
			utilization: 1.25,
			measurement: 'estimated',
			recommendation: 'required',
			can_compact: true,
			reason_code: null,
			revision: 'rev-1',
			checkpoint_id: null,
			active_compaction_run_id: null
		};
		const breakdown = { scope: 'request', complete: true, uncounted: [], components: [
			{ id: 'messages', tokens: 9856, measurement: 'estimated', count: 2, included: true, items: ['user:1', 'assistant:2'] }
		] };
		expect(() => parseContextState({ ...state, breakdown: { ...breakdown, components: [
			{ ...breakdown.components[0], raw_prompt: 'private' }
		] } })).toThrow(ChatContractError);
		expect(() => parseContextState({ ...state, breakdown: { ...breakdown, components: [
			{ ...breakdown.components[0], tokens: -1 }
		] } })).toThrow(ChatContractError);
		expect(() => parseContextState({ ...state, breakdown: { ...breakdown, uncounted: ['mcp_tools'] } })).toThrow(ChatContractError);
		expect(() => parseContextState({ ...state, breakdown: { ...breakdown, components: [breakdown.components[0], breakdown.components[0]] } })).toThrow(ChatContractError);
		expect(
			parseChatRunEvent({
				event_id: 'run-context:1',
				run_id: 'run-context',
				seq: 1,
				type: 'run.started',
				created_at: '2026-07-21T00:00:00Z',
				payload: {
					conversation_id: 'conv-1',
					temp_thread_id: null,
					model_name: 'gpt-test',
					effective_features: {},
					run_kind: 'compaction'
				}
			})
		).toMatchObject({ type: 'run.started', payload: { run_kind: 'compaction' } });
		expect(
			parseChatRunEvent({
				event_id: 'run-context:2',
				run_id: 'run-context',
				seq: 2,
				type: 'context.updated',
				created_at: '2026-07-21T00:00:01Z',
				payload: { state, phase: 'compacted', cause: 'manual', before_tokens: 12000, after_tokens: 7000 }
			})
		).toMatchObject({ type: 'context.updated', payload: { state: { utilization: 1.25 }, phase: 'compacted' } });
		expect(() =>
			parseChatRunEvent({
				event_id: 'run-context:2',
				run_id: 'run-context',
				seq: 2,
				type: 'context.updated',
				created_at: '2026-07-21T00:00:01Z',
				payload: { state: { ...state, unsafe_prompt: 'secret' }, phase: 'compacted', cause: 'manual', before_tokens: 12000, after_tokens: 7000 }
			})
		).toThrow(ChatContractError);
		expect(() => parseChatRunEvent({
			event_id: 'run-context:1',
			run_id: 'run-context',
			seq: 1,
			type: 'run.started',
			created_at: '2026-07-21T00:00:00Z',
			payload: {
				conversation_id: 'conv-1',
				temp_thread_id: null,
				model_name: 'gpt-test',
				effective_features: {}
			}
		})).toThrow(ChatContractError);
		expect(() => parseChatRunEvent({
			event_id: 'run-context:2',
			run_id: 'run-context',
			seq: 2,
			type: 'context.updated',
			created_at: '2026-07-21T00:00:01Z',
			payload: { state: { ...state, utilization: -0.1 }, phase: 'compacted', cause: null, before_tokens: null, after_tokens: null }
		})).toThrow(ChatContractError);
	});

	it('parses the backend awaiting-input approval stage without a tool name', () => {
		expect(
			parseChatRunEvent({
				event_id: 'run-approval:7',
				run_id: 'run-approval',
				seq: 7,
				type: 'run.stage.changed',
				created_at: '2026-07-26T00:00:00Z',
				payload: { stage: 'awaiting_input', tool_name: null }
			})
		).toMatchObject({
			type: 'run.stage.changed',
			payload: { stage: 'awaiting_input', tool_name: null }
		});
	});

	it('parses failed tool completion metadata while accepting legacy completed events', () => {
		const event = {
			event_id: 'run-1:3',
			run_id: 'run-1',
			seq: 3,
			type: 'tool.call.completed',
			created_at: '2026-07-27T00:00:00Z',
			payload: {
				call_id: 'call-1',
				name: 'builtin_read_status',
				content: [{ type: 'text', text: 'Tool call exceeded the run policy limit.' }],
				status: 'failed',
				error_code: 'policy_limit_exceeded'
			}
		};
		expect(parseChatRunEvent(event)).toMatchObject({ type: 'tool.call.completed', payload: { status: 'failed', error_code: 'policy_limit_exceeded' } });
		expect(parseChatRunEvent({ ...event, payload: { ...event.payload, status: 'completed', error_code: null } })).toMatchObject({ type: 'tool.call.completed', payload: { error_code: null } });
		expect(parseChatRunEvent({ ...event, payload: { call_id: 'call-1', name: 'legacy', content: [{ type: 'text', text: 'ok' }], status: 'completed' } })).toMatchObject({ type: 'tool.call.completed', payload: { error_code: null } });
	});

	it('parses only the exact approval-resolution payload with decision provenance', () => {
		const event = {
			event_id: 'run-1:3',
			run_id: 'run-1',
			seq: 3,
			type: 'tool.approval_resolved',
			created_at: '2026-07-21T00:00:00Z',
			payload: {
				call_id: 'call-1',
				decision: 'deny',
				decided_by_user_id: null,
				decided_at: '2026-07-21T00:00:01Z'
			}
		};
		expect(parseChatRunEvent(event)).toMatchObject({ type: 'tool.approval_resolved', payload: { decision: 'deny', decided_by_user_id: null } });
		expect(() => parseChatRunEvent({ ...event, payload: { ...event.payload, decided_at: 'not-a-date' } })).toThrow(ChatContractError);
		expect(() => parseChatRunEvent({ ...event, payload: { call_id: 'call-1', decision: 'deny' } })).toThrow(ChatContractError);
	});

	it('parses only redacted frozen approval dispatch details', () => {
		const event = {
			event_id: 'run-1:4',
			run_id: 'run-1',
			seq: 4,
			type: 'tool.approval_required',
			created_at: '2026-07-26T00:00:00Z',
			payload: {
				call_id: 'call-1',
				name: 'workspace.write_file',
				source: 'workspace',
				effect: 'workspace_write',
				destination: 'workspace:ws-1',
				redacted_arguments: { path: 'src/app.py', content: '[REDACTED]' },
				preview: [{ type: 'text', text: 'Modify src/app.py' }],
				expected_state_revision: 7,
				writer_fence: 3,
				expires_at: '2026-07-26T00:15:00Z'
			}
		};
		expect(parseChatRunEvent(event)).toMatchObject({ type: 'tool.approval_required', payload: { redacted_arguments: { content: '[REDACTED]' } } });
		expect(() => parseChatRunEvent({ ...event, payload: { ...event.payload, arguments: { content: 'secret' } } })).toThrow(ChatContractError);
	});

	it('parses only the exact bounded interaction-resolved payload', () => {
		const event = {
			event_id: 'run-1:3',
			run_id: 'run-1',
			seq: 3,
			type: 'interaction.resolved',
			created_at: '2026-07-21T00:00:00Z',
			payload: {
				interaction_id: '75dcc8d9-dc8d-460b-a6ca-6a5fdd1e10d6',
				status: 'answered',
				response: { option_ids: ['yes'], text: null }
			}
		};
		expect(parseChatRunEvent(event)).toMatchObject({ type: 'interaction.resolved', payload: { status: 'answered' } });
		expect(() =>
			parseChatRunEvent({
				...event,
				payload: { ...event.payload, response: { option_ids: ['yes'], text: 'x'.repeat(4001), extra: true } }
			})
		).toThrow(ChatContractError);
		expect(() => parseChatRunEvent({ ...event, payload: { ...event.payload, status: 'timeout' } })).toThrow(ChatContractError);
	});
	it.each([
		['run.completed', { status: 'completed', message_id: '1' }],
		['run.failed', { status: 'failed', message_id: null, error_code: 'provider_error', safe_message: 'Provider failed.' }],
		['run.canceled', { status: 'canceled', message_id: '1', error_code: 'canceled_by_user', safe_message: 'Canceled.' }]
	] as const)('parses the typed %s terminal payload', (type, payload) => {
		expect(
			parseChatRunEvent({
				event_id: 'run-1:2',
				run_id: 'run-1',
				seq: 2,
				type,
				created_at: '2026-07-21T00:00:00Z',
				payload
			})
		).toMatchObject({ type, payload });
	});
});

it('preserves whitespace and uses Unicode code points consistently for live and saved tool output', () => {
	const base = { event_id: 'run-1:1', run_id: 'run-1', seq: 1, created_at: '2026-11-03T00:00:00Z', type: 'tool.call.progress' };
	for (const text of [' \n\t', '📄'.repeat(4000)]) {
		expect(parseChatRunEvent({ ...base, payload: { call_id: 't1', name: 'read', text } })).toMatchObject({ payload: { text } });
		expect(parseChatPartsStrict([{ type: 'tool_call', call_id: 't1', name: 'read', arguments: {}, status: 'completed', progress: [text] }])[0]).toMatchObject({ progress: [text] });
	}
	expect(() => parseChatRunEvent({ ...base, payload: { call_id: 't1', name: 'read', text: '📄'.repeat(4001) } })).toThrow(ChatContractError);
});

it('accepts the native plugin source for tool lifecycle and approval without opening arbitrary source kinds', () => {
	const base = { event_id: 'run-1:1', run_id: 'run-1', seq: 1, created_at: '2026-11-03T00:00:00Z' };
	const identity = { call_id: 'plugin-call', name: 'plugin__owned__inspect', source: 'plugin', category: 'Plugin' };
	const events = [
		{ type: 'tool.call.started', payload: { ...identity, arguments: {} } },
		{ type: 'tool.call.completed', payload: { ...identity, content: [{ type: 'text', text: 'Observed result' }], status: 'completed', error_code: null } },
		{ type: 'tool.approval_required', payload: { call_id: identity.call_id, name: identity.name, source: 'plugin', effect: 'workspace_write', destination: null, redacted_arguments: {}, preview: [], expected_state_revision: null, writer_fence: null, expires_at: '2026-11-04T00:00:00Z' } },
	];
	for (const event of events) {
		expect(parseChatRunEvent({ ...base, ...event })).toMatchObject({ payload: { source: 'plugin' } });
		expect(() => parseChatRunEvent({ ...base, ...event, payload: { ...event.payload, source: 'unregistered-executor' } })).toThrow(ChatContractError);
	}
});
