// @ts-check
/**
 * Finds Korean text that is still hard-coded in frontend source (outside comments).
 * Used by `node scripts/i18n.mjs scan` and the hard-coded text guard test.
 */
import { readFile, readdir } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export const FRONTEND_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
export const ALLOWLIST_PATH = path.join(FRONTEND_DIR, 'src/lib/i18n/hardcoded-text-allowlist.json');

const HANGUL = /[\u1100-\u11FF\u3130-\u318F\uAC00-\uD7A3]/;
const REGEX_PREFIX = /[(,=:[!&|?{};+\-*%<>~^]/;
/** @type {Record<string, true>} */
const REGEX_KEYWORDS = { return: true, typeof: true, case: true, in: true, of: true, new: true, delete: true, void: true, throw: true, yield: true, await: true, else: true, do: true };

/** @param {string} text */
const blank = (text) => text.replace(/[^\n]/g, ' ');

/**
 * Replaces JS/TS comments with spaces while keeping strings, template literals and regexes.
 * @param {string} source
 */
export function stripScriptComments(source) {
	let out = '';
	let i = 0;
	let previous = '';
	let lastWord = '';

	/** @param {number} depth brace depth inside a template expression; 0 means top level */
	const scan = (depth) => {
		while (i < source.length) {
			const ch = source[i];
			const next = source[i + 1];
			if (ch === '/' && next === '/') {
				const end = source.indexOf('\n', i);
				const stop = end === -1 ? source.length : end;
				out += blank(source.slice(i, stop));
				i = stop;
				continue;
			}
			if (ch === '/' && next === '*') {
				const end = source.indexOf('*/', i + 2);
				const stop = end === -1 ? source.length : end + 2;
				out += blank(source.slice(i, stop));
				i = stop;
				continue;
			}
			if (ch === '"' || ch === "'") {
				let j = i + 1;
				while (j < source.length && source[j] !== ch && source[j] !== '\n') j += source[j] === '\\' ? 2 : 1;
				out += source.slice(i, j + 1);
				i = j + 1;
				previous = ch;
				continue;
			}
			if (ch === '`') {
				out += ch;
				i += 1;
				while (i < source.length && source[i] !== '`') {
					if (source[i] === '\\') {
						out += source.slice(i, i + 2);
						i += 2;
					} else if (source[i] === '$' && source[i + 1] === '{') {
						out += '${';
						i += 2;
						scan(1);
					} else {
						out += source[i];
						i += 1;
					}
				}
				out += source[i] ?? '';
				i += 1;
				previous = '`';
				continue;
			}
			if (ch === '/' && (previous === '' || REGEX_PREFIX.test(previous) || Object.hasOwn(REGEX_KEYWORDS, lastWord))) {
				let j = i + 1;
				let inClass = false;
				while (j < source.length && source[j] !== '\n') {
					if (source[j] === '\\') {
						j += 2;
						continue;
					}
					if (source[j] === '[') inClass = true;
					else if (source[j] === ']') inClass = false;
					else if (source[j] === '/' && !inClass) break;
					j += 1;
				}
				j += 1;
				while (j < source.length && /[a-z]/i.test(source[j])) j += 1;
				out += source.slice(i, j);
				i = j;
				previous = '/';
				lastWord = '';
				continue;
			}
			if (depth > 0 && ch === '{') depth += 1;
			if (depth > 0 && ch === '}') {
				depth -= 1;
				if (depth === 0) {
					out += ch;
					i += 1;
					return;
				}
			}
			if (/[A-Za-z_$]/.test(ch)) {
				let j = i;
				while (j < source.length && /[A-Za-z0-9_$]/.test(source[j])) j += 1;
				lastWord = source.slice(i, j);
				out += lastWord;
				previous = source[j - 1];
				i = j;
				continue;
			}
			out += ch;
			if (!/\s/.test(ch)) {
				previous = ch;
				lastWord = '';
			}
			i += 1;
		}
	};
	scan(0);
	return out;
}

/**
 * Comment-free text of a Svelte component: scripts are lexed, markup drops HTML comments and
 * styles drop CSS comments. Line structure is preserved so findings keep their line numbers.
 * @param {string} source
 */
export function stripSvelteComments(source) {
	return source.replace(/(<script\b[^>]*>)([\s\S]*?)(<\/script>)|(<style\b[^>]*>)([\s\S]*?)(<\/style>)|<!--[\s\S]*?-->/g,
		(match, scriptOpen, script, scriptClose, styleOpen, style, styleClose) => {
			if (scriptOpen) return `${scriptOpen}${stripScriptComments(script)}${scriptClose}`;
			if (styleOpen) return `${styleOpen}${style.replace(/\/\*[\s\S]*?\*\//g, blank)}${styleClose}`;
			return blank(match);
		});
}

/**
 * @param {string} source
 * @param {string} filename
 * @returns {Array<{ line: number, text: string }>}
 */
export function findHardcodedText(source, filename) {
	const stripped = filename.endsWith('.svelte') ? stripSvelteComments(source) : stripScriptComments(source);
	const original = source.split('\n');
	return stripped.split('\n').flatMap((line, index) => (HANGUL.test(line) ? [{ line: index + 1, text: original[index].trim() }] : []));
}

/** UI source files: components, routes and modules, excluding tests, mocks and the catalogs. */
export async function collectSourceFiles(dir = path.join(FRONTEND_DIR, 'src')) {
	/** @type {string[]} */
	const files = [];
	for (const entry of await readdir(dir, { withFileTypes: true })) {
		const full = path.join(dir, entry.name);
		if (entry.isDirectory()) {
			if (entry.name === '__tests__' || entry.name === '__mocks__' || full.endsWith(path.join('lib', 'i18n', 'messages'))) continue;
			files.push(...(await collectSourceFiles(full)));
		} else if (/\.(svelte|ts|js)$/.test(entry.name) && !/\.(test|spec)\.[jt]s$/.test(entry.name) && !entry.name.endsWith('.d.ts')) {
			files.push(full);
		}
	}
	return files.sort();
}

/**
 * @typedef {Record<string, { reason: string, lines: string[] | 'all' }>} HardcodedTextAllowlist
 * keys are paths relative to frontend/, `lines` are exact trimmed source lines
 */

/**
 * @param {string[]} files absolute paths
 * @param {HardcodedTextAllowlist} allowlist
 */
export async function scanHardcodedText(files, allowlist) {
	/** @type {Array<{ file: string, line: number, text: string }>} */
	const findings = [];
	for (const file of files) {
		const relative = path.relative(FRONTEND_DIR, file).replaceAll(path.sep, '/');
		const allowed = allowlist[relative];
		if (allowed?.lines === 'all') continue;
		for (const hit of findHardcodedText(await readFile(file, 'utf8'), file)) {
			if (allowed?.lines.includes(hit.text)) continue;
			findings.push({ file: relative, ...hit });
		}
	}
	return findings;
}

export async function loadAllowlist() {
	return /** @type {HardcodedTextAllowlist} */ (JSON.parse(await readFile(ALLOWLIST_PATH, 'utf8')));
}
