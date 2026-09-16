import { fireEvent, render } from '@testing-library/svelte';
import { tick } from 'svelte';
import { describe, expect, it, vi } from 'vitest';
import ChatWindow from '../ChatWindow.svelte';

const callbacks = {
	onCopy: () => {},
	onRegenerate: () => {},
	onRetry: () => {},
	onFork: () => {},
	onSwitchVersion: () => {}
};

describe('ChatWindow', () => {
	it('shows safe ordered sources above the corresponding answer while streaming and after reload', async () => {
		const message = {
			id: 'answer', conversation_id: 'conversation', parent_id: null,
			role: 'assistant' as const, content: '검색으로 확인한 답변입니다.', created_at: null,
			streaming: true,
			citations: [
				{ source_kind: 'web', url: 'https://docs.openstack.org/barbican/', title: 'Barbican 가이드' },
				{ source_kind: 'web', url: 'javascript:alert(1)', title: '실행 금지' },
				{ source_kind: 'document', document_index: 0, title: '첨부 문서' }
			]
		};
		const view = render(ChatWindow, { activePath: [message], models: [], ...callbacks });
		const source = view.getByRole('link', { name: /Barbican 가이드/ });
		expect(source.getAttribute('href')).toBe('https://docs.openstack.org/barbican/');
		expect(source.compareDocumentPosition(view.getByText(message.content)) & Node.DOCUMENT_POSITION_FOLLOWING).not.toBe(0);
		expect(view.queryByText('실행 금지')).toBeNull();
		expect(view.getByText('첨부 문서').closest('a')).toBeNull();
		await view.rerender({ activePath: [{ ...message, streaming: false }] });
		expect(view.getByRole('link', { name: /Barbican 가이드/ }).compareDocumentPosition(view.getByText(message.content)) & Node.DOCUMENT_POSITION_FOLLOWING).not.toBe(0);
	});
	it('shows a user-facing active task and elapsed time', () => {
		const { getByRole } = render(ChatWindow, {
			activePath: [],
			models: [],
			agentActivity: {
				label: '웹 검색 진행 중',
				startedAt: new Date(Date.now() - 2_000).toISOString()
			},
			...callbacks
		});

		const status = getByRole('status');
		expect(status.textContent).toContain('웹 검색 진행 중');
		expect(status.textContent).toContain('초');
	});

	it('shows manual context compaction as chat-window activity before other run activity', () => {
		const { getByRole, queryByText } = render(ChatWindow, {
			activePath: [],
			models: [],
			manualCompactionActivity: '컨텍스트 압축 중',
			agentActivity: {
				label: '응답을 작성 중',
				startedAt: new Date().toISOString()
			},
			...callbacks
		});

		expect(getByRole('status').textContent).toContain('컨텍스트 압축 중');
		expect(queryByText('응답을 작성 중')).toBeNull();
	});


	it('renders the mapped tool task instead of a backend identifier', () => {
		const { getByRole, queryByText } = render(ChatWindow, {
			activePath: [],
			models: [],
			toolActivity: '웹 검색',
			...callbacks
		});

		expect(getByRole('status').textContent).toContain('웹 검색 진행 중');
		expect(queryByText(/managed_web_search|mcp__/)).toBeNull();
	});

	it('inserts a Lumen starter prompt through the normal chat input callback', async () => {
		const onStarterPrompt = vi.fn();
		const { getByRole } = render(ChatWindow, {
			activePath: [],
			models: [],
			empty: true,
			starterPrompts: [{ label: '프로젝트 현황', prompt: '현재 프로젝트를 요약해 주세요.' }],
			onStarterPrompt,
			...callbacks
		});

		await fireEvent.click(getByRole('button', { name: '프로젝트 현황' }));

		expect(onStarterPrompt).toHaveBeenCalledWith('현재 프로젝트를 요약해 주세요.');
	});

	it('renders a non-empty conversation without an undefined component error', () => {
		const { getByText } = render(ChatWindow, {
			activePath: [
				{
					id: 'message-1',
					conversation_id: 'conversation-1',
					role: 'user',
					parent_id: null,
					content: '확인할 메시지',
					created_at: '2026-07-23T00:00:00Z'
				}
			],
			models: [],
			...callbacks
		});

		expect(getByText('확인할 메시지')).toBeTruthy();
	});

	it('renders durable tool activity and its execution time inside the final assistant bubble', () => {
		const { container, getByText } = render(ChatWindow, {
			activePath: [
				{
					id: 'user-1',
					conversation_id: 'conversation-1',
					role: 'user',
					parent_id: null,
					content: 'Notion을 검색해 주세요.',
					created_at: '2026-07-28T00:00:00Z'
				},
				{
					id: 'assistant-tool-1',
					conversation_id: 'conversation-1',
					role: 'assistant',
					parent_id: 'user-1',
					content: '',
					parts: [
						{
							type: 'tool_call',
							call_id: 'call-1',
							name: 'mcp__1__notion_search',
							arguments: { query: 'Notion' },
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
					execution: { tool_durations_ms: { 'call-1': 840 } },
					created_at: '2026-07-28T00:00:01Z'
				},
				{
					id: 'assistant-final-1',
					conversation_id: 'conversation-1',
					role: 'assistant',
					parent_id: 'assistant-tool-1',
					content: '검색 결과입니다.',
					created_at: '2026-07-28T00:00:02Z'
				}
			],
			models: [],
			...callbacks
		});

		expect(container.querySelectorAll('article.chat')).toHaveLength(2);
		expect(getByText('MCP: Notion Search')).toBeTruthy();
		expect(getByText('840ms')).toBeTruthy();
		expect(getByText('검색 결과입니다.')).toBeTruthy();
	});

	it('attaches persisted execution activity to the final assistant bubble', async () => {
		const { container, getByLabelText, getByText } = render(ChatWindow, {
			activePath: [
				{
					id: 'user-1',
					conversation_id: 'conversation-1',
					role: 'user',
					parent_id: null,
					content: '문서를 찾아 주세요.',
					created_at: '2026-07-28T00:00:00Z'
				},
				{
					id: 'assistant-final-1',
					conversation_id: 'conversation-1',
					role: 'assistant',
					parent_id: 'user-1',
					content: '검색 결과입니다.',
					execution: {
						activity: [
							{
								id: 'reasoning:1',
								kind: 'reasoning',
								seq: 1,
								createdAt: '2026-07-28T00:00:01Z',
								text: '검색 범위를 정리합니다.',
								active: false
							},
							{
								id: 'tool:call-1',
								kind: 'tool',
								seq: 2,
								createdAt: '2026-07-28T00:00:02Z',
								callId: 'call-1',
								name: 'mcp__1__notion_search',
								source: 'mcp',
								category: 'MCP · Notion',
								arguments: { query: 'Afterglow' },
								status: 'completed',
								content: [{ type: 'text', text: 'found' }],
								errorCode: null,
								durationMs: 840
							}
						]
					},
					created_at: '2026-07-28T00:00:03Z'
				}
			],
			models: [],
			...callbacks
		});

		expect(container.querySelectorAll('article.chat')).toHaveLength(2);
		const summary = getByLabelText('작업 내역 열기');
		expect((summary.closest('details') as HTMLDetailsElement).open).toBe(false);
		await fireEvent.click(summary);
		expect(getByText('MCP · Notion')).toBeTruthy();
		expect(getByText('검색 결과입니다.')).toBeTruthy();
	});

	it('shows a visible retry action for a failed user turn and invokes it', async () => {
		const onRetry = vi.fn();
		const { getByRole, getByText } = render(ChatWindow, {
			activePath: [
				{
					id: 'failed-user-message',
					conversation_id: 'conversation-1',
					role: 'user',
					parent_id: null,
					content: '다시 전송할 메시지',
					execution: { run_id: 'run-failed', status: 'failed', retryable: true },
					created_at: '2026-07-23T00:00:00Z'
				}
			],
			models: [],
			...callbacks,
			onRetry
		});

		expect(getByText('응답 생성에 실패했습니다')).toBeTruthy();
		await fireEvent.click(getByRole('button', { name: '다시 전송' }));
		expect(onRetry).toHaveBeenCalledOnce();
		expect(onRetry).toHaveBeenCalledWith('failed-user-message');
	});

	it('uses start/end chat anatomy with role metadata and a compact corner tail', () => {
		const { container, getByText } = render(ChatWindow, {
			activePath: [
				{
					id: 'message-1',
					conversation_id: 'conversation-1',
					role: 'user',
					parent_id: null,
					content: '배포 상태를 확인해 주세요.',
					created_at: '2026-07-23T00:00:00Z'
				},
				{
					id: 'message-2',
					conversation_id: 'conversation-1',
					role: 'assistant',
					parent_id: 'message-1',
					content: '현재 배포는 정상입니다.',
					model_name: 'afterglow-chat',
					created_at: '2026-07-23T00:01:00Z'
				}
			],
			models: [{ id: 1, model_name: 'afterglow-chat', display_name: 'Afterglow Chat' }],
			...callbacks
		});

		const chats = container.querySelectorAll('article.chat');
		expect(chats).toHaveLength(2);
		expect(chats[0].classList.contains('chat-end')).toBe(true);
		expect(chats[0].querySelector('.chat-header')).toBeTruthy();
		expect(chats[0].querySelector('.chat-bubble')).toBeTruthy();
		expect(chats[0].querySelector('.chat-footer')).toBeTruthy();
		expect(chats[1].classList.contains('chat-start')).toBe(true);
		expect(chats[1].querySelector('.chat-bubble')).toBeTruthy();
		expect(getByText('나')).toBeTruthy();
		expect(getByText('Afterglow')).toBeTruthy();
		expect(getByText('Afterglow Chat')).toBeTruthy();
	});

	it('shows an explicit follow control after the reader scrolls away from streaming output', async () => {
		const { container, getByRole } = render(ChatWindow, {
			activePath: [],
			models: [],
			busy: true,
			...callbacks
		});
		await tick();
		const scroll = container.querySelector('.scroll') as HTMLDivElement;
		Object.defineProperties(scroll, {
			scrollHeight: { configurable: true, value: 1_000 },
			clientHeight: { configurable: true, value: 100 },
			scrollTop: { configurable: true, value: 0, writable: true }
		});

		await fireEvent.scroll(scroll);
		await tick();

		expect(getByRole('button', { name: '새 응답 따라가기' })).toBeTruthy();
	});

	it('preserves scroll offset while its older-history callback prepends messages', async () => {
		let scroll: HTMLDivElement;
		const onLoadOlder = vi.fn(async () => {
			Object.defineProperty(scroll, 'scrollHeight', { configurable: true, value: 1_200 });
		});
		const { container } = render(ChatWindow, {
			activePath: [],
			models: [],
			hasOlder: true,
			onLoadOlder,
			...callbacks
		});
		scroll = container.querySelector('.scroll') as HTMLDivElement;
		Object.defineProperties(scroll, {
			scrollHeight: { configurable: true, value: 1_000 },
			clientHeight: { configurable: true, value: 100 },
			scrollTop: { configurable: true, value: 0, writable: true }
		});

		await fireEvent.scroll(scroll);

		expect(onLoadOlder).toHaveBeenCalledOnce();
		expect(scroll.scrollTop).toBe(200);
	});
});
