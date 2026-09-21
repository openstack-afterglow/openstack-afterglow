import { describe, expect, it } from 'vitest';
import {
	lastAssistantModel,
	projectMessagesForDisplay,
	type ChatMessage,
	type ChatUsage
} from '../chatTree';

function msg(
	id: string,
	role: ChatMessage['role'],
	parent_id: string | null,
	created_at: string
): ChatMessage {
	return { id, conversation_id: 'c1', role, parent_id, content: id, created_at };
}


describe('lastAssistantModel', () => {
	const withModel = (m: ChatMessage, model: string | null): ChatMessage => ({
		...m,
		model_name: model
	});

	it('마지막 assistant 의 model_name 을 반환', () => {
		const path = [
			msg('u1', 'user', null, '2026-01-01T00:00:00Z'),
			withModel(msg('a1', 'assistant', 'u1', '2026-01-01T00:00:01Z'), 'gpt-4o'),
			msg('u2', 'user', 'a1', '2026-01-01T00:00:02Z'),
			withModel(msg('a2', 'assistant', 'u2', '2026-01-01T00:00:03Z'), 'claude-sonnet-5')
		];
		expect(lastAssistantModel(path)).toBe('claude-sonnet-5');
	});

	it('뒤에 tool 메시지가 붙어도 마지막 assistant 를 찾음', () => {
		const path = [
			withModel(msg('a1', 'assistant', null, '2026-01-01T00:00:01Z'), 'gpt-4o'),
			msg('t1', 'tool', 'a1', '2026-01-01T00:00:02Z')
		];
		expect(lastAssistantModel(path)).toBe('gpt-4o');
	});

	it('assistant 가 없거나 model_name 이 없으면 null', () => {
		expect(lastAssistantModel([msg('u1', 'user', null, '2026-01-01T00:00:00Z')])).toBeNull();
		expect(
			lastAssistantModel([withModel(msg('a1', 'assistant', null, '2026-01-01T00:00:01Z'), null)])
		).toBeNull();
	});
});

describe('projectMessagesForDisplay', () => {
	it('keeps a durable MCP call and final answer inside one assistant message', () => {
		const path = [
			msg('u1', 'user', null, '2026-07-28T00:00:00Z'),
			{
				...msg('a-tool', 'assistant', 'u1', '2026-07-28T00:00:01Z'),
				parts: [
					{
						type: 'tool_call',
						call_id: 'call-1',
						name: 'mcp__1__notion_search',
						arguments: { query: 'database' },
						status: 'completed'
					},
					{
						type: 'tool_result',
						call_id: 'call-1',
						name: 'mcp__1__notion_search',
						content: [{ type: 'text', text: 'found' }],
						is_error: false
					}
				],
				execution: { tool_durations_ms: { 'call-1': 840 } }
			},
			{ ...msg('a-final', 'assistant', 'a-tool', '2026-07-28T00:00:02Z'), content: '검색 결과입니다.' }
		];

		const projected = projectMessagesForDisplay(path);

		expect(projected).toHaveLength(2);
		expect(projected[1]).toMatchObject({
			id: 'a-final',
			content: '검색 결과입니다.',
			tool_items: [
				{
					id: 'call-1',
					name: 'mcp__1__notion_search',
					result: 'found',
					running: false,
					durationMs: 840
				}
			]
		});
	});
});

describe('ChatUsage contract', () => {
	it('requires the complete ledger-backed monthly and lifetime fields', () => {
		const usage: ChatUsage = {
			found: true,
			total_credited_cost: 7.2,
			lifetime_prompt_tokens: 1000,
			lifetime_completion_tokens: 500,
			lifetime_request_count: 1,
			month_credited_cost: 7.2,
			week_credited_cost: 2.5,
			month_prompt_tokens: 1000,
			month_completion_tokens: 500,
			month_request_count: 1,
			quota_used: 7.2,
			quota_max: 1000,
			quota_weekly_max: 100
		};

		expect(usage.month_prompt_tokens + usage.month_completion_tokens).toBe(1500);
		expect(usage.quota_used).toBe(usage.month_credited_cost);
		expect(usage.week_credited_cost).toBe(2.5);
	});
});
