import { fireEvent, render, screen } from '@testing-library/svelte';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { initLocale } from '$lib/i18n/runtime.svelte';
import ChatMessage from '../ChatMessage.svelte';

function props(source_kind: 'web' | 'data_source', url: string) {
	return {
		message: { id: 'a1', conversation_id: 'conversation-1', role: 'assistant' as const, parent_id: null, content: '**Answer**', created_at: null, citations: [{ type: 'citation', citation_id: 'c1', source_id: 'record-1', source_kind, title: 'Dataset', url }] },
		models: [], onCopy: vi.fn(), onRegenerate: vi.fn(), onRetry: vi.fn(), onFork: vi.fn(), onPrevVersion: vi.fn(), onNextVersion: vi.fn()
	};
}
beforeEach(() => initLocale('ko'));

describe('registered citation link and Markdown copy consumers', () => {
	it.each(['web', 'data_source'] as const)('does not expose OAuth/TempURL credentials from %s sources as links or copied references', async (kind) => {
		for (const suffix of ['#access_token=secret', '#/callback?%69d_token=secret', '#private_token=secret', '?temp_url_sig=secret&temp_url_expires=123', '?client_secret=secret', '?api%2Dkey=secret']) {
			const input = props(kind, `https://git.example/data.csv${suffix}`);
			const view = render(ChatMessage, input);
			expect(view.queryByRole('link', { name: /Dataset/ })).toBeNull();
			expect(view.container.innerHTML).not.toContain('secret');
			await fireEvent.click(view.getByRole('button', { name: '복사' }));
			expect(input.onCopy).toHaveBeenCalledWith('**Answer**');
			view.unmount();
		}
	});
	it.each(['#section', '#authorization', '#token', '#key', '#api-key', '?q=password+reset', '?q=password+reset#section'])('keeps ordinary external record URL %s readable and portable through the actual copy button', async (suffix) => {
		const url = `https://git.example/org/repo/blob/main/data.csv${suffix}`;
		const input = props('data_source', url);
		render(ChatMessage, input);
		expect(screen.getByRole('link', { name: /Dataset/ }).getAttribute('href')).toBe(url);
		await fireEvent.click(screen.getByRole('button', { name: '복사' }));
		expect(input.onCopy).toHaveBeenCalledWith(expect.stringContaining(`[Dataset](<${url}>)`));
		expect(input.onCopy.mock.calls[0][0].startsWith('**Answer**')).toBe(true);
	});
});
