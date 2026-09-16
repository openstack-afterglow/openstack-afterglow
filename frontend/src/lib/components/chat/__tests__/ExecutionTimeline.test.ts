import { fireEvent, render, waitFor } from '@testing-library/svelte';
import { expect, it, vi } from 'vitest';
import ExecutionTimeline from '../ExecutionTimeline.svelte';

it('shows user-facing tasks while hiding backend lifecycle stages', async () => {
	const { getByLabelText, getByText, queryByText } = render(ExecutionTimeline, {
		active: true,
		items: [
			{
				id: 'stage:1',
				kind: 'stage',
				seq: 1,
				createdAt: '2026-07-26T00:00:00Z',
				stage: 'model_response',
				toolName: null
			},
			{
				id: 'reasoning:0',
				kind: 'reasoning',
				seq: 2,
				createdAt: '2026-07-26T00:00:01Z',
				text: '검색 범위를 정리합니다.',
				active: false
			},
			{
				id: 'stage:2',
				kind: 'stage',
				seq: 3,
				createdAt: '2026-07-26T00:00:02Z',
				stage: 'tool_execution',
				toolName: 'managed_web_search'
			},
			{
				id: 'tool:call-1',
				kind: 'tool',
				seq: 4,
				createdAt: '2026-07-26T00:00:03Z',
				callId: 'call-1',
				name: 'managed_web_search',
				source: 'managed',
				category: '관리형 도구',
				arguments: { query: 'Afterglow' },
				status: 'completed',
				content: [{ type: 'text', text: '검색 결과' }],
				durationMs: null,
				errorCode: null
			},
			{
				id: 'stage:3',
				kind: 'stage',
				seq: 5,
				createdAt: '2026-07-26T00:00:04Z',
				stage: 'response_writing',
				toolName: null
			}
		]
	});

	const timeline = getByLabelText('실행 기록');
	expect(timeline.textContent).toMatch(/추론 과정.*웹 검색/s);
	expect(queryByText('모델 응답을 처리함')).toBeNull();
	expect(queryByText('응답을 작성함')).toBeNull();
	await fireEvent.click(getByText('추론 과정'));
	expect(getByText('검색 범위를 정리합니다.')).toBeTruthy();
	await fireEvent.click(getByText('웹 검색'));
	expect(getByText('검색 결과')).toBeTruthy();
});

it('keeps completed execution details closed until each nested disclosure is opened', async () => {
	const { container, getByLabelText, getByText, queryByText } = render(ExecutionTimeline, {
		active: false,
		items: [
			{
				id: 'reasoning:0',
				kind: 'reasoning',
				seq: 1,
				createdAt: '2026-07-26T00:00:00Z',
				text: '도구 범위를 정리합니다.',
				active: false
			},
			{
				id: 'tool:call-1',
				kind: 'tool',
				seq: 2,
				createdAt: '2026-07-26T00:00:01Z',
				callId: 'call-1',
				name: 'mcp__7__search',
				source: 'mcp',
				category: 'MCP · 문서',
				arguments: { query: 'Afterglow' },
				status: 'completed',
				content: [{ type: 'text', text: '검색 결과' }],
				errorCode: null,
				durationMs: 210
			}
		]
	});

	const timeline = getByLabelText('작업 내역 열기');
	expect((timeline.closest('details') as HTMLDetailsElement).open).toBe(false);
	await fireEvent.click(timeline);
	const category = getByText('MCP · 문서');
	expect((category.closest('details') as HTMLDetailsElement).open).toBe(false);
	await fireEvent.click(category);
	expect((category.closest('details') as HTMLDetailsElement).open).toBe(true);
	const toolButton = container.querySelector('.tool-head') as HTMLButtonElement;
	expect(toolButton.getAttribute('aria-expanded')).toBe('false');
	await fireEvent.click(toolButton);
	expect(getByText('검색 결과')).toBeTruthy();
	await fireEvent.click(getByText('추론 과정'));
	expect(getByText('도구 범위를 정리합니다.')).toBeTruthy();
});


