import { describe, expect, it } from 'vitest';
import { formatMessage, MessageSyntaxError, messageArguments, messageRichErrors, messageTags, parseMessage } from '../messageFormat.js';

const format = (source: string, values: Record<string, string | number | boolean | null | undefined> = {}, locale = 'en-US') =>
	formatMessage(parseMessage(source), values, locale);

describe('messageFormat', () => {
	it('substitutes arguments verbatim and keeps a missing value visible', () => {
		expect(format('{name} 인스턴스를 삭제했습니다.', { name: 'web-01' })).toBe('web-01 인스턴스를 삭제했습니다.');
		expect(format('Year {year}', { year: 2026 })).toBe('Year 2026');
		expect(format('Hello {name}')).toBe('Hello {name}');
	});

	it('selects plural forms with locale rules, exact matches first, and formats #', () => {
		const source = '{count, plural, =0 {No results} one {# result} other {# results}}';
		expect(format(source, { count: 0 })).toBe('No results');
		expect(format(source, { count: 1 })).toBe('1 result');
		expect(format(source, { count: 1234 })).toBe('1,234 results');
		// Japanese has no `one` category, so the same count always reads `other`.
		expect(format('{count, plural, one {# 件(one)} other {# 件}}', { count: 1 }, 'ja-JP')).toBe('1 件');
	});

	it('falls back to other for unknown select values and non-numeric plural input', () => {
		const select = '{role, select, admin {Administrator} other {Member}}';
		expect(format(select, { role: 'admin' })).toBe('Administrator');
		expect(format(select, { role: 'reader' })).toBe('Member');
		expect(format(select)).toBe('Member');
		expect(format('{n, plural, one {# item} other {# items}}', { n: 'many' })).toBe('# items');
	});

	it('treats prototype names as ordinary select values, including explicit options', () => {
		const fallback = '{role, select, admin {Administrator} other {Member}}';
		for (const role of ['constructor', 'toString', '__proto__']) {
			expect(format(fallback, { role })).toBe('Member');
		}
		const explicit = '{role, select, __proto__ {Prototype} constructor {Constructor} toString {String} other {Member}}';
		expect(format(explicit, { role: '__proto__' })).toBe('Prototype');
		expect(format(explicit, { role: 'constructor' })).toBe('Constructor');
		expect(format(explicit, { role: 'toString' })).toBe('String');
		expect(format(explicit, { role: 'unknown' })).toBe('Member');
		expect(() => parseMessage('{role, select, __proto__ {First} __proto__ {Second} other {Member}}')).toThrow(MessageSyntaxError);
	});

	it('ignores inherited branches in both plural and select ASTs', () => {
		for (const kind of ['plural', 'select']) {
			const nodes = parseMessage(`{value, ${kind}, other {Fallback}}`);
			const choice = nodes[0];
			if (choice.type !== 'plural' && choice.type !== 'select') throw new Error('Expected a choice');
			const inherited = [{ type: 'text', value: 'Inherited' }];
			Object.setPrototypeOf(choice.options, { one: inherited, '=1': inherited, constructor: inherited });
			expect(formatMessage(nodes, { value: kind === 'plural' ? 1 : 'constructor' }, 'en-US')).toBe('Fallback');
		}
	});

	it('preserves supported exact decimal forms and canonical duplicate detection', () => {
		for (const [selector, count] of [['1.25', 1.25], ['.5', 0.5], ['1.', 1], ['01.0', 1], ['0', 0]] as const) {
			const source = `{n, plural, =${selector} {Exact} one {Category} other {Other}}`;
			expect(format(source, { n: count })).toBe('Exact');
			expect(format(source, { n: 2 })).toBe('Other');
		}
		expect(() => parseMessage('{n, plural, =1.0 {First} =01 {Second} other {Other}}')).toThrow(MessageSyntaxError);
	});

	it('rejects malformed, non-finite and unsupported exact numbers', () => {
		for (const selector of ['', '.', '..', '1..2', '1.2.3', '-1', '-.5', '+1', '1e2', '0x10', 'NaN', 'Infinity', '9'.repeat(400)]) {
			expect(() => parseMessage(`{n, plural, =${selector} {Exact} other {Other}}`)).toThrow(MessageSyntaxError);
		}
	});

	it('uses the nearest plural count for # inside a nested select', () => {
		const source = '{count, plural, one {{kind, select, gpu {# GPU host} other {# host}}} other {{kind, select, gpu {# GPU hosts} other {# hosts}}}}';
		expect(format(source, { count: 2, kind: 'gpu' })).toBe('2 GPU hosts');
		expect(format(source, { count: 1, kind: 'cpu' })).toBe('1 host');
	});

	it('applies ICU apostrophe rules', () => {
		expect(format("Don't stop")).toBe("Don't stop");
		expect(format("It''s {name}", { name: 'ok' })).toBe("It's ok");
		expect(format("Literal '{braces}' stay")).toBe('Literal {braces} stay');
		expect(format("{n, plural, other {'#' is # }}", { n: 3 })).toBe('# is 3 ');
	});

	it('rejects malformed or unsupported syntax with an offset', () => {
		expect(() => parseMessage('{count, plural, one {#}}')).toThrow(MessageSyntaxError);
		expect(() => parseMessage('{count, plural, single {#} other {#}}')).toThrow(MessageSyntaxError);
		expect(() => parseMessage('Unclosed {name')).toThrow(MessageSyntaxError);
		expect(() => parseMessage('{value, number}')).toThrow(MessageSyntaxError);
		expect(() => parseMessage('Stray } brace')).toThrow(MessageSyntaxError);
		expect(() => parseMessage('{count, plural, other {#}')).toThrow(MessageSyntaxError);
	});

	it('lists every argument name including nested choices', () => {
		const names = messageArguments(parseMessage('{a} {count, plural, other {{kind, select, x {{b}} other {}}}}'));
		expect([...names].sort()).toEqual(['a', 'b', 'count', 'kind']);
	});

	it('lists tag tokens so translations keep the same markup', () => {
		expect(messageTags('<strong>{count}</strong>개 선택됨<br/>')).toEqual(['</strong>', '<br/>', '<strong>']);
		expect(messageTags('형식: <project-id> 그대로')).toEqual([]);
	});

	it('diagnoses reversed, unclosed and misnested intended rich tags', () => {
		const intended = ['strong', 'em'];
		const reversed = '</strong>text<strong>';
		expect(messageTags(reversed)).toEqual(messageTags('<strong>text</strong>'));
		expect(messageRichErrors(parseMessage(reversed), intended).some((error) => error.includes('</strong>'))).toBe(true);
		expect(messageRichErrors(parseMessage('<strong>text'), intended).some((error) => error.includes('<strong>'))).toBe(true);
		expect(messageRichErrors(parseMessage('<strong><em>text</strong></em>'), intended).some((error) => error.includes('</strong>'))).toBe(true);
		expect(messageRichErrors(parseMessage('<strong>text</strong/>'), intended).some((error) => error.includes('</strong/>'))).toBe(true);
	});

	it('validates every choice path while allowing outer and branch-spanning tags', () => {
		const intended = ['strong', 'em', 'br'];
		const outer = '<strong>{n, plural, one {<em># item</em>} other {{kind, select, gpu {# GPUs<br/>} other {# items}}}}</strong>';
		expect(messageRichErrors(parseMessage(outer), intended)).toEqual([]);
		const branchClose = '<strong>{kind, select, a {A</strong>} other {<em>B</em></strong>}}';
		expect(messageRichErrors(parseMessage(branchClose), intended)).toEqual([]);
		const branchOpen = '{kind, select, a {<strong>A} other {<strong><em>B</em>}}</strong>';
		expect(messageRichErrors(parseMessage(branchOpen), intended)).toEqual([]);
		const invalid = '<strong>{kind, select, a {A</strong>} other {B}}';
		expect(messageRichErrors(parseMessage(invalid), intended).some((error) => error.includes('<strong>'))).toBe(true);
		const invalidPlural = '{n, plural, =0 {<em>none} one {one} other {many}}';
		expect(messageRichErrors(parseMessage(invalidPlural), intended).some((error) => error.includes('<em>'))).toBe(true);
	});

	it('allows reordering, quoted ICU text and non-intended literal hints', () => {
		const source = '<em>First</em><strong>Second</strong><br/>';
		const translated = "<strong>'{literal}' {name}</strong><em>First</em><br /> <hint> <project-id>";
		expect(messageRichErrors(parseMessage(translated), messageTags(source))).toEqual([]);
		expect(messageRichErrors(parseMessage("'{<strong>quoted</strong>}'"), ['strong'])).toEqual([]);
		expect(messageRichErrors(parseMessage('<hint> </otherhint>'), ['strong'])).toEqual([]);
	});

	it('correlates repeated selects rather than combining impossible branches', () => {
		const paired = '{kind, select, a {<strong>} other {<em>}}text{kind, select, a {</strong>} other {</em>}}';
		expect(messageRichErrors(parseMessage(paired), ['strong', 'em'])).toEqual([]);
		const nested = '{kind, select, a {<strong>{kind, select, b {</em>} other {</strong>}}} other {plain}}';
		expect(messageRichErrors(parseMessage(nested), ['strong', 'em'])).toEqual([]);
		const narrowed = '{kind, select, a {<strong>} other {<em>}}{kind, select, a {</strong>} b {</em>} other {</em>}}';
		expect(messageRichErrors(parseMessage(narrowed), ['strong', 'em'])).toEqual([]);
		const invalid = '{kind, select, a {<strong>} other {<em>}}{kind, select, b {</em>} other {</strong>}}';
		expect(messageRichErrors(parseMessage(invalid), ['strong', 'em']).some((error) => error.includes('</strong>'))).toBe(true);
	});
});
