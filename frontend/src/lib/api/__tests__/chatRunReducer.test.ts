import { describe, expect, it } from 'vitest';
import { parseChatRunEvent } from '../chatContracts';
import { createRunViewState, reduceRunEvent } from '../chatRunReducer';

const at = '2026-07-21T00:00:00Z';

function event(seq: number, type: string, payload: object, createdAt = at) {
	return parseChatRunEvent({
		event_id: `run-1:${seq}`,
		run_id: 'run-1',
		seq,
		type,
		created_at: createdAt,
		payload
	});
}

describe('chat run reducer', () => {
	it('accumulates ordered deltas and replaces them with canonical completed parts', () => {
		let state = createRunViewState('run-1');
		state = reduceRunEvent(state, event(1, 'run.started', { conversation_id: 'c1', temp_thread_id: null, model_name: 'm', effective_features: {}, run_kind: 'completion' }));
		state = reduceRunEvent(state, event(2, 'message.created', { message_id: '42', role: 'assistant', parent_id: '1' }));
		state = reduceRunEvent(state, event(3, 'part.delta', { message_id: '42', part_index: 0, part_type: 'text', delta: 'hel' }));
		state = reduceRunEvent(state, event(4, 'part.delta', { message_id: '42', part_index: 0, part_type: 'text', delta: 'lo' }));
		state = reduceRunEvent(state, event(5, 'part.completed', { message_id: '42', part_index: 0, part: { type: 'text', text: 'hello' } }));
		expect(state.parts).toEqual([{ type: 'text', text: 'hello' }]);
		expect(state.messageId).toBe('42');
	});

	it('retains the latest persisted stage and its start time after replay', () => {
		let state = createRunViewState('run-1');
		state = reduceRunEvent(
			state,
			event(1, 'run.stage.changed', { stage: 'queued', tool_name: null })
		);
		state = reduceRunEvent(
			state,
			event(2, 'run.stage.changed', { stage: 'tool_execution', tool_name: 'web_search' })
		);
		expect(state).toMatchObject({
			stage: 'tool_execution',
			stageToolName: 'web_search',
			stageStartedAt: at
		});
	});

	it('replays the backend awaiting-input approval stage into the activity journal', () => {
		const state = reduceRunEvent(
			createRunViewState('run-1'),
			event(1, 'run.stage.changed', { stage: 'awaiting_input', tool_name: null })
		);
		expect(state).toMatchObject({
			stage: 'awaiting_input',
			stageToolName: null,
			activity: [expect.objectContaining({ kind: 'stage', stage: 'awaiting_input', toolName: null })]
		});
	});

	it('replays stages, user-visible reasoning, and a tool call in durable sequence', () => {
		let state = createRunViewState('run-1');
		state = reduceRunEvent(state, event(1, 'run.stage.changed', { stage: 'model_response', tool_name: null }));
		state = reduceRunEvent(
			state,
			event(2, 'part.delta', { message_id: '42', part_index: 1, part_type: 'reasoning', delta: '문서를 확인합니다.' })
		);
		state = reduceRunEvent(
			state,
			event(3, 'tool.call.started', { call_id: 'call-1', name: 'web_search', arguments: { query: 'Afterglow' } })
		);
		state = reduceRunEvent(
			state,
			event(4, 'tool.call.completed', {
				call_id: 'call-1',
				name: 'web_search',
				content: [{ type: 'text', text: '결과' }],
				status: 'completed',
				error_code: null
			})
		);

		expect(state.activity).toEqual([
			expect.objectContaining({ kind: 'stage', seq: 1, stage: 'model_response' }),
			expect.objectContaining({ kind: 'reasoning', seq: 2, text: '문서를 확인합니다.', active: true }),
			expect.objectContaining({
				kind: 'tool',
				seq: 3,
				callId: 'call-1',
				status: 'completed',
				content: [{ type: 'text', text: '결과' }]
			})
		]);
	});

	it('measures completed tool activity from durable event timestamps', () => {
		let state = createRunViewState('run-1');
		state = reduceRunEvent(
			state,
			event(
				1,
				'tool.call.started',
				{ call_id: 'call-1', name: 'notion_search', arguments: { query: 'Afterglow' } },
				'2026-07-28T00:00:00Z'
			)
		);
		state = reduceRunEvent(
			state,
			event(
				2,
				'tool.call.completed',
				{ call_id: 'call-1', name: 'notion_search', content: [], status: 'completed', error_code: null },
				'2026-07-28T00:00:00.840Z'
			)
		);

		expect(state.tools['call-1']).toMatchObject({
			callId: 'call-1',
			status: 'completed',
			durationMs: 840
		});
		expect(state.activity).toContainEqual(
			expect.objectContaining({ kind: 'tool', callId: 'call-1', durationMs: 840 })
		);
	});

	it('preserves same-index reasoning from successive model messages around a tool call', () => {
		let state = createRunViewState('run-1');
		state = reduceRunEvent(state, event(1, 'message.created', { message_id: 'assistant-1', role: 'assistant', parent_id: null }));
		state = reduceRunEvent(
			state,
			event(2, 'part.delta', { message_id: 'assistant-1', part_index: 1, part_type: 'reasoning', delta: '첫 번째 판단' })
		);
		state = reduceRunEvent(
			state,
			event(3, 'tool.call.started', { call_id: 'call-1', name: 'web_search', arguments: { query: 'Afterglow' } })
		);
		state = reduceRunEvent(state, event(4, 'message.created', { message_id: 'assistant-2', role: 'assistant', parent_id: null }));
		state = reduceRunEvent(
			state,
			event(5, 'part.completed', {
				message_id: 'assistant-1',
				part_index: 1,
				part: { type: 'reasoning', text: '첫 번째 판단 완료', visibility: 'user' }
			})
		);
		state = reduceRunEvent(
			state,
			event(6, 'part.delta', { message_id: 'assistant-2', part_index: 1, part_type: 'reasoning', delta: '두 번째 판단' })
		);

		expect(state.activity).toEqual([
			expect.objectContaining({ kind: 'reasoning', id: 'reasoning:assistant-1:1', seq: 2, text: '첫 번째 판단 완료', active: false }),
			expect.objectContaining({ kind: 'tool', id: 'tool:call-1', seq: 3 }),
			expect.objectContaining({ kind: 'reasoning', id: 'reasoning:assistant-2:1', seq: 6, text: '두 번째 판단' })
		]);
		expect(state.parts[1]).toEqual({ type: 'reasoning', text: '두 번째 판단', visibility: 'user' });
	});

	it('retains compaction context events without creating an assistant message', () => {
		const contextState = {
			model_name: 'm',
			context_limit: 16000,
			output_reserve: 4096,
			safety_reserve: 2048,
			input_budget: 9856,
			input_tokens: 8000,
			utilization: 8000 / 9856,
			measurement: 'tokenizer',
			recommendation: 'required',
			can_compact: true,
			reason_code: null,
			revision: 'rev-1',
			checkpoint_id: null,
			active_compaction_run_id: 'run-1'
		};
		let state = createRunViewState('run-1');
		state = reduceRunEvent(state, event(1, 'run.started', { conversation_id: 'c1', temp_thread_id: null, model_name: 'm', effective_features: {}, run_kind: 'compaction' }));
		state = reduceRunEvent(
			state,
			event(2, 'context.updated', {
				state: contextState,
				phase: 'compacting',
				cause: 'manual',
				before_tokens: 8000,
				after_tokens: null
			})
		);
		expect(state.runKind).toBe('compaction');
		expect(state.messageId).toBeNull();
		expect(state.context).toMatchObject({ phase: 'compacting', cause: 'manual', before_tokens: 8000 });
		expect(state.activity).toEqual([expect.objectContaining({ kind: 'context', phase: 'compacting' })]);
	});

	it('deduplicates old events and rejects a sequence gap', () => {
		const state = createRunViewState('run-1');
		const started = { conversation_id: null, temp_thread_id: null, model_name: 'm', effective_features: {}, run_kind: 'completion' };
		const afterStarted = reduceRunEvent(state, event(1, 'run.started', started));
		expect(reduceRunEvent(afterStarted, event(1, 'run.started', started))).toBe(afterStarted);
		expect(() => reduceRunEvent(afterStarted, event(3, 'run.started', started))).toThrow('sequence gap');
	});
});