it('renders durable generated files as owned download actions', async () => {
	const { container, getByLabelText, getByText } = render(ExecutionTimeline, {
		active: false,
		items: [
			{
				id: 'tool:call-file',
				kind: 'tool',
				seq: 1,
				createdAt: '2026-07-26T00:00:00Z',
				callId: 'call-file',
				name: 'workspace_report',
				source: 'workspace',
				category: '워크스페이스',
				arguments: {},
				status: 'completed',
				content: [
					{
						type: 'file',
						asset_id: 'asset-1',
						mime_type: 'text/csv',
						name: 'report.csv',
						size_bytes: 2048
					}
				],
				errorCode: null,
				durationMs: 40
			}
		]
	});

	await fireEvent.click(getByLabelText('작업 내역 열기'));
	await fireEvent.click(getByText('워크스페이스'));
	await fireEvent.click(container.querySelector('.tool-head') as HTMLButtonElement);

	const download = getByLabelText('report.csv 다운로드');
	expect(download.textContent).toContain('report.csv');
	expect(download.textContent).toContain('2.0 KB');

	const fetchMock = vi.fn(async () => new Response('name,value\nlatency,12\n', { status: 200 }));
	const createObjectURL = vi.fn((_blob: Blob) => 'blob:report');
	const revokeObjectURL = vi.fn();
	const originalCreateObjectURL = Object.getOwnPropertyDescriptor(URL, 'createObjectURL');
	const originalRevokeObjectURL = Object.getOwnPropertyDescriptor(URL, 'revokeObjectURL');
	Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: createObjectURL });
	Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: revokeObjectURL });
	const anchorClick = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
	vi.stubGlobal('fetch', fetchMock);
	try {
		await fireEvent.click(download);
		await waitFor(() => expect(anchorClick).toHaveBeenCalledOnce());
		expect(fetchMock).toHaveBeenCalledWith(
			expect.stringContaining('/api/v1/chat/assets/asset-1/download'),
			expect.any(Object)
		);
		const generatedBlob = createObjectURL.mock.calls[0]?.[0];
		expect(generatedBlob).toMatchObject({ size: 22, type: 'text/plain;charset=utf-8' });
		expect(revokeObjectURL).toHaveBeenCalledWith('blob:report');
	} finally {
		vi.unstubAllGlobals();
		anchorClick.mockRestore();
		if (originalCreateObjectURL) Object.defineProperty(URL, 'createObjectURL', originalCreateObjectURL);
		else Reflect.deleteProperty(URL, 'createObjectURL');
		if (originalRevokeObjectURL) Object.defineProperty(URL, 'revokeObjectURL', originalRevokeObjectURL);
		else Reflect.deleteProperty(URL, 'revokeObjectURL');
	}
});

it('shows automatic context compaction start and completion activity', () => {
	const { getByText } = render(ExecutionTimeline, {
		active: true,
		items: [
			{
				id: 'context:1',
				kind: 'context',
				seq: 1,
				createdAt: '2026-07-26T00:00:00Z',
				phase: 'compacting',
				cause: 'automatic',
				beforeTokens: 12000,
				afterTokens: null
			},
			{
				id: 'context:2',
				kind: 'context',
				seq: 2,
				createdAt: '2026-07-26T00:00:01Z',
				phase: 'compacted',
				cause: 'automatic',
				beforeTokens: 12000,
				afterTokens: 7000
			}
		]
	});
	expect(getByText('컨텍스트 자동 압축 중')).toBeTruthy();
	expect(getByText('컨텍스트 자동 압축 완료')).toBeTruthy();
});

it('hides unfinished context compaction after its run ends', () => {
	const { queryByText } = render(ExecutionTimeline, {
		active: false,
		items: [
			{
				id: 'context:1',
				kind: 'context',
				seq: 1,
				createdAt: '2026-07-26T00:00:00Z',
				phase: 'compacting',
				cause: 'automatic',
				beforeTokens: 12000,
				afterTokens: null
			}
		]
	});
	expect(queryByText('컨텍스트 자동 압축 중')).toBeNull();
});
