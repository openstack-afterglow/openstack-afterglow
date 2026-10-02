<script lang="ts">
	import { t } from '$lib/i18n/ns/chat-studio';
	import { renderMarkdown, highlightCodeBlocks } from '$lib/api/chatMarkdown';
	import { enhanceChatMarkdown } from '$lib/api/chatRichOutput';
	import 'katex/dist/katex.min.css';

	interface Props {
		content: string;
		/** 스트리밍 중이면 코드 하이라이트를 미룬다(델타마다 재하이라이트 방지). */
		streaming?: boolean;
	}
	let { content, streaming = false }: Props = $props();

	let host = $state<HTMLDivElement | null>(null);
	// 스트리밍 중에는 캐시 미사용(매 델타 partial), 완료 후에는 content-keyed 캐시로 재파싱 방지.
	const html = $derived(renderMarkdown(content, { cache: !streaming }));


	async function copyCode(button: HTMLButtonElement, code: string) {
		try {
			if (navigator.clipboard?.writeText) {
				await navigator.clipboard.writeText(code);
			} else {
				const textarea = document.createElement('textarea');
				textarea.value = code;
				textarea.setAttribute('readonly', '');
				textarea.style.cssText = 'position:fixed;opacity:0';
				document.body.append(textarea);
				textarea.select();
				const copied = document.execCommand('copy');
				textarea.remove();
				if (!copied) throw new Error('copy command rejected');
			}
			button.textContent = t('markdownMessage.copied');
			window.setTimeout(() => {
				if (button.isConnected) button.textContent = t('markdownMessage.copy');
			}, 1_400);
		} catch {
			button.textContent = t('markdownMessage.failed');
			window.setTimeout(() => {
				if (button.isConnected) button.textContent = t('markdownMessage.copy');
			}, 1_400);
		}
	}

	function installCodeCopyButtons(el: HTMLDivElement) {
		for (const pre of el.querySelectorAll('pre')) {
			if (pre.querySelector(':scope > .chat-code-copy')) continue;
			const code = pre.querySelector('code')?.textContent ?? pre.textContent ?? '';
			if (!code) continue;
			const button = document.createElement('button');
			button.type = 'button';
			button.className = 'chat-code-copy';
			button.textContent = t('markdownMessage.copy');
			button.ariaLabel = t('markdownMessage.copyCode');
			button.title = t('markdownMessage.copyCode');
			button.addEventListener('click', () => void copyCode(button, code));
			pre.append(button);
		}
	}
	// 스트리밍이 끝나고 최종 HTML 이 DOM 에 반영된 뒤 한 번만 하이라이트.
	$effect(() => {
		void html;
		const el = host;
		if (!el || streaming) return;
		// 마이크로태스크 이후 DOM 반영 보장
		queueMicrotask(() => {
			if (host === el && !streaming) {
				void (async () => {
					await highlightCodeBlocks(el);
					if (host === el && !streaming) {
						await enhanceChatMarkdown(el);
						if (host === el && !streaming) installCodeCopyButtons(el);
					}
				})();
			}
		});
	});
</script>

<div bind:this={host} class="md-body" class:streaming>
	<!-- renderMarkdown 이 DOMPurify.sanitize 로 살균한 HTML -->
	{@html html}
</div>

