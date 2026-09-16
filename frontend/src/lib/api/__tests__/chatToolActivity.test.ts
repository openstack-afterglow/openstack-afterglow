import { describe, expect, it } from 'vitest';
import {
	formatToolArgs,
	parseAssistantToolCalls,
	toolActivityFromCanonicalParts,
	toolNameFromResultMeta
} from '../chatToolActivity';

describe('parseAssistantToolCalls', () => {
	it('litellm/OpenAI 형태(function.{name,arguments})를 파싱', () => {
		const items = parseAssistantToolCalls([
			{ id: 'c1', type: 'function', function: { name: 'search', arguments: '{"q":"seoul"}' } }
		]);
		expect(items).toEqual([
			{ id: 'c1', name: 'search', args: '{"q":"seoul"}', result: null, running: true }
		]);
	});
	it('라이브 SSE 형태({name,args})를 파싱', () => {
		const items = parseAssistantToolCalls([{ id: 'c2', name: 'list', args: '{}' }]);
		expect(items[0].name).toBe('list');
		expect(items[0].id).toBe('c2');
	});
	it('이름 없는 항목은 건너뛴다', () => {
		expect(parseAssistantToolCalls([{ id: 'x' }, null, 'nope'])).toEqual([]);
	});
	it('배열 아니면 빈 목록', () => {
		expect(parseAssistantToolCalls(undefined)).toEqual([]);
		expect(parseAssistantToolCalls({})).toEqual([]);
	});
});

describe('toolNameFromResultMeta', () => {
	it('결과 메타에서 툴 이름 추출', () => {
		expect(toolNameFromResultMeta([{ tool_call_id: 'c1', name: 'search' }])).toBe('search');
	});
	it('식별 불가 시 null', () => {
		expect(toolNameFromResultMeta([])).toBeNull();
		expect(toolNameFromResultMeta(null)).toBeNull();
	});
});

describe('toolActivityFromCanonicalParts', () => {
	it('복원된 canonical tool call/result를 하나의 완료 카드로 결합한다', () => {
		expect(
			toolActivityFromCanonicalParts([
				{ type: 'tool_call', call_id: 'c1', name: 'mcp.search', arguments: { q: 'union mount' }, status: 'running' },
				{ type: 'tool_result', call_id: 'c1', name: 'mcp.search', content: [{ type: 'text', text: 'result' }], is_error: false }
			])
		).toEqual([{ id: 'c1', name: 'mcp.search', args: '{"q":"union mount"}', result: 'result', running: false }]);
	});

	it('생성 파일 part를 다운로드 가능한 artifact로 보존한다', () => {
		expect(
			toolActivityFromCanonicalParts([
				{ type: 'tool_call', call_id: 'c2', name: 'workspace.report', arguments: {}, status: 'running' },
				{
					type: 'tool_result',
					call_id: 'c2',
					name: 'workspace.report',
					content: [
						{
							type: 'file',
							asset_id: 'asset-1',
							mime_type: 'text/csv',
							name: 'report.csv',
							size_bytes: 2048
						}
					],
					is_error: false
				}
			])
		).toEqual([
			{
				id: 'c2',
				name: 'workspace.report',
				args: '{}',
				result: null,
				running: false,
				files: [
					{
						assetId: 'asset-1',
						name: 'report.csv',
						mimeType: 'text/csv',
						sizeBytes: 2048
					}
				]
			}
		]);
	});
});

describe('formatToolArgs', () => {
	it('빈 객체·공백은 빈 문자열', () => {
		expect(formatToolArgs('{}')).toBe('');
		expect(formatToolArgs('   ')).toBe('');
		expect(formatToolArgs(null)).toBe('');
	});
	it('유효 JSON 은 pretty print', () => {
		expect(formatToolArgs('{"q":"x"}')).toBe('{\n  "q": "x"\n}');
	});
	it('파싱 실패 원문 유지', () => {
		expect(formatToolArgs('not json')).toBe('not json');
	});
});
