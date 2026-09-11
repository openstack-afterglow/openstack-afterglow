import { describe, expect, it } from 'vitest';
import {
	buildActivePath,
	getSiblingInfo,
	getSiblings,
	lastAssistantModel,
	resolveLeafFor,
	projectMessagesForDisplay,
	siblingLeafInDirection,
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

/**
 * 트리 형태:
 *   u1 (user)
 *   ├─ a1  (assistant, 첫 답변)
 *   │   └─ u2 (user 후속)
 *   │       └─ a3 (assistant)
 *   └─ a2  (assistant, a1 재생성 형제 — 최신)
 */
const tree: ChatMessage[] = [
	msg('u1', 'user', null, '2026-01-01T00:00:00Z'),
	msg('a1', 'assistant', 'u1', '2026-01-01T00:00:01Z'),
	msg('u2', 'user', 'a1', '2026-01-01T00:00:02Z'),
	msg('a3', 'assistant', 'u2', '2026-01-01T00:00:03Z'),
	msg('a2', 'assistant', 'u1', '2026-01-01T00:00:04Z')
];

describe('buildActivePath', () => {
	it('active_leaf 에서 루트까지 역추적 후 reverse', () => {
		expect(buildActivePath(tree, 'a3').map((m) => m.id)).toEqual(['u1', 'a1', 'u2', 'a3']);
	});

	it('형제 리프를 활성으로 지정하면 그 경로만', () => {
		expect(buildActivePath(tree, 'a2').map((m) => m.id)).toEqual(['u1', 'a2']);
	});

	it('빈 입력은 빈 경로', () => {
		expect(buildActivePath([], 'x')).toEqual([]);
	});

	it('active_leaf 가 없으면 최신 리프로 폴백', () => {
		// 리프 후보: a3(00:03), a2(00:04) → 최신 a2
		expect(buildActivePath(tree, null).map((m) => m.id)).toEqual(['u1', 'a2']);
	});

	it('알 수 없는 leaf id 도 최신 리프로 폴백', () => {
		expect(buildActivePath(tree, 'ghost').map((m) => m.id)).toEqual(['u1', 'a2']);
	});
});

describe('getSiblings / getSiblingInfo', () => {
	it('같은 parent_id 의 같은 role 을 created_at 순으로', () => {
		const a1 = tree.find((m) => m.id === 'a1')!;
		expect(getSiblings(tree, a1).map((m) => m.id)).toEqual(['a1', 'a2']);
	});

	it('1-based 인덱스와 총 개수', () => {
		const a2 = tree.find((m) => m.id === 'a2')!;
		expect(getSiblingInfo(tree, a2)).toMatchObject({ index: 2, total: 2 });
	});

	it('형제 없으면 total=1', () => {
		const a3 = tree.find((m) => m.id === 'a3')!;
		expect(getSiblingInfo(tree, a3)).toMatchObject({ index: 1, total: 1 });
	});
});

describe('resolveLeafFor', () => {
	it('subtree 가 있는 형제는 최신 자식을 따라 리프까지 내려감', () => {
		// a1 아래 u2 → a3 (리프)
		expect(resolveLeafFor(tree, 'a1')).toBe('a3');
	});

	it('이미 리프면 그대로', () => {
		expect(resolveLeafFor(tree, 'a2')).toBe('a2');
		expect(resolveLeafFor(tree, 'a3')).toBe('a3');
	});
});

describe('siblingLeafInDirection', () => {
	it('a2 에서 이전으로 이동하면 a1 의 리프(a3) 로 전환', () => {
		const a2 = tree.find((m) => m.id === 'a2')!;
		expect(siblingLeafInDirection(tree, a2, -1)).toBe('a3');
	});

	it('a1 에서 다음으로 이동하면 a2 리프', () => {
		const a1 = tree.find((m) => m.id === 'a1')!;
		expect(siblingLeafInDirection(tree, a1, 1)).toBe('a2');
	});

	it('경계 밖 이동은 null', () => {
		const a2 = tree.find((m) => m.id === 'a2')!;
		expect(siblingLeafInDirection(tree, a2, 1)).toBeNull();
		const a1 = tree.find((m) => m.id === 'a1')!;
		expect(siblingLeafInDirection(tree, a1, -1)).toBeNull();
	});
});

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
