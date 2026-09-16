import { fireEvent, render, waitFor } from '@testing-library/svelte';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('$lib/api/chatAttachments', async (importOriginal) => {
	const actual = await importOriginal<typeof import('$lib/api/chatAttachments')>();
	return { ...actual, uploadChatAttachment: vi.fn() };
});

import ChatInput from '../ChatInput.svelte';
import { uploadChatAttachment } from '$lib/api/chatAttachments';

beforeEach(() => {
	vi.mocked(uploadChatAttachment).mockReset();
	vi.stubGlobal('matchMedia', (query: string) => ({
		matches: query.includes('min-width: 768px') || query.includes('prefers-reduced-motion'),
		media: query,
		addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
		dispatchEvent: () => false, onchange: null
	}));
	Object.defineProperty(URL, 'createObjectURL', {
		configurable: true,
		value: vi.fn(() => 'blob:preview')
	});
	Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: vi.fn() });
});

describe('ChatInput native Search', () => {
	const props = { value: '', onSend: vi.fn(), onStop: vi.fn() };
	const nativeSearch = {
		web_search: true,
		feature_gates: { web_search: { available: true, mode: 'native' as const, reason_code: null, pricing_available: true } }
	};

	it('lets users enable and disable optional native search', async () => {
		const view = render(ChatInput, { ...props, modelCaps: nativeSearch });
		const search = view.getByRole('button', { name: 'Search 웹 검색' });
		await fireEvent.click(search);
		expect(search.getAttribute('aria-pressed')).toBe('true');
		await fireEvent.click(search);
		expect(search.getAttribute('aria-pressed')).toBe('false');
	});

	it('does not offer an opt-in for a model with built-in required search', () => {
		const view = render(ChatInput, { ...props, modelCaps: { ...nativeSearch, web_search_required: true } });
		const search = view.getByRole('button', { name: 'Search 웹 검색' }) as HTMLButtonElement;
		search.click();
		expect(search.disabled).toBe(true);
		expect(search.getAttribute('aria-pressed')).toBe('true');
	});

	it('blocks opt-in when native search pricing is unavailable', () => {
		const view = render(ChatInput, { ...props, modelCaps: {
			...nativeSearch,
			feature_gates: { web_search: { ...nativeSearch.feature_gates.web_search, pricing_available: false } }
		} });
		const search = view.getByRole('button', { name: 'Search 웹 검색' }) as HTMLButtonElement;
		search.click();
		expect(search.disabled).toBe(true);
		expect(search.getAttribute('aria-pressed')).toBe('false');
	});

	it('does not mistake a managed search route for a native API option', () => {
		const view = render(ChatInput, { ...props, modelCaps: {
			...nativeSearch,
			feature_gates: { web_search: { ...nativeSearch.feature_gates.web_search, mode: 'managed' } }
		} });
		expect(view.queryByRole('button', { name: 'Search 웹 검색' })).toBeNull();
	});
});

describe('ChatInput attachments', () => {
	it('marks a scanned image ready instead of leaving the composer upload-blocked', async () => {
		vi.mocked(uploadChatAttachment).mockResolvedValue({
			id: 'asset-clean',
			mime_type: 'image/png',
			name: 'clean.png'
		});
		const { container } = render(ChatInput, {
			value: '',
			modelCaps: { vision: true },
			onSend: vi.fn(),
			onStop: vi.fn()
		});
		const input = container.querySelector<HTMLInputElement>('input[type="file"]');
		expect(input).toBeTruthy();
		const file = new File(['image'], 'clean.png', { type: 'image/png' });
		Object.defineProperty(input!, 'files', { configurable: true, value: [file] });

		await fireEvent.change(input!);

		await waitFor(() => expect(container.querySelector('.chip.uploading')).toBeNull());
		expect(container.querySelector<HTMLImageElement>('.chip img')?.alt).toBe('clean.png');
	});

	it('explains when the scanned asset pipeline is unavailable', () => {
		const { container } = render(ChatInput, {
			value: '',
			modelCaps: {
				vision: true,
				feature_gates: {
					image_input: {
						available: false,
						mode: 'none',
						reason_code: 'asset_pipeline_unavailable',
						pricing_available: false
					}
				}
			},
			onSend: vi.fn(),
			onStop: vi.fn()
		});

		expect(container.querySelector<HTMLButtonElement>('.tool-shell')?.disabled).toBe(true);
	});
});

