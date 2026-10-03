import { describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
	initialize: vi.fn(),
	render: vi.fn().mockResolvedValue({ svg: '<svg><script>alert(1)</script><text>diagram</text></svg>' })
}));

vi.mock('mermaid', () => ({ default: mocks }));

import { renderMermaidBlocks } from '../chatRichOutput';

describe('Mermaid chat output', () => {
	it('renders fenced diagrams and sanitizes the generated SVG', async () => {
		const host = document.createElement('div');
		host.innerHTML = '<pre><code class="language-mermaid">flowchart LR\nA[Start] --&gt; B[Finish]</code></pre>';

		await renderMermaidBlocks(host);

		expect(host.querySelector('.mermaid-diagram svg')).toBeTruthy();
		expect(host.querySelector('.mermaid-diagram script')).toBeNull();
	});
});
