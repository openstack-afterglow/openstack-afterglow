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
	it('only promotes task-bearing stages', () => {
		expect(taskLabelForStage('tool_execution', 'managed_web_search')).not.toBeNull();
		expect(taskLabelForStage('awaiting_input', null)).not.toBeNull();
		expect(taskLabelForStage('model_response', null)).toBeNull();
	});
});
