// @vitest-environment node
import { describe, expect, it } from 'vitest';
import {
	agentToForm,
	buildAgentPayload,
	emptyAgentForm,
	idsFromRecord,
	isAvatarUrl,
	type Agent
} from '../chatAgents';

describe('idsFromRecord', () => {
	it('선택된 id 만 오름차순 int[]', () => {
		expect(idsFromRecord({ 3: true, 1: false, 2: true })).toEqual([2, 3]);
	});
	it('빈 Record → 빈 배열', () => {
		expect(idsFromRecord({})).toEqual([]);
	});
});

describe('buildAgentPayload', () => {
	it('빈 선택값 필드는 생략, params 없음', () => {
		const form = { ...emptyAgentForm(), name: '  도우미  ' };
		expect(buildAgentPayload(form)).toEqual({
			name: '도우미',
			mcp_ids: [],
			tool_ids: [],
			visibility: 'private'
		});
	});

	it('temperature/max_tokens 유효 시에만 params 포함', () => {
		const form = {
			...emptyAgentForm(),
			name: 'a',
			temperature: '0.7',
			max_tokens: '2048'
		};
		expect(buildAgentPayload(form).params).toEqual({ temperature: 0.7, max_tokens: 2048 });
	});

	it('max_tokens 가 0/음수/비정수면 생략', () => {
		expect(buildAgentPayload({ ...emptyAgentForm(), name: 'a', max_tokens: '0' }).params).toBeUndefined();
		expect(buildAgentPayload({ ...emptyAgentForm(), name: 'a', max_tokens: '-5' }).params).toBeUndefined();
		expect(buildAgentPayload({ ...emptyAgentForm(), name: 'a', max_tokens: '1.5' }).params).toBeUndefined();
	});

	it('temperature 만 있으면 그것만', () => {
		expect(buildAgentPayload({ ...emptyAgentForm(), name: 'a', temperature: '0' }).params).toEqual({
			temperature: 0
		});
	});

	it('선택 필드 + id 배열 매핑', () => {
		const form = {
			...emptyAgentForm(),
			name: 'agent',
			description: ' desc ',
			avatar: '🤖',
			instructions: ' do things ',
			model_name: 'gpt-4o',
			visibility: 'public' as const,
			mcp_ids: { 5: true, 2: true, 9: false },
			tool_ids: { 1: true }
		};
		expect(buildAgentPayload(form)).toEqual({
			name: 'agent',
			description: 'desc',
			avatar: '🤖',
			instructions: 'do things',
			model_name: 'gpt-4o',
			visibility: 'public',
			mcp_ids: [2, 5],
			tool_ids: [1]
		});
	});
});

describe('agentToForm', () => {
	const base: Agent = {
		id: 1,
		name: '리서처',
		description: '검색 도우미',
		avatar: '🔎',
		instructions: '너는 리서처다',
		model_name: 'claude-sonnet-5',
		params: { temperature: 0.3, max_tokens: 4096 },
		mcp_ids: [7, 4],
		tool_ids: [2],
		visibility: 'public'
	};

	it('편집 진입 왕복: form → payload 가 원본과 일치', () => {
		const form = agentToForm(base);
		expect(form.temperature).toBe('0.3');
		expect(form.max_tokens).toBe('4096');
		expect(form.mcp_ids).toEqual({ 7: true, 4: true });
		const payload = buildAgentPayload(form);
		expect(payload).toEqual({
			name: '리서처',
			description: '검색 도우미',
			avatar: '🔎',
			instructions: '너는 리서처다',
			model_name: 'claude-sonnet-5',
			params: { temperature: 0.3, max_tokens: 4096 },
			mcp_ids: [4, 7],
			tool_ids: [2],
			visibility: 'public'
		});
	});

	it('params null 이면 빈 문자열', () => {
		const form = agentToForm({ ...base, params: null });
		expect(form.temperature).toBe('');
		expect(form.max_tokens).toBe('');
	});
});

describe('isAvatarUrl', () => {
	it('http(s) URL 이면 true', () => {
		expect(isAvatarUrl('https://x/y.png')).toBe(true);
		expect(isAvatarUrl('http://x/y.png')).toBe(true);
	});
	it('이모지/텍스트/빈값이면 false', () => {
		expect(isAvatarUrl('🤖')).toBe(false);
		expect(isAvatarUrl('')).toBe(false);
		expect(isAvatarUrl(null)).toBe(false);
	});
});
