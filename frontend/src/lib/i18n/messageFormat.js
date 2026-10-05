// @ts-check
/**
 * ICU MessageFormat subset shared by the browser runtime and the Node catalog tools.
 *
 * Supported syntax:
 *   {name}                                       argument (inserted as String(value))
 *   {count, plural, =0 {...} one {...} other {...}} plural; `#` is the locale-formatted number
 *   {kind, select, admin {...} other {...}}      select on String(value)
 *   Exact selectors accept finite unsigned integers/decimals, including `.5` and `1.`.
 *   Signs, exponents and non-decimal number literals are not supported.
 *   ''                                           a literal apostrophe
 *   '{' … '}'                                    quoted literal braces (ICU apostrophe rules)
 *
 * Rich-text tags such as <strong>…</strong> are plain text here; `rich.ts` turns them into
 * segments for the RichText component after values have been substituted.
 */

/**
 * @typedef {{ type: 'text', value: string }} TextNode
 * @typedef {{ type: 'argument', name: string }} ArgumentNode
 * @typedef {{ type: 'pound' }} PoundNode
 * @typedef {{ type: 'plural' | 'select', name: string, options: Record<string, MessageNode[]> }} ChoiceNode
 * @typedef {TextNode | ArgumentNode | PoundNode | ChoiceNode} MessageNode
 * @typedef {Record<string, string | number | boolean | null | undefined>} MessageValues
 */

export class MessageSyntaxError extends Error {
	/**
	 * @param {string} reason
	 * @param {number} offset
	 */
	constructor(reason, offset) {
		super(`${reason} at offset ${offset}`);
		this.name = 'MessageSyntaxError';
		this.offset = offset;
	}
}

/** @type {Record<string, true>} */
const PLURAL_CATEGORIES = { zero: true, one: true, two: true, few: true, many: true, other: true };
const IDENTIFIER_CHAR = /[A-Za-z0-9_]/;
const SELECTOR_CHAR = /[A-Za-z0-9_-]/;
const WHITESPACE = /\s/;

/**
 * @param {string} source
 * @returns {MessageNode[]}
 */
export function parseMessage(source) {
	let pos = 0;

	const skipWhitespace = () => {
		while (pos < source.length && WHITESPACE.test(source[pos])) pos += 1;
	};

	/** @param {RegExp} allowed */
	const readWhile = (allowed) => {
		const start = pos;
		while (pos < source.length && allowed.test(source[pos])) pos += 1;
		return source.slice(start, pos);
	};

	/**
	 * @param {boolean} inPlural `#` refers to the nearest enclosing plural
	 * @param {number} depth
	 * @returns {MessageNode[]}
	 */
	const parseNodes = (inPlural, depth) => {
		/** @type {MessageNode[]} */
		const nodes = [];
		let text = '';
		const flush = () => {
			if (text) nodes.push({ type: 'text', value: text });
			text = '';
		};
		while (pos < source.length) {
			const ch = source[pos];
			if (ch === "'") {
				const next = source[pos + 1];
				if (next === "'") {
					text += "'";
					pos += 2;
					continue;
				}
				if (next === '{' || next === '}' || (inPlural && next === '#')) {
					pos += 1;
					while (pos < source.length) {
						if (source[pos] === "'") {
							if (source[pos + 1] === "'") {
								text += "'";
								pos += 2;
								continue;
							}
							pos += 1;
							break;
						}
						text += source[pos];
						pos += 1;
					}
					continue;
				}
				text += ch;
				pos += 1;
				continue;
			}
			if (ch === '{') {
				flush();
				nodes.push(parseArgument(inPlural, depth));
				continue;
			}
			if (ch === '}') {
				if (depth === 0) throw new MessageSyntaxError('unmatched "}"', pos);
				flush();
				return nodes;
			}
			if (ch === '#' && inPlural) {
				flush();
				nodes.push({ type: 'pound' });
				pos += 1;
				continue;
			}
			text += ch;
			pos += 1;
		}
		if (depth > 0) throw new MessageSyntaxError('unclosed "{"', pos);
		flush();
		return nodes;
	};

	/**
	 * @param {boolean} inPlural
	 * @param {number} depth
	 * @returns {MessageNode}
	 */
	const parseArgument = (inPlural, depth) => {
		const start = pos;
		pos += 1;
		skipWhitespace();
		const name = readWhile(IDENTIFIER_CHAR);
		if (!name || /^[0-9]/.test(name)) throw new MessageSyntaxError('invalid argument name', start);
		skipWhitespace();
		if (source[pos] === '}') {
			pos += 1;
			return { type: 'argument', name };
		}
		if (source[pos] !== ',') throw new MessageSyntaxError(`expected "," or "}" after "${name}"`, pos);
		pos += 1;
		skipWhitespace();
		const kind = readWhile(IDENTIFIER_CHAR);
		if (kind !== 'plural' && kind !== 'select') {
			throw new MessageSyntaxError(`unsupported argument type "${kind}"`, pos);
		}
		skipWhitespace();
		if (source[pos] !== ',') throw new MessageSyntaxError(`expected "," after "${kind}"`, pos);
		pos += 1;
		/** @type {Record<string, MessageNode[]>} */
		const options = Object.create(null);
		for (;;) {
			skipWhitespace();
			if (pos >= source.length) throw new MessageSyntaxError(`unclosed ${kind} "${name}"`, start);
			if (source[pos] === '}') {
				pos += 1;
				break;
			}
			const selectorStart = pos;
			let selector;
			if (source[pos] === '=') {
				pos += 1;
				const exact = readWhile(/[^\s{}]/);
				if (!/^(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)$/.test(exact) || !Number.isFinite(Number(exact))) {
					throw new MessageSyntaxError('invalid exact selector number', selectorStart);
				}
				selector = `=${Number(exact)}`;
			} else {
				selector = readWhile(SELECTOR_CHAR);
			}
			if (!selector) throw new MessageSyntaxError(`expected a ${kind} option`, selectorStart);
			if (kind === 'plural' && !selector.startsWith('=') && !Object.hasOwn(PLURAL_CATEGORIES, selector)) {
				throw new MessageSyntaxError(`unknown plural category "${selector}"`, selectorStart);
			}
			if (Object.hasOwn(options, selector)) {
				throw new MessageSyntaxError(`duplicate option "${selector}"`, selectorStart);
			}
			skipWhitespace();
			if (source[pos] !== '{') throw new MessageSyntaxError(`expected "{" after "${selector}"`, pos);
			pos += 1;
			options[selector] = parseNodes(kind === 'plural' || inPlural, depth + 1);
			pos += 1;
		}
		if (!Object.hasOwn(options, 'other')) {
			throw new MessageSyntaxError(`${kind} "${name}" requires an "other" option`, start);
		}
		return { type: kind, name, options };
	};

	return parseNodes(false, 0);
}

