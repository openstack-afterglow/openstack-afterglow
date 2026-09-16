import { describe, expect, it } from 'vitest';
import { taskLabelForContext, taskLabelForStage, taskLabelForTool } from '../chatTaskLabels';

describe('taskLabelForTool', () => {
	it('maps managed and built-in tools to user-facing task labels', () => {
		expect(taskLabelForTool('managed_web_search')).toBe('웹 검색');
		expect(taskLabelForTool('list_my_conversations')).toBe('대화 목록 확인');
		expect(taskLabelForTool('memory_search')).toBe('메모리 검색');
		expect(taskLabelForTool('afterglow_vm_delete')).toBe('가상 머신 삭제');
	});

	it('keeps each MCP task distinct without exposing its server identifier', () => {
		expect(taskLabelForTool('mcp__server-42__list_documents')).toBe('MCP: List Documents');
		expect(taskLabelForTool('mcp__server-42__memory_write')).toBe('MCP: Memory Write');
	});
});

describe('taskLabelForStage', () => {
	it('only promotes task-bearing stages', () => {
		expect(taskLabelForStage('tool_execution', 'managed_web_search')).toBe('웹 검색 진행 중');
		expect(taskLabelForStage('awaiting_input', null)).toBe('작업 승인을 기다리는 중');
		expect(taskLabelForStage('model_response', null)).toBeNull();
	});

	it('labels manual and automatic context compaction activity', () => {
		expect(taskLabelForContext('compacting', 'manual')).toBe('컨텍스트 압축 중');
		expect(taskLabelForContext('compacted', 'manual')).toBe('컨텍스트 압축 완료');
		expect(taskLabelForContext('compacting', 'automatic')).toBe('컨텍스트 자동 압축 중');
		expect(taskLabelForContext('compacted', 'automatic')).toBe('컨텍스트 자동 압축 완료');
	});
});
