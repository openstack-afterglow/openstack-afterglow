import { describe, expect, it } from 'vitest';
import { render } from '@testing-library/svelte';
import RichText from '../RichText.svelte';
import { buildRichSegments, richPlainText } from '../rich';

describe('rich text segments', () => {
	it('builds nested elements and keeps stray or unclosed tags literal', () => {
		const segments = buildRichSegments('<strong>A <em>b</em></strong> </em> <project-id> <code>tail', []);
		expect(segments).toEqual([
			{ type: 'element', tag: 'strong', children: [{ type: 'text', value: 'A ' }, { type: 'element', tag: 'em', children: [{ type: 'text', value: 'b' }] }] },
			{ type: 'text', value: ' </em> <project-id> ' },
			{ type: 'text', value: '<code>' },
			{ type: 'text', value: 'tail' },
		]);
		expect(richPlainText(segments)).toBe('A b </em> <project-id> <code>tail');
	});

	it('renders built-in tags as elements and never interprets values as markup', () => {
		const segments = buildRichSegments('Delete <strong>\uE0000\uE001</strong>?<br/>Done', ['<img src=x>']);
		const { container } = render(RichText, { segments, classes: { strong: 'text-ink-0' } });
		const strong = container.querySelector('strong');
		expect(strong?.textContent).toBe('<img src=x>');
		expect(strong?.className).toBe('text-ink-0');
		expect(container.querySelector('img')).toBeNull();
		expect(container.querySelector('br')).not.toBeNull();
		expect(container.textContent).toBe('Delete <img src=x>?Done');
	});
});