/** @type {Map<string, Intl.PluralRules>} */
const pluralRulesCache = new Map();
/** @type {Map<string, Intl.NumberFormat>} */
const numberFormatCache = new Map();

/** @param {string} intlLocale */
function pluralRules(intlLocale) {
	let rules = pluralRulesCache.get(intlLocale);
	if (!rules) {
		rules = new Intl.PluralRules(intlLocale);
		pluralRulesCache.set(intlLocale, rules);
	}
	return rules;
}

/** @param {string} intlLocale */
function numberFormat(intlLocale) {
	let format = numberFormatCache.get(intlLocale);
	if (!format) {
		format = new Intl.NumberFormat(intlLocale);
		numberFormatCache.set(intlLocale, format);
	}
	return format;
}

/**
 * @param {MessageNode[]} nodes
 * @param {MessageValues | undefined} values
 * @param {string} intlLocale BCP 47 tag of the language the message is written in
 * @param {(value: string | number | boolean) => string} [insertValue] rich-text sentinel hook
 * @returns {string}
 */
export function formatMessage(nodes, values, intlLocale, insertValue = String) {
	/** @param {ChoiceNode} node @param {string} selector */
	const ownOption = (node, selector) => Object.hasOwn(node.options, selector) ? node.options[selector] : undefined;

	/**
	 * @param {MessageNode[]} branch
	 * @param {number | undefined} pound
	 */
	const render = (branch, pound) => {
		let out = '';
		for (const node of branch) {
			if (node.type === 'text') {
				out += node.value;
			} else if (node.type === 'argument') {
				const value = values?.[node.name];
				out += value === undefined || value === null ? `{${node.name}}` : insertValue(value);
			} else if (node.type === 'pound') {
				out += pound === undefined ? '#' : numberFormat(intlLocale).format(pound);
			} else if (node.type === 'plural') {
				const raw = values?.[node.name];
				const count = raw === undefined || raw === null || raw === '' ? Number.NaN : Number(raw);
				const known = Number.isFinite(count);
				const option =
					(known ? ownOption(node, `=${count}`) ?? ownOption(node, pluralRules(intlLocale).select(count)) : undefined)
					?? node.options.other;
				out += render(option, known ? count : undefined);
			} else {
				const raw = values?.[node.name];
				const option = (raw === undefined || raw === null ? undefined : ownOption(node, String(raw))) ?? node.options.other;
				out += render(option, pound);
			}
		}
		return out;
	};
	return render(nodes, undefined);
}

