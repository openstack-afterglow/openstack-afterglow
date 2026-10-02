import { render } from '@testing-library/svelte';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import ChatBubbleFixture from './ChatBubbleFixture.svelte';

const componentSource = readFileSync(resolve(__dirname, '../ChatBubble.svelte'), 'utf8');

describe('ChatBubble', () => {
	it('renders semantic start/end messages with metadata and an optional footer', () => {
		const { container } = render(ChatBubbleFixture);
		const messages = container.querySelectorAll('article.chat-message');

		expect(messages).toHaveLength(2);
		expect(messages[0].classList.contains('chat-start')).toBe(true);
		expect(messages[0].querySelector('.chat-header time')?.getAttribute('datetime')).toBe(
			'2026-07-26T08:43:00Z'
		);
		expect(messages[1].classList.contains('chat-end')).toBe(true);
		expect(messages[1].querySelector('.chat-bubble')?.textContent).toContain('첫 줄');
		expect(messages[1].querySelector('.chat-bubble')?.textContent).toContain(
			'verylongunbrokenmessagetokenwithoutspacesmustremaincontainedinthebubble'
		);
	});

	it('uses shared chat message tokens instead of local dimensions or colors', () => {
		expect(componentSource).toContain('var(--chat-message-gap)');
		expect(componentSource).toContain('var(--chat-message-directional-corner)');
		expect(componentSource).toContain('var(--chat-message-assistant-max-inline)');
		expect(componentSource).toContain('var(--chat-message-user-max-inline)');
		expect(componentSource).toContain('var(--color-surface-raised)');
		expect(componentSource).toContain('var(--color-accent)');
		expect(componentSource).toMatch(
			/\.chat-end \.chat-bubble \{[\s\S]*white-space: pre-wrap;[\s\S]*word-break: break-word;[\s\S]*overflow-wrap: anywhere;/
		);
		expect(componentSource).not.toMatch(/#[0-9a-f]{3,8}\b/i);
	});
});