<style>
	.md-body {
		font-size: 0.875rem;
		line-height: 1.65;
		color: var(--color-ink-1);
		word-break: break-word;
		overflow-wrap: anywhere;
	}
	.md-body.streaming::after {
		content: '';
		display: inline-block;
		width: 0.45rem;
		height: 1.05em;
		margin-left: 0.14rem;
		vertical-align: -0.16em;
		border-radius: 1px;
		background: var(--color-accent);
		animation: stream-cursor-blink 0.9s steps(1, end) infinite;
	}
	.md-body :global(.math-display) {
		display: block;
		margin: 0.8rem 0;
		padding: 0.65rem 0.8rem;
		overflow-x: auto;
		border: 1px solid var(--color-line);
		border-radius: 0.55rem;
		background: var(--color-surface-sunken);
		color: var(--color-ink-0);
	}
	.md-body :global(.math-inline .katex) {
		font-size: 1em;
	}
	.md-body :global(.mermaid-diagram) {
		display: grid;
		place-items: center;
		margin: 0 0 0.75rem;
		padding: 0.9rem;
		overflow-x: auto;
		border: 1px solid var(--color-line);
		border-radius: 0.6rem;
		background: var(--color-surface-sunken);
	}
	.md-body :global(.mermaid-diagram svg) {
		max-width: 100%;
		height: auto;
	}
	.md-body :global(pre[data-mermaid-error]) {
		border-color: var(--color-state-warning);
	}
	@keyframes stream-cursor-blink {
		50% { opacity: 0; }
	}
	@media (prefers-reduced-motion: reduce) {
		.md-body.streaming::after { animation: none; }
	}
	.md-body :global(p) {
		margin: 0 0 0.75em;
	}
	.md-body :global(p:last-child) {
		margin-bottom: 0;
	}
	.md-body :global(h1),
	.md-body :global(h2),
	.md-body :global(h3),
	.md-body :global(h4) {
		margin: 1.1em 0 0.5em;
		font-weight: 650;
		line-height: 1.3;
		color: var(--color-ink-0);
	}
	.md-body :global(h1) { font-size: 1.35em; }
	.md-body :global(h2) { font-size: 1.2em; }
	.md-body :global(h3) { font-size: 1.05em; }
	.md-body :global(ul),
	.md-body :global(ol) {
		margin: 0 0 0.75em;
		padding-left: 1.4em;
	}
	.md-body :global(li) {
		margin: 0.2em 0;
	}
	.md-body :global(li > p) {
		margin: 0;
	}
	.md-body :global(a) {
		color: var(--color-accent);
		text-decoration: underline;
		text-underline-offset: 2px;
	}
	.md-body :global(a:hover) {
		color: color-mix(in oklab, var(--color-accent) 75%, var(--color-ink-0));
	}
	.md-body :global(blockquote) {
		margin: 0 0 0.75em;
		padding: 0.25em 0 0.25em 0.9em;
		border-left: 3px solid var(--color-line-2);
		color: var(--color-ink-2);
	}
	.md-body :global(hr) {
		border: none;
		border-top: 1px solid var(--color-line);
		margin: 1.2em 0;
	}
	/* 인라인 코드 */
	.md-body :global(:not(pre) > code) {
		font-family: var(--font-mono, ui-monospace, SFMono-Regular, Menlo, monospace);
		font-size: 0.85em;
		padding: 0.12em 0.38em;
		border-radius: 0.35rem;
		background: var(--color-surface-sunken);
		border: 1px solid var(--color-line);
		color: var(--color-ink-0);
	}
	/* 코드 블록(하이라이트 전/후 공통 셸) */
	.md-body :global(pre) {
		position: relative;
		margin: 0 0 0.75em;
		padding: 0.85rem 1rem;
		border-radius: 0.6rem;
		border: 1px solid var(--color-line);
		background: var(--color-surface-sunken);
		overflow-x: auto;
		font-size: 0.82em;
		line-height: 1.55;
	}
	.md-body :global(.chat-code-copy) {
		position: absolute;
		top: 0.5rem;
		right: 0.5rem;
		z-index: 1;
		padding: 0.2rem 0.45rem;
		border: 1px solid var(--color-line-2);
		border-radius: 0.35rem;
		background: var(--color-surface-raised);
		color: var(--color-ink-2);
		font: inherit;
		font-size: 0.75rem;
		line-height: 1.2;
		cursor: pointer;
		opacity: 0;
		transition: opacity 0.15s, background 0.15s;
	}
	.md-body :global(pre:hover .chat-code-copy),
	.md-body :global(pre:focus-within .chat-code-copy) {
		opacity: 1;
	}
	.md-body :global(.chat-code-copy:hover) {
		background: var(--color-surface-sunken);
	}
	.md-body :global(.chat-code-copy:focus-visible) {
		opacity: 1;
		outline: none;
		box-shadow: var(--focus-ring);
	}
	.md-body :global(pre code) {
		font-family: var(--font-mono, ui-monospace, SFMono-Regular, Menlo, monospace);
		background: none;
		border: none;
		padding: 0;
		color: var(--color-ink-1);
	}
	/* shiki dual-theme: 기본(다크)은 --shiki-dark, 라이트 모드에서 --shiki-light */
	.md-body :global(pre.shiki),
	.md-body :global(pre.shiki span) {
		color: var(--shiki-dark, inherit);
		background-color: var(--shiki-dark-bg, transparent);
	}
	:global(:root.light) .md-body :global(pre.shiki),
	:global(:root.light) .md-body :global(pre.shiki span) {
		color: var(--shiki-light, inherit);
		background-color: var(--shiki-light-bg, transparent);
	}
	.md-body :global(table) {
		border-collapse: collapse;
		margin: 0 0 0.75em;
		font-size: 0.9em;
		display: block;
		overflow-x: auto;
	}
	.md-body :global(th),
	.md-body :global(td) {
		border: 1px solid var(--color-line);
		padding: 0.35em 0.65em;
		text-align: left;
	}
	.md-body :global(th) {
		background: var(--color-surface-sunken);
		font-weight: 600;
	}
	.md-body :global(img) {
		max-width: 100%;
		border-radius: 0.5rem;
	}
</style>
