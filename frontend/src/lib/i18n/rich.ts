/**
 * Turns a formatted message containing `<tag>…</tag>` / `<tag/>` markup into a segment tree.
 *
 * Values are substituted as private-use sentinels before tags are parsed, so user data such as a
 * resource named `<b>` stays literal text and can never create markup. Unbalanced or stray tags
 * are kept as text, which preserves literal angle-bracket hints like `<project-id>`.
 */
export type RichSegment =
	| { type: 'text'; value: string }
	| { type: 'element'; tag: string; children: RichSegment[] };

export const RICH_VALUE_OPEN = '\uE000';
export const RICH_VALUE_CLOSE = '\uE001';

const TAG_TOKEN = /<(\/?)([A-Za-z][A-Za-z0-9]*)\s*(\/?)>/g;
const VALUE_TOKEN = /\uE000(\d+)\uE001/g;

interface OpenElement {
	tag: string;
	raw: string;
	children: RichSegment[];
}

export function buildRichSegments(formatted: string, values: readonly string[]): RichSegment[] {
	const root: OpenElement = { tag: '', raw: '', children: [] };
	const stack: OpenElement[] = [root];
	const pushText = (value: string) => {
		if (!value) return;
		const target = stack[stack.length - 1].children;
		const last = target[target.length - 1];
		const expanded = value.replace(VALUE_TOKEN, (_, index: string) => values[Number(index)] ?? '');
		if (last?.type === 'text') last.value += expanded;
		else target.push({ type: 'text', value: expanded });
	};

	let cursor = 0;
	for (const match of formatted.matchAll(TAG_TOKEN)) {
		const [raw, closing, tag, selfClosing] = match;
		pushText(formatted.slice(cursor, match.index));
		cursor = match.index + raw.length;
		if (selfClosing && !closing) {
			stack[stack.length - 1].children.push({ type: 'element', tag, children: [] });
		} else if (!closing) {
			stack.push({ tag, raw, children: [] });
		} else if (stack.length > 1 && stack[stack.length - 1].tag === tag) {
			const element = stack.pop()!;
			stack[stack.length - 1].children.push({ type: 'element', tag, children: element.children });
		} else {
			pushText(raw);
		}
	}
	pushText(formatted.slice(cursor));

	// Unclosed tags degrade to their literal text followed by their content.
	while (stack.length > 1) {
		const element = stack.pop()!;
		const parent = stack[stack.length - 1].children;
		parent.push({ type: 'text', value: element.raw }, ...element.children);
	}
	return root.children;
}

/** Plain text of a segment tree, used for custom-tag snippets and accessible names. */
export function richPlainText(segments: readonly RichSegment[]): string {
	return segments.map((segment) => (segment.type === 'text' ? segment.value : richPlainText(segment.children))).join('');
}
