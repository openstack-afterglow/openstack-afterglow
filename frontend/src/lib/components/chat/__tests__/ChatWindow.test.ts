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

const historyMessage = (id: string, conversation_id = 'a') => ({
	id, conversation_id, parent_id: null, role: 'user' as const, content: id, created_at: null
});

// jsdom has no layout or native scroll anchoring. Model fixed-height DOM rows whose
// rectangles follow the actual row order and the current scrollTop after a prepend.
function historyGeometry(container: HTMLElement) {
	let currentScrollTop = 0;
	const getScroll = () => {
		const el = container.querySelector<HTMLDivElement>('.scroll')!;
		if (el && !Object.getOwnPropertyDescriptor(el, 'scrollTop')?.set) {
			Object.defineProperties(el, {
				scrollTop: {
					configurable: true,
					get: () => currentScrollTop,
					set: (v) => { currentScrollTop = v; }
				},
				scrollHeight: {
					configurable: true,
					get: () => el.querySelectorAll('[data-history-message-id]').length * 80
				},
				clientHeight: { configurable: true, value: 100 }
			});
		}
		return el;
	};
	getScroll();
	const original = Element.prototype.getBoundingClientRect;
	const geometry = vi.spyOn(Element.prototype, 'getBoundingClientRect').mockImplementation(function (this: Element) {
		const scroll = getScroll();
		if (this === scroll) return { top: 0, bottom: 100 } as DOMRect;
		if (this.hasAttribute('data-history-message-id')) {
			const rows = Array.from(scroll.querySelectorAll('[data-history-message-id]'));
			const top = rows.indexOf(this) * 80 - scroll.scrollTop;
			return { top, bottom: top + 80 } as DOMRect;
		}
		return original.call(this);
	});
	return {
		get scroll() { return getScroll(); },
		visible: () => {
			const scroll = getScroll();
			const row = Array.from(scroll.querySelectorAll<HTMLElement>('[data-history-message-id]'))
				.find((node) => node.getBoundingClientRect().bottom > 0);
			return { id: row?.dataset.historyMessageId, top: row?.getBoundingClientRect().top };
		},
		restore: () => geometry.mockRestore()
	};
}

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

	it('loads older messages on deliberate upward scroll and keeps the displayed row in place', async () => {
		const messages = ['answer', 'second', 'third', 'fourth', 'fifth'].map((id) => historyMessage(id));
		const pending = Promise.withResolvers<boolean>();
		const onLoadBefore = vi.fn(() => pending.promise);
		const props = { models: [], hasBefore: true, conversationKey: 'a', onLoadBefore, ...callbacks };
		const view = render(ChatWindow, { ...props, activePath: messages });
		await tick();
		const fixture = historyGeometry(view.container);
		const scroll = fixture.scroll;
		try {
			scroll.scrollTop = 300;
			await fireEvent.scroll(scroll);
			await fireEvent.wheel(scroll, { deltaY: -30 });
			expect(onLoadBefore).not.toHaveBeenCalled();
			scroll.scrollTop = 50;
			const before = fixture.visible();
			await fireEvent.scroll(scroll);
			await view.rerender({ ...props, activePath: [historyMessage('older-1'), historyMessage('older-2'), historyMessage('older-3'), ...messages] });
			pending.resolve(true);
			await tick();
			expect(onLoadBefore).toHaveBeenCalledOnce();
			expect(fixture.visible()).toEqual(before);
			expect(scroll.scrollTop).toBe(290);
		} finally {
			fixture.restore();
		}
	});

	it.each(['overscroll', 'down then up'])('preserves the latest visible row across a delayed prepend after %s', async (movement) => {
		const pending = Promise.withResolvers<boolean>();
		const onLoadBefore = vi.fn(() => pending.promise);
		const props = { models: [], hasBefore: true, conversationKey: 'a', onLoadBefore, ...callbacks };
		const current = [historyMessage('first'), historyMessage('second'), historyMessage('third'), historyMessage('fourth')];
		const view = render(ChatWindow, { ...props, activePath: current });
		await tick();
		const fixture = historyGeometry(view.container);
		const scroll = fixture.scroll;
		const wheelAt = async (timeStamp: number, deltaY: number) => {
			const wheel = new WheelEvent('wheel', { bubbles: true, deltaY });
			Object.defineProperty(wheel, 'timeStamp', { value: timeStamp });
			await fireEvent(scroll, wheel);
		};
		try {
			await wheelAt(1_000, -30);
			expect(onLoadBefore).toHaveBeenCalledOnce();
			if (movement === 'overscroll') {
				await wheelAt(1_050, -30);
				await fireEvent.touchStart(scroll, { touches: [{ clientY: 100 }] });
				await fireEvent.touchMove(scroll, { touches: [{ clientY: 140 }] });
			} else {
				await wheelAt(1_050, 120);
				scroll.scrollTop = 125;
				await fireEvent.scroll(scroll);
				scroll.scrollTop = 90;
				await fireEvent.scroll(scroll);
				await wheelAt(1_100, -30);
			}
			const before = fixture.visible();
			expect(before).toEqual(movement === 'overscroll' ? { id: 'first', top: 0 } : { id: 'second', top: -10 });
			await view.rerender({ ...props, activePath: [historyMessage('older-1'), historyMessage('older-2'), historyMessage('older-3'), ...current] });
			await tick();
			expect(fixture.visible()).toEqual(before);
			await wheelAt(1_150, -30);
			pending.resolve(true);
			await tick();
			await tick();
			await fireEvent.scroll(scroll); // synthetic programmatic scroll from compensation
			await wheelAt(1_200, -30); // same gesture's residual events
			expect(fixture.visible()).toEqual(before);
			expect(onLoadBefore).toHaveBeenCalledOnce();
		} finally {
			fixture.restore();
		}
	});

	it('keeps a short latest page on open but loads history on upward wheel input', async () => {
		const onLoadBefore = vi.fn(async () => true);
		const view = render(ChatWindow, {
			activePath: [{ id: 'first', conversation_id: 'a', parent_id: null, role: 'user', content: 'short page', created_at: null }],
			models: [], hasBefore: true, onLoadBefore, ...callbacks
		});
		await tick();
		const scroll = view.container.querySelector('.scroll') as HTMLDivElement;
		Object.defineProperties(scroll, {
			scrollTop: { configurable: true, value: 0, writable: true },
			scrollHeight: { configurable: true, value: 100 },
			clientHeight: { configurable: true, value: 100 }
		});
		await fireEvent.scroll(scroll);
		expect(onLoadBefore).not.toHaveBeenCalled();
		await fireEvent.wheel(scroll, { deltaY: -30 });
		expect(onLoadBefore).toHaveBeenCalledOnce();
	});

	it('requests one older page per upward touch gesture even when the transcript is short', async () => {
		const onLoadBefore = vi.fn(async () => true);
		const view = render(ChatWindow, {
			activePath: [{ id: 'first', conversation_id: 'a', parent_id: null, role: 'user', content: 'short mobile page', created_at: null }],
			models: [], hasBefore: true, onLoadBefore, ...callbacks
		});
		await tick();
		const scroll = view.getByRole('region', { name: '대화 기록' }) as HTMLDivElement;
		Object.defineProperties(scroll, {
			scrollTop: { configurable: true, value: 0, writable: true },
			scrollHeight: { configurable: true, value: 100 },
			clientHeight: { configurable: true, value: 100 }
		});
		await fireEvent.touchStart(scroll, { touches: [{ clientY: 100 }] });
		await fireEvent.touchMove(scroll, { touches: [{ clientY: 125 }] });
		await tick();
		expect(onLoadBefore).toHaveBeenCalledOnce();
		await fireEvent.touchMove(scroll, { touches: [{ clientY: 160 }] });
		expect(onLoadBefore).toHaveBeenCalledOnce();
		await fireEvent.touchStart(scroll, { touches: [{ clientY: 100 }] });
		await fireEvent.touchMove(scroll, { touches: [{ clientY: 125 }] });
		expect(onLoadBefore).toHaveBeenCalledTimes(2);
	});

	it('loads at most one page per wheel gesture, including programmatic scroll after restore', async () => {
		const onLoadBefore = vi.fn(async () => true);
		const view = render(ChatWindow, {
			activePath: [{ id: 'anchor', conversation_id: 'a', parent_id: null, role: 'user', content: 'reader', created_at: null }],
			models: [], hasBefore: true, onLoadBefore, ...callbacks
		});
		await tick();
		const scroll = view.getByRole('region', { name: '대화 기록' }) as HTMLDivElement;
		Object.defineProperties(scroll, {
			scrollTop: { configurable: true, value: 0, writable: true },
			scrollHeight: { configurable: true, value: 200 },
			clientHeight: { configurable: true, value: 100 }
		});
		const wheelAt = async (timeStamp: number) => {
			const event = new WheelEvent('wheel', { bubbles: true, deltaY: -100 });
			Object.defineProperty(event, 'timeStamp', { value: timeStamp });
			await fireEvent(scroll, event);
			await tick();
		};
		await wheelAt(1_000);
		expect(onLoadBefore).toHaveBeenCalledOnce();
		scroll.scrollTop = 50;
		await fireEvent.scroll(scroll);
		scroll.scrollTop = 0;
		await fireEvent.scroll(scroll);
		await wheelAt(1_050);
		expect(onLoadBefore).toHaveBeenCalledOnce();
		await wheelAt(1_500);
		expect(onLoadBefore).toHaveBeenCalledTimes(2);
	});

	it.each(['conversation', 'request fence'])('does not restore a stale view after changing the %s even with a shared message ID', async (change) => {
		const pending = Promise.withResolvers<boolean>();
		const onLoadBefore = vi.fn(() => pending.promise);
		const message = (conversation: string) => ({ ...historyMessage('shared-anchor', conversation), content: conversation });
		const props = { models: [], hasBefore: true, onLoadBefore, scrollFence: {}, ...callbacks };
		const conversationKey = change === 'conversation' ? 'b' : 'a';
		const view = render(ChatWindow, { ...props, conversationKey: 'a', activePath: [message('a'), historyMessage('tail', 'a')] });
		await tick();
		const fixture = historyGeometry(view.container);
		const scroll = fixture.scroll;
		try {
			await fireEvent.wheel(scroll, { deltaY: -30 });
			expect(onLoadBefore).toHaveBeenCalledOnce();
			const nextProps = { ...props, conversationKey, scrollFence: {}, activePath: [message('b'), historyMessage('tail-b1', 'b'), historyMessage('tail-b2', 'b'), historyMessage('tail-b3', 'b')] };
			await view.rerender(nextProps);
			await tick();
			scroll.scrollTop = 17;
			await fireEvent.scroll(scroll);
			await view.rerender({ ...nextProps, activePath: [historyMessage('b-older', 'b'), ...nextProps.activePath] });
			await tick();
			const newView = fixture.visible();
			expect(newView).toEqual({ id: 'b-older', top: -17 });
			pending.resolve(true);
			await tick();
			await tick();
			expect(fixture.visible()).toEqual(newView);
			expect(scroll.scrollTop).toBe(17);
			expect(view.getByText('b')).toBeTruthy();
		} finally {
			fixture.restore();
		}
	});

	it('shows a latest-window action when a run completes off-window', () => {
		const message = {
			id: 'answer', conversation_id: 'conversation', parent_id: null,
			role: 'assistant' as const, content: 'old window', created_at: null
		};
		const view = render(ChatWindow, {
			activePath: [message], models: [], newHistoryActivity: true,
			onLoadLatest: vi.fn(async () => true), ...callbacks
		});
		expect(view.getByText('새 응답이 도착했습니다.')).toBeTruthy();
		expect(view.getByRole('button', { name: '최신 응답 보기' })).toBeTruthy();
	});
});
