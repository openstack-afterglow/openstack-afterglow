import { describe, expect, it } from 'vitest';
import {
	ChatContractError,
	parseChatPartsForDisplay,
	parseChatPartsStrict,
	parseChatRunEvent,
	parseContextState
} from '../chatContracts';

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