describe('ChatInput compact context meter', () => {
	it('keeps measured context use inside the composer controls', async () => {
		const view = render(ChatInput, {
			value: '',
			hasContextScope: true,
			contextState: {
				model_name: 'gpt-5',
				context_limit: 16_384,
				output_reserve: 2_048,
				safety_reserve: 512,
				input_budget: 13_824,
				input_tokens: 4_147,
				utilization: 0.3,
				measurement: 'estimated',
				recommendation: 'none',
				can_compact: false,
				reason_code: 'no_prior_turn',
				revision: 'context-r1',
				checkpoint_id: null,
				active_compaction_run_id: null
			},
			onSend: vi.fn(),
			onStop: vi.fn()
		});

		const meter = view.getByRole('meter', { name: '컨텍스트 입력 예산 사용률' });
		expect(meter.getAttribute('aria-valuenow')).toBe('30');
		const details = view.getByRole('button', { name: '컨텍스트 용량 세부 정보' });
		await fireEvent.click(details);
		expect(view.getByRole('dialog', { name: '컨텍스트 윈도우' })).toBeTruthy();
		expect(view.queryByText('대화 메시지·초안')).toBeNull();
	});

	it('does not invent a zero percent meter for unknown context usage', async () => {
		const view = render(ChatInput, {
			value: '',
			hasContextScope: true,
			contextState: {
				model_name: 'gpt-5',
				context_limit: null,
				output_reserve: 2_048,
				safety_reserve: 512,
				input_budget: null,
				input_tokens: null,
				utilization: null,
				measurement: 'unknown',
				recommendation: 'unavailable',
				can_compact: false,
				reason_code: 'context_window_unknown',
				revision: 'context-r2',
				checkpoint_id: null,
				active_compaction_run_id: null
			},
			onSend: vi.fn(),
			onStop: vi.fn()
		});

		expect(view.queryByRole('meter')).toBeNull();
		const explanation = view.getByRole('button', { name: '컨텍스트를 표시할 수 없는 이유' });
		expect(explanation.getAttribute('aria-expanded')).toBe('false');
		await fireEvent.click(explanation);
		expect(explanation.getAttribute('aria-expanded')).toBe('true');
		const panel = view.getByRole('dialog', { name: '컨텍스트 윈도우' });
		expect(view.queryByRole('meter')).toBeNull();
		await fireEvent.keyDown(panel, { key: 'Escape' });
		await waitFor(() => expect(view.queryByRole('dialog')).toBeNull());
		expect(document.activeElement).toBe(explanation);
		expect(explanation.getAttribute('aria-expanded')).toBe('false');
	});

	it('uses the full model denominator and excludes deferred tools from current capacity', async () => {
		const state = {
			model_name: 'sonar', context_limit: 16000, output_reserve: 2000, safety_reserve: 1000,
			input_budget: 13000, input_tokens: 4000, utilization: 4000 / 13000,
			measurement: 'estimated' as const, recommendation: 'none' as const, can_compact: false,
			reason_code: null, revision: 'r1', checkpoint_id: null, active_compaction_run_id: null,
			breakdown: { scope: 'preview' as const, complete: true, uncounted: [] as string[], components: [
				{ id: 'messages', tokens: 3000, measurement: 'estimated' as const, count: 2, included: true, items: ['user:1', 'assistant:2'] },
				{ id: 'tools', tokens: 1000, measurement: 'estimated' as const, count: 1, included: true, items: ['tool_catalog_search'] },
				{ id: 'deferred_tools', tokens: 7000, measurement: 'estimated' as const, count: 5, included: false, items: ['Research server'] }
			] }
		};
		const view = render(ChatInput, { value: '', hasContextScope: true, contextState: state, onSend: vi.fn(), onStop: vi.fn() });
		await fireEvent.click(view.getByRole('button', { name: '컨텍스트 용량 세부 정보' }));
		const messageRow = view.getByText('대화 메시지·초안', { exact: false }).closest('summary')!;
		expect(messageRow.textContent).toContain('18.8%');
		expect(view.queryByText('7,000')).toBeNull();
		expect(view.getByText('남은 입력 용량').parentElement?.textContent).toContain('9,000');
		await view.rerender({ contextState: { ...state, breakdown: {
			...state.breakdown, complete: false, uncounted: ['mcp_tools'], components: [
				...state.breakdown.components,
				{ id: 'mcp_tools', tokens: null, measurement: 'unknown' as const, count: null, included: false, items: ['Preloaded MCP'] }
			]
		} } });
		expect(view.queryByRole('meter')).toBeNull();
		expect(view.getByText('남은 입력 용량').parentElement?.textContent).not.toContain('9,000');
	});

});


