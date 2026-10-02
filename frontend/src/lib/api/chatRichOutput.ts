import katex from 'katex';
import mermaid from 'mermaid';
import DOMPurify from 'dompurify';

const MATH_PATTERN = /(\$\$[\s\S]+?\$\$|\\\[[\s\S]+?\\\]|\\\([\s\S]+?\\\)|(?<!\\)\$(?:\\.|[^$\\\n])+(?<!\\)\$)/g;
let mermaidInitialized = false;
let mermaidSequence = 0;

function texFromDelimited(value: string): { tex: string; displayMode: boolean } {
	if (value.startsWith('$$')) return { tex: value.slice(2, -2), displayMode: true };
	if (value.startsWith('\\[')) return { tex: value.slice(2, -2), displayMode: true };
	if (value.startsWith('\\(')) return { tex: value.slice(2, -2), displayMode: false };
	return { tex: value.slice(1, -1), displayMode: false };
}

function mathEligibleTextNodes(container: HTMLElement): Text[] {
	const nodes: Text[] = [];
	const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT, {
		acceptNode(node) {
			if (!node.textContent || !/[\\$]/.test(node.textContent)) return NodeFilter.FILTER_REJECT;
			const parent = node.parentElement;
			return parent?.closest('pre, code, a, .katex, .math-display, .mermaid-diagram')
				? NodeFilter.FILTER_REJECT
				: NodeFilter.FILTER_ACCEPT;
		}
	});
	while (walker.nextNode()) nodes.push(walker.currentNode as Text);
	return nodes;
}

/** Render untrusted TeX without allowing HTML-like KaTeX commands. */
export async function renderMath(container: HTMLElement): Promise<void> {
	for (const placeholder of Array.from(container.querySelectorAll<HTMLElement>('[data-chat-math]'))) {
		const encoded = placeholder.dataset.chatMath;
		if (!encoded?.startsWith('afterglow:')) continue;
		try {
			placeholder.innerHTML = katex.renderToString(decodeURIComponent(encoded.slice('afterglow:'.length)), {
				displayMode: true,
				throwOnError: false,
				strict: 'ignore',
				trust: false,
				output: 'htmlAndMathml'
			});
			placeholder.removeAttribute('data-chat-math');
		} catch {
			placeholder.textContent = '$$ invalid math $$';
		}
	}
	for (const textNode of mathEligibleTextNodes(container)) {
		const source = textNode.textContent ?? '';
		MATH_PATTERN.lastIndex = 0;
		if (!MATH_PATTERN.test(source)) continue;
		MATH_PATTERN.lastIndex = 0;
		const fragment = document.createDocumentFragment();
		let cursor = 0;
		for (const match of source.matchAll(MATH_PATTERN)) {
			const start = match.index ?? 0;
			fragment.append(source.slice(cursor, start));
			const { tex, displayMode } = texFromDelimited(match[0]);
			const shell = document.createElement(displayMode ? 'div' : 'span');
			shell.className = displayMode ? 'math-display' : 'math-inline';
			shell.innerHTML = katex.renderToString(tex, {
				displayMode,
				throwOnError: false,
				strict: 'ignore',
				trust: false,
				output: 'htmlAndMathml'
			});
			fragment.append(shell);
			cursor = start + match[0].length;
		}
		fragment.append(source.slice(cursor));
		textNode.replaceWith(fragment);
	}
}
function initializeMermaid(): void {
	if (mermaidInitialized) return;
	mermaid.initialize({ startOnLoad: false, securityLevel: 'strict', htmlLabels: false });
	mermaidInitialized = true;
}

/** Render only fenced `mermaid` blocks after streaming completes. Invalid source stays readable. */
export async function renderMermaidBlocks(container: HTMLElement): Promise<void> {
	const blocks = Array.from(container.querySelectorAll('pre > code.language-mermaid'))
		.filter((code) => !code.closest('pre')?.hasAttribute('data-mermaid'));
	if (!blocks.length) return;
	initializeMermaid();
	for (const code of blocks) {
		const pre = code.closest('pre');
		if (!pre) continue;
		pre.setAttribute('data-mermaid', '');
		const source = code.textContent ?? '';
		const diagram = document.createElement('div');
		diagram.className = 'mermaid-diagram';
		try {
			const { svg } = await mermaid.render(`afterglow-mermaid-${++mermaidSequence}`, source);
			diagram.innerHTML = DOMPurify.sanitize(svg, {
				USE_PROFILES: { svg: true, svgFilters: true },
				FORBID_TAGS: ['foreignObject'],
				FORBID_ATTR: ['onerror', 'onload', 'onclick']
			});
			pre.replaceWith(diagram);
		} catch {
			// Diagram source is user/model content. Preserve it as a code block on parse failure.
			pre.setAttribute('data-mermaid-error', '');
		}
	}
}

export async function enhanceChatMarkdown(container: HTMLElement): Promise<void> {
	try {
		await renderMath(container);
	} catch {
		// A deployment that has not yet rolled out the optional renderer keeps safe plain Markdown.
	}
	try {
		await renderMermaidBlocks(container);
	} catch {
		// The diagram source remains as its sanitized fenced code block.
	}
}