/**
 * Argument names a translation must keep identical to the source message.
 * @param {MessageNode[]} nodes
 * @returns {Set<string>}
 */
export function messageArguments(nodes) {
	/** @type {Set<string>} */
	const names = new Set();
	/** @param {MessageNode[]} branch */
	const visit = (branch) => {
		for (const node of branch) {
			if (node.type === 'argument') names.add(node.name);
			else if (node.type === 'plural' || node.type === 'select') {
				names.add(node.name);
				for (const option of Object.values(node.options)) visit(option);
			}
		}
	};
	visit(nodes);
	return names;
}

const TAG_TOKEN = /<(\/?)([A-Za-z][A-Za-z0-9]*)\s*(\/?)>/g;

/**
 * Sorted tag tokens (`<strong>`, `</strong>`, `<br/>`) so translations keep the same markup.
 * @param {string} source
 * @returns {string[]}
 */
export function messageTags(source) {
	return [...source.matchAll(TAG_TOKEN)]
		.map(([, closing, name, selfClosing]) => `<${closing}${name}${selfClosing}>`)
		.sort();
}

/**
 * Diagnose unbalanced intended rich tags on static ICU render paths. Pass tag names
 * (e.g. `strong`, `br`) or tokens returned by messageTags. Other tag-like hints are literal.
 * ICU quoting is already resolved in the AST; interpolation values cannot create tags
 * in the rich renderer. Branches may open/close tags outside their own selector.
 * Repeated selects are correlated by argument value, including different option sets.
 * Plural branches are conservatively independent (no locale is provided), so correlated
 * plural markup may produce diagnostics. This checks static markup, not tags constructed
 * from interpolated values or `#`. Path enumeration can grow exponentially with choices.
 * This helper does not change rendering or the sorted messageTags parity contract.
 *
 * @param {MessageNode[]} nodes
 * @param {Iterable<string>} intendedTags
 * @returns {string[]}
 */
export function messageRichErrors(nodes, intendedTags) {
	const intended = new Set([...intendedTags].map((tag) => tag.replace(/^<\/?([A-Za-z][A-Za-z0-9]*)\s*\/?>$/, '$1')));
	if (intended.size === 0) return [];
	/** @typedef {{ value?: string, excluded: Set<string> }} SelectConstraint */
	/** @typedef {{ text: string, selects: Map<string, SelectConstraint> }} RichPath */
	/**
	 * @param {MessageNode[]} branch
	 * @param {RichPath[]} paths
	 * @returns {RichPath[]}
	 */
	const expand = (branch, paths) => {
		for (const node of branch) {
			if (node.type === 'text' || node.type === 'argument' || node.type === 'pound') {
				// Sentinels keep argument boundaries from joining partial tag tokens.
				const text = node.type === 'text' ? node.value : node.type === 'pound' ? '#' : '\uE000\uE001';
				paths = paths.map((path) => ({ ...path, text: path.text + text }));
				continue;
			}
			/** @type {RichPath[]} */
			const next = [];
			for (const path of paths) {
				for (const [selector, option] of Object.entries(node.options)) {
					let selects = path.selects;
					if (node.type === 'select') {
						const previous = selects.get(node.name);
						const excluded = new Set(previous?.excluded);
						let value = previous?.value;
						if (selector === 'other') {
							for (const key of Object.keys(node.options)) {
								if (key !== 'other') excluded.add(key);
							}
							if (value !== undefined && excluded.has(value)) continue;
						} else {
							if ((value !== undefined && value !== selector) || excluded.has(selector)) continue;
							value = selector;
						}
						selects = new Map(selects);
						selects.set(node.name, { value, excluded });
					}
					for (const expanded of expand(option, [{ text: path.text, selects }])) next.push(expanded);
				}
			}
			paths = next;
		}
		return paths;
	};
	/** @type {Set<string>} */
	const errors = new Set();
	for (const { text } of expand(nodes, [{ text: '', selects: new Map() }])) {
		/** @type {string[]} */
		const stack = [];
		for (const [token, closing, tag, selfClosing] of text.matchAll(TAG_TOKEN)) {
			if (!intended.has(tag)) continue;
			if (closing) {
				const open = stack[stack.length - 1];
				if (selfClosing || open !== tag) {
					errors.add(`Unexpected closing tag ${token}${open ? `; expected </${open}>` : '; no open tag'}`);
				} else stack.pop();
			} else if (!selfClosing) stack.push(tag);
		}
		for (const tag of stack.reverse()) errors.add(`Unclosed tag <${tag}>`);
	}
	return [...errors];
}
