// @vitest-environment node
import { describe, expect, it } from 'vitest';
import { taskLabelForStage, taskLabelForTool } from '../chatTaskLabels';

describe('taskLabelForTool', () => {
	it('keeps each MCP task distinct without exposing its server identifier', () => {
		const documents = taskLabelForTool('mcp__server-42__list_documents');
		const memory = taskLabelForTool('mcp__server-42__memory_write');
		expect(documents).not.toBe(memory);
		expect(documents).not.toContain('server-42');
		expect(memory).not.toContain('server-42');
	});
});

describe('taskLabelForStage', () => {
	it('names observed lifecycle stages without presenting them as private reasoning', () => {
		expect(taskLabelForStage('tool_execution', 'managed_web_search')).not.toBeNull();
		expect(taskLabelForStage('awaiting_input', null)).not.toBeNull();
		expect(taskLabelForStage('model_response', null)).toBe('모델 응답 수신');
		expect(taskLabelForStage('model_request', null)).toBe('모델 요청 전송');
		expect(taskLabelForStage('response_writing', null)).toBe('답변 작성');
	});
});
