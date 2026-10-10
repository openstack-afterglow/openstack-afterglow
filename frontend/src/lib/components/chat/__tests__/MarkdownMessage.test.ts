import { fireEvent, render, waitFor } from '@testing-library/svelte';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('$lib/api/chatMarkdown', () => ({
	renderMarkdown: () => '<pre><code>const answer = 42;</code></pre>',
	highlightCodeBlocks: vi.fn(async () => {})
}));
vi.mock('$lib/api/chatRichOutput', () => ({
	enhanceChatMarkdown: vi.fn(async () => {})
}));

import MarkdownMessage from '../MarkdownMessage.svelte';

describe('MarkdownMessage', () => {
	it('keeps the caret on the stable streaming surface, absent before first content and after completion', async () => {
		const view = render(MarkdownMessage, { content: '', streaming: true });
		const body = view.container.querySelector('.md-body');
		expect(body?.classList.contains('streaming')).toBe(false);
		await view.rerender({ content: '첫 토큰' });
		expect(view.container.querySelector('.md-body')).toBe(body);
		expect(body?.classList.contains('streaming')).toBe(true);
		await view.rerender({ content: '첫 토큰 다음 토큰' });
		expect(view.container.querySelector('.md-body')).toBe(body);
		expect(body?.classList.contains('motion-enter')).toBe(false);
		await view.rerender({ streaming: false });
		expect(body?.classList.contains('streaming')).toBe(false);
	});

	beforeEach(() => {
		Object.assign(navigator, { clipboard: { writeText: vi.fn(async () => {}) } });
	});

	it('installs an accessible code copy control and copies the source', async () => {
		const { getByRole } = render(MarkdownMessage, { content: '```ts\nconst answer = 42;\n```' });

		const copy = await waitFor(() => getByRole('button', { name: '코드 복사' }));
		expect(copy.classList.contains('chat-code-copy')).toBe(true);
		await fireEvent.click(copy);

		expect(navigator.clipboard.writeText).toHaveBeenCalledWith('const answer = 42;');
	});
});