describe('ChatInput shortcuts', () => {
	it('binds an @ mention to the selected agent', async () => {
		const onSelectAgent = vi.fn();
		const { getByRole } = render(ChatInput, {
			value: '@ops',
			availableAgents: [{ id: 7, name: 'ops-reviewer' }],
			onSelectAgent,
			onSend: vi.fn(),
			onStop: vi.fn()
		});

		await fireEvent.click(getByRole('option', { name: /ops-reviewer.*에이전트/i }));
		expect(onSelectAgent).toHaveBeenCalledWith(7);
	});

	it('shows a slash skill suggestion without pretending it is an unrestricted shell command', () => {
		const { getByRole } = render(ChatInput, {
			value: '/research',
			availableSkills: [{ id: 3, name: 'research' }],
			onSend: vi.fn(),
			onStop: vi.fn()
		});

		expect(getByRole('option', { name: /research.*스킬/i })).toBeTruthy();
	});


	it('executes a supplied slash command instead of treating it as a skill', async () => {
		const onSelect = vi.fn();
		const { getByRole } = render(ChatInput, {
			value: '/',
			composerCommands: [
				{
					id: 'compact',
					name: '압축',
					description: '이전 대화를 요약해 컨텍스트를 확보합니다',
					onSelect
				}
			],
			onSend: vi.fn(),
			onStop: vi.fn()
		});

		await fireEvent.click(getByRole('option', { name: /압축.*컨텍스트.*명령/i }));
		expect(onSelect).toHaveBeenCalledOnce();
	});

	it('shows a non-actionable reason for disabled slash commands', async () => {
		const onSelect = vi.fn();
		const { getByRole } = render(ChatInput, {
			value: '/',
			composerCommands: [
				{
					id: 'compact',
					name: '압축',
					description: '이전 대화를 요약해 컨텍스트를 확보합니다',
					disabled: true,
					disabledReason: '아직 압축할 이전 대화가 없습니다',
					onSelect
				}
			],
			onSend: vi.fn(),
			onStop: vi.fn()
		});
		const option = getByRole('option', { name: /압축.*아직 압축할 이전 대화가 없습니다/i });

		expect((option as HTMLButtonElement).disabled).toBe(true);
		await fireEvent.click(option);
		expect(onSelect).not.toHaveBeenCalled();
	});
	it('filters slash commands from text typed after the trigger', async () => {
		const view = render(ChatInput, {
			value: '/',
			composerCommands: [
				{ id: 'compact', name: '압축', description: '컨텍스트를 확보합니다', onSelect: vi.fn() },
				{ id: 'usage', name: '사용량', description: '사용량을 확인합니다', onSelect: vi.fn() }
			],
			onSend: vi.fn(),
			onStop: vi.fn()
		});

		await fireEvent.input(view.getByRole('textbox'), { target: { value: '/사용' } });

		expect(view.getByRole('option', { name: /사용량/i })).toBeTruthy();
		expect(view.queryByRole('option', { name: /압축/i })).toBeNull();
	});

	it('moves the active slash command with arrow keys and wraps upward', async () => {
		const view = render(ChatInput, {
			value: '/',
			composerCommands: [
				{ id: 'compact', name: '압축', description: '컨텍스트를 확보합니다', onSelect: vi.fn() },
				{ id: 'usage', name: '사용량', description: '사용량을 확인합니다', onSelect: vi.fn() }
			],
			onSend: vi.fn(),
			onStop: vi.fn()
		});
		const textarea = view.getByRole('textbox');
		const compact = view.getByRole('option', { name: /압축/i });
		const usage = view.getByRole('option', { name: /사용량/i });

		expect(compact.getAttribute('aria-selected')).toBe('true');
		await fireEvent.keyDown(textarea, { key: 'ArrowDown' });
		expect(usage.getAttribute('aria-selected')).toBe('true');
		await fireEvent.keyDown(textarea, { key: 'ArrowUp' });
		expect(compact.getAttribute('aria-selected')).toBe('true');
		await fireEvent.keyDown(textarea, { key: 'ArrowUp' });
		expect(usage.getAttribute('aria-selected')).toBe('true');
	});

	it('autocompletes the active command with Tab without executing it', async () => {
		const onSelect = vi.fn();
		const view = render(ChatInput, {
			value: '/',
			composerCommands: [
				{ id: 'new-project', name: '새 프로젝트', description: '프로젝트를 만듭니다', onSelect }
			],
			onSend: vi.fn(),
			onStop: vi.fn()
		});
		const textarea = view.getByRole('textbox') as HTMLTextAreaElement;

		await fireEvent.keyDown(textarea, { key: 'Tab' });

		expect(textarea.value).toBe('/새 프로젝트 ');
		expect(onSelect).not.toHaveBeenCalled();
	});

	it('executes an exact slash command with Enter instead of sending it as chat text', async () => {
		const onSelect = vi.fn();
		const onSend = vi.fn();
		const view = render(ChatInput, {
			value: '/모델 선택',
			composerCommands: [
				{ id: 'select-model', name: '모델 선택', description: '모델을 선택합니다', onSelect }
			],
			onSend,
			onStop: vi.fn()
		});

		await fireEvent.keyDown(view.getByRole('textbox'), { key: 'Enter' });

		expect(onSelect).toHaveBeenCalledOnce();
		expect(onSend).not.toHaveBeenCalled();
	});

	it('opens extensible quick-add actions from the at-sign trigger', async () => {
		const view = render(ChatInput, {
			value: '@',
			modelCaps: { vision: true, tool_call: true },
			availableTools: [{ id: 1, name: '검색' }],
			onSend: vi.fn(),
			onStop: vi.fn()
		});
		const fileInput = view.container.querySelector<HTMLInputElement>('input[type="file"]')!;
		const click = vi.spyOn(fileInput, 'click');

		await waitFor(() =>
			expect(view.getAllByRole('option').map((option) => option.textContent)).toEqual(
				expect.arrayContaining([
					expect.stringMatching(/파일 첨부.*추가/i),
					expect.stringMatching(/도구 및 스킬.*추가/i)
				])
			)
		);
		await fireEvent.click(view.getByRole('option', { name: /파일 첨부.*추가/i }));

		expect(click).toHaveBeenCalledOnce();
	});
	it('does not dispatch a hidden agent shortcut while streaming', async () => {
		const onSelectAgent = vi.fn();
		const view = render(ChatInput, {
			value: '@ops',
			streaming: true,
			availableAgents: [{ id: 7, name: 'ops-reviewer' }],
			onSelectAgent,
			onSend: vi.fn(),
			onStop: vi.fn()
		});
		const textarea = view.getByRole('textbox') as HTMLTextAreaElement;

		expect(view.queryByRole('listbox')).toBeNull();
		await fireEvent.keyDown(textarea, { key: 'ArrowDown' });
		await fireEvent.keyDown(textarea, { key: 'Tab' });
		await fireEvent.keyDown(textarea, { key: 'Enter' });

		expect(onSelectAgent).not.toHaveBeenCalled();
		expect(textarea.value).toBe('@ops');
		expect(textarea.getAttribute('aria-activedescendant')).toBeNull();
	});

	it('does not execute an exact slash command while streaming', async () => {
		const onSelect = vi.fn();
		const onSend = vi.fn();
		const view = render(ChatInput, {
			value: '/압축',
			streaming: true,
			composerCommands: [
				{ id: 'compact', name: '압축', description: '컨텍스트를 확보합니다', onSelect }
			],
			onSend,
			onStop: vi.fn()
		});

		await fireEvent.keyDown(view.getByRole('textbox'), { key: 'Enter' });

		expect(onSelect).not.toHaveBeenCalled();
		expect(onSend).not.toHaveBeenCalled();
	});
});

describe('ChatInput send-only suspension', () => {
	it('keeps editing and attachments available while preventing both Enter and button sends', async () => {
		const onSend = vi.fn();
		const view = render(ChatInput, {
			value: '보존할 초안',
			sendDisabled: true,
			modelCaps: { vision: true },
			onSend,
			onStop: vi.fn()
		});
		const textarea = view.getByRole('textbox') as HTMLTextAreaElement;
		expect(textarea.disabled).toBe(false);
		await fireEvent.input(textarea, { target: { value: '압축 중에도 수정한 초안' } });
		await fireEvent.keyDown(textarea, { key: 'Enter' });
		const send = view.getByRole('button', { name: '전송' }) as HTMLButtonElement;
		expect(send.disabled).toBe(true);
		send.click();
		expect(onSend).not.toHaveBeenCalled();
		expect(textarea.value).toBe('압축 중에도 수정한 초안');
		expect(view.container.querySelector<HTMLButtonElement>('.tool-shell')?.disabled).toBe(false);

		await view.rerender({ sendDisabled: false });
		await fireEvent.keyDown(textarea, { key: 'Enter' });
		expect(onSend).toHaveBeenCalledOnce();
	});
});
