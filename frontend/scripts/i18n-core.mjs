// @ts-check
/**
 * Catalog tooling shared by `scripts/i18n.mjs` and the frontend unit tests.
 *
 * Layout: src/lib/i18n/messages/<locale>/<namespace>.json (flat key → ICU message),
 * src/lib/i18n/ns/<namespace>.ts (runtime binding) and src/lib/i18n/review/<locale>.json
 * (`namespace:key` → hash of the Korean source a native reviewer approved).
 */
import { createHash } from 'node:crypto';
import { readFile, readdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { messageArguments, messageRichErrors, messageTags, parseMessage } from '../src/lib/i18n/messageFormat.js';

export const I18N_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../src/lib/i18n');
/** Must equal LOCALES in src/lib/i18n/locales.ts (asserted by the catalog test). */
export const LOCALES = ['ko', 'en', 'ja', 'zh-CN'];
export const SOURCE_LOCALE = 'ko';
export const TRANSLATION_LOCALES = LOCALES.filter((locale) => locale !== SOURCE_LOCALE);

const NAMESPACE_PATTERN = /^[a-z][a-z0-9-]*$/;
const KEY_PATTERN = /^[a-z][A-Za-z0-9]*(?:\.[A-Za-z0-9_]+)*$/;
const HANGUL = /[\u1100-\u11FF\u3130-\u318F\uAC00-\uD7A3]/;
// Built-ins match RichText.svelte; paired/self-closing custom tags are snippet markup.
const BUILTIN_RICH_TAGS = new Set(['strong', 'b', 'em', 'i', 'code', 'kbd', 'br']);
/** @type {readonly string[]} */
const NO_RICH_ERRORS = Object.freeze([]);

/**
 * @typedef {Record<string, string>} Messages
 * @typedef {{ namespaces: string[], messages: Record<string, Record<string, Messages>>, modules: string[] | null, loadErrors: Finding[] }} Catalogs
 * @typedef {{ level: 'error' | 'warning', code: string, locale?: string, namespace?: string, key?: string, detail: string }} Finding
 * @typedef {Record<string, Record<string, string>>} ReviewManifests locale → `ns:key` → source hash
 * @typedef {'reviewed' | 'outdated' | 'draft' | 'missing'} ReviewState
 * @typedef {{ args: string[], tags: string[], richErrors: readonly string[], error: string | null }} MessageInspection
 */

/** Short stable hash of a Korean source message; a changed source invalidates its reviews.
 * @param {string} text
 */
export function sourceHash(text) {
	return createHash('sha256').update(text, 'utf8').digest('hex').slice(0, 16);
}

/** @param {string} dir */
async function listJson(dir) {
	try {
		return (await readdir(dir)).filter((name) => name.endsWith('.json')).map((name) => name.slice(0, -5)).sort();
	} catch (error) {
		if (!error || typeof error !== 'object' || !('code' in error) || error.code !== 'ENOENT') throw error;
		return [];
	}
}

/**
 * @param {string} [dir]
 * @returns {Promise<Catalogs>}
 */
export async function loadCatalogs(dir = I18N_DIR) {
	/** @type {Finding[]} */
	const loadErrors = [];
	/** @type {Record<string, Record<string, Messages>>} */
	const messages = {};
	/** @type {Set<string>} */
	const namespaceSet = new Set();
	for (const locale of LOCALES) {
		messages[locale] = {};
		for (const namespace of await listJson(path.join(dir, 'messages', locale))) {
			namespaceSet.add(namespace);
			const file = path.join(dir, 'messages', locale, `${namespace}.json`);
			try {
				const parsed = JSON.parse(await readFile(file, 'utf8'));
				if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
					loadErrors.push({ level: 'error', code: 'not-flat-object', locale, namespace, detail: 'catalog must be a flat JSON object' });
					continue;
				}
				messages[locale][namespace] = parsed;
			} catch (error) {
				loadErrors.push({ level: 'error', code: 'invalid-json', locale, namespace, detail: String(error) });
			}
		}
	}
	let modules = null;
	try {
		modules = (await readdir(path.join(dir, 'ns'))).filter((name) => name.endsWith('.ts')).map((name) => name.slice(0, -3)).sort();
	} catch (error) {
		if (!error || typeof error !== 'object' || !('code' in error) || error.code !== 'ENOENT') throw error;
		modules = null;
	}
	return { namespaces: [...namespaceSet].sort(), messages, modules, loadErrors };
}

/** @param {Catalogs} catalogs */
function catalogLoadFailures(catalogs) {
	return catalogs.loadErrors.map((finding) => `${finding.code} ${[finding.locale, finding.namespace].filter(Boolean).join('/')}: ${finding.detail}`);
}

/** @param {string[]} tags @returns {Set<string>} */
function intendedRichTags(tags) {
	const intended = new Set();
	const opened = new Set();
	const closed = new Set();
	for (const token of tags) {
		const name = token.replace(/[<>/]/g, '');
		if (BUILTIN_RICH_TAGS.has(name) || token.endsWith('/>')) intended.add(name);
		else if (token.startsWith('</')) closed.add(name);
		else opened.add(name);
	}
	for (const name of opened) if (closed.has(name)) intended.add(name);
	return intended;
}

/**
 * @param {string} source
 * @returns {MessageInspection}
 */
function inspect(source) {
	try {
		const nodes = parseMessage(source);
		const tags = messageTags(source);
		return {
			args: [...messageArguments(nodes)].sort(),
			tags,
			richErrors: tags.length ? messageRichErrors(nodes, intendedRichTags(tags)) : NO_RICH_ERRORS,
			error: null,
		};
	} catch (error) {
		return { args: [], tags: [], richErrors: NO_RICH_ERRORS, error: error instanceof Error ? error.message : String(error) };
	}
}

/**
 * Validates structure, completeness and translation safety of every catalog.
 * @param {Catalogs} catalogs
 * @returns {Finding[]}
 */
export function validateCatalogs(catalogs) {
	/** @type {Finding[]} */
	const findings = [...catalogs.loadErrors];
	const sourceNamespaces = Object.keys(catalogs.messages[SOURCE_LOCALE] ?? {}).sort();
	const push = (/** @type {Finding} */ finding) => findings.push(finding);

	for (const namespace of catalogs.namespaces) {
		if (!NAMESPACE_PATTERN.test(namespace)) {
			push({ level: 'error', code: 'invalid-namespace', namespace, detail: 'namespace file names are lowercase kebab-case' });
		}
		if (!sourceNamespaces.includes(namespace)) {
			push({ level: 'error', code: 'extra-namespace', namespace, detail: 'translation namespace has no Korean source catalog' });
		}
	}
	if (catalogs.modules) {
		for (const namespace of sourceNamespaces) {
			if (!catalogs.modules.includes(namespace)) {
				push({ level: 'error', code: 'missing-module', namespace, detail: `create src/lib/i18n/ns/${namespace}.ts` });
			}
		}
		for (const module of catalogs.modules) {
			if (!sourceNamespaces.includes(module)) {
				push({ level: 'error', code: 'orphan-module', namespace: module, detail: 'namespace module has no Korean source catalog' });
			}
		}
	}

	for (const namespace of sourceNamespaces) {
		const source = catalogs.messages[SOURCE_LOCALE][namespace];
		/** @type {Record<string, MessageInspection>} */
		const sourceInfo = {};
		for (const [key, value] of Object.entries(source)) {
			if (!KEY_PATTERN.test(key)) push({ level: 'error', code: 'invalid-key', locale: SOURCE_LOCALE, namespace, key, detail: 'keys are dot-separated lowerCamel segments' });
			if (typeof value !== 'string') {
				push({ level: 'error', code: 'non-string', locale: SOURCE_LOCALE, namespace, key, detail: 'message values must be strings' });
				continue;
			}
			if (!value.trim()) push({ level: 'error', code: 'empty-message', locale: SOURCE_LOCALE, namespace, key, detail: 'source message is empty' });
			const info = inspect(value);
			sourceInfo[key] = info;
			if (info.error) push({ level: 'error', code: 'syntax', locale: SOURCE_LOCALE, namespace, key, detail: info.error });
			if (info.richErrors.length) push({ level: 'error', code: 'rich-structure', locale: SOURCE_LOCALE, namespace, key, detail: info.richErrors.join('; ') });
		}

		for (const locale of TRANSLATION_LOCALES) {
			const translation = catalogs.messages[locale]?.[namespace];
			if (!translation) {
				push({ level: 'error', code: 'missing-namespace', locale, namespace, detail: `create messages/${locale}/${namespace}.json` });
				continue;
			}
			const sourceKeys = Object.keys(source);
			const translationKeys = Object.keys(translation);
			for (const key of translationKeys) {
				if (!Object.hasOwn(source, key)) push({ level: 'error', code: 'extra-key', locale, namespace, key, detail: 'key does not exist in the Korean source' });
			}
			const shared = translationKeys.filter((key) => Object.hasOwn(source, key));
			if (shared.join('\n') !== sourceKeys.filter((key) => Object.hasOwn(translation, key)).join('\n')) {
				push({ level: 'warning', code: 'key-order', locale, namespace, detail: 'key order differs from the Korean source; run `npm run i18n:format`' });
			}
			for (const key of sourceKeys) {
				const value = translation[key];
				if (value === undefined) {
					push({ level: 'error', code: 'missing-key', locale, namespace, key, detail: 'translation missing' });
					continue;
				}
				if (typeof value !== 'string') {
					push({ level: 'error', code: 'non-string', locale, namespace, key, detail: 'message values must be strings' });
					continue;
				}
				if (!value.trim()) {
					push({ level: 'error', code: 'empty-message', locale, namespace, key, detail: 'translation is empty' });
					continue;
				}
				if (HANGUL.test(value)) {
					push({ level: 'error', code: 'untranslated-hangul', locale, namespace, key, detail: 'translation still contains Korean text' });
				}
				const info = inspect(value);
				if (info.error) {
					push({ level: 'error', code: 'syntax', locale, namespace, key, detail: info.error });
					continue;
				}
				if (info.richErrors.length) push({ level: 'error', code: 'rich-structure', locale, namespace, key, detail: info.richErrors.join('; ') });
				const expected = sourceInfo[key];
				if (!expected || expected.error) continue;
				if (info.args.join(',') !== expected.args.join(',')) {
					push({ level: 'error', code: 'argument-mismatch', locale, namespace, key, detail: `expected {${expected.args.join('}, {')}} but found {${info.args.join('}, {')}}` });
				}
				if (info.tags.join('') !== expected.tags.join('')) {
					push({ level: 'error', code: 'tag-mismatch', locale, namespace, key, detail: `expected ${expected.tags.join(' ') || 'no tags'} but found ${info.tags.join(' ') || 'no tags'}` });
				}
			}
		}
	}
	return findings;
}

/**
 * @param {string} [dir]
 * @returns {Promise<ReviewManifests>}
 */
export async function loadReviews(dir = I18N_DIR) {
	/** @type {ReviewManifests} */
	const manifests = {};
	for (const locale of TRANSLATION_LOCALES) {
		const file = path.join(dir, 'review', `${locale}.json`);
		try {
			const parsed = JSON.parse(await readFile(file, 'utf8'));
			if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed) || Object.values(parsed).some((hash) => typeof hash !== 'string')) {
				throw new Error(`${locale} review manifest must be a flat JSON object of source hashes`);
			}
			manifests[locale] = parsed;
		} catch (error) {
			if (error && typeof error === 'object' && 'code' in error && error.code === 'ENOENT') manifests[locale] = {};
			else throw new Error(`Could not load ${file}: ${String(error)}`, { cause: error });
		}
	}
	return manifests;
}

/**
 * @param {Catalogs} catalogs
 * @param {ReviewManifests} reviews
 * @param {string} locale
 * @param {string} namespace
 * @param {string} key
 * @returns {ReviewState}
 */
export function reviewState(catalogs, reviews, locale, namespace, key) {
	const value = catalogs.messages[locale]?.[namespace]?.[key];
	if (typeof value !== 'string' || !value.trim()) return 'missing';
	const approved = reviews[locale]?.[`${namespace}:${key}`];
	if (!approved) return 'draft';
	return approved === sourceHash(catalogs.messages[SOURCE_LOCALE][namespace][key]) ? 'reviewed' : 'outdated';
}

/**
 * Per-locale and per-namespace review progress.
 * @param {Catalogs} catalogs
 * @param {ReviewManifests} reviews
 */
export function reviewReport(catalogs, reviews) {
	/** @type {Array<{ locale: string, namespace: string, total: number, reviewed: number, outdated: number, draft: number, missing: number }>} */
	const rows = [];
	for (const locale of TRANSLATION_LOCALES) {
		for (const namespace of Object.keys(catalogs.messages[SOURCE_LOCALE]).sort()) {
			const row = { locale, namespace, total: 0, reviewed: 0, outdated: 0, draft: 0, missing: 0 };
			for (const key of Object.keys(catalogs.messages[SOURCE_LOCALE][namespace])) {
				row.total += 1;
				row[reviewState(catalogs, reviews, locale, namespace, key)] += 1;
			}
			rows.push(row);
		}
	}
	return rows;
}

/** @param {string} value */
function csvField(value) {
	return /[",\r\n]/.test(value) ? `"${value.replaceAll('"', '""')}"` : value;
}

export const CSV_COLUMNS = ['namespace', 'key', 'source_ko', 'reference_en', 'translation', 'status'];

/**
 * Spreadsheet export for one target locale (UTF-8 with BOM so spreadsheet apps detect Korean).
 * @param {Catalogs} catalogs
 * @param {ReviewManifests} reviews
 * @param {string} locale
 * @param {{ namespaces?: string[], states?: ReviewState[] }} [filter]
 */
export function exportCsv(catalogs, reviews, locale, filter = {}) {
	const lines = [CSV_COLUMNS.join(',')];
	for (const namespace of Object.keys(catalogs.messages[SOURCE_LOCALE]).sort()) {
		if (filter.namespaces?.length && !filter.namespaces.includes(namespace)) continue;
		for (const [key, source] of Object.entries(catalogs.messages[SOURCE_LOCALE][namespace])) {
			const state = reviewState(catalogs, reviews, locale, namespace, key);
			if (filter.states?.length && !filter.states.includes(state)) continue;
			const reference = locale === 'en' ? '' : catalogs.messages.en?.[namespace]?.[key] ?? '';
			const translation = catalogs.messages[locale]?.[namespace]?.[key] ?? '';
			lines.push([namespace, key, source, reference, translation, state].map(csvField).join(','));
		}
	}
	return `\uFEFF${lines.join('\r\n')}\r\n`;
}

/**
 * RFC 4180 parser (quoted fields may contain commas, quotes and newlines).
 * @param {string} text
 * @returns {string[][]}
 */
export function parseCsv(text) {
	const input = text.startsWith('\uFEFF') ? text.slice(1) : text;
	/** @type {string[][]} */
	const rows = [];
	/** @type {string[]} */
	let row = [];
	let field = '';
	let quoted = false;
	let closedQuote = false;
	for (let i = 0; i < input.length; i += 1) {
		const ch = input[i];
		if (quoted) {
			if (ch === '"' && input[i + 1] === '"') {
				field += '"';
				i += 1;
			} else if (ch === '"') {
				quoted = false;
				closedQuote = true;
			} else {
				field += ch;
			}
		} else if (ch === '"') {
			if (field || closedQuote) throw new Error(`Invalid CSV: unexpected quote at character ${i + 1}`);
			quoted = true;
		} else if (ch === ',') {
			row.push(field);
			field = '';
			closedQuote = false;
		} else if (ch === '\n' || ch === '\r') {
			if (ch === '\r' && input[i + 1] === '\n') i += 1;
			row.push(field);
			rows.push(row);
			row = [];
			field = '';
			closedQuote = false;
		} else {
			if (closedQuote) throw new Error(`Invalid CSV: text after closing quote at character ${i + 1}`);
			field += ch;
		}
	}
	if (quoted) throw new Error('Invalid CSV: unterminated quoted field');
	if (field || row.length) {
		row.push(field);
		rows.push(row);
	}
	return rows.filter((cells) => cells.some((cell) => cell !== ''));
}

/**
 * Applies a translator's CSV to one locale. All rows are validated first; nothing is applied when
 * any row is invalid, and a row whose Korean source changed since export is rejected.
 * @param {Catalogs} catalogs
 * @param {ReviewManifests} reviews
 * @param {string} locale
 * @param {string} csvText
 * @param {{ markReviewed?: boolean }} [options]
 * @returns {{ errors: string[], updated: number }}
 */
export function importCsv(catalogs, reviews, locale, csvText, options = {}) {
	if (!TRANSLATION_LOCALES.includes(locale)) return { errors: [`${locale} is not a translation locale`], updated: 0 };
	const loadFailures = catalogLoadFailures(catalogs);
	if (loadFailures.length) return { errors: loadFailures, updated: 0 };
	/** @type {string[][]} */
	let parsed;
	try {
		parsed = parseCsv(csvText);
	} catch (error) {
		return { errors: [error instanceof Error ? error.message : String(error)], updated: 0 };
	}
	const [header, ...rows] = parsed;
	if (!header) return { errors: ['CSV header must include namespace, key, source_ko and translation'], updated: 0 };
	if (new Set(header).size !== header.length) return { errors: ['CSV header column names must be unique'], updated: 0 };
	const column = (/** @type {string} */ name) => header?.indexOf(name) ?? -1;
	const indexes = { namespace: column('namespace'), key: column('key'), source: column('source_ko'), translation: column('translation') };
	if (Object.values(indexes).some((index) => index < 0)) {
		return { errors: ['CSV header must include namespace, key, source_ko and translation'], updated: 0 };
	}
	/** @type {string[]} */
	const errors = [];
	/** @type {Array<{ namespace: string, key: string, value: string }>} */
	const changes = [];
	rows.forEach((cells, index) => {
		const line = index + 2;
		if (cells.length !== header.length) {
			errors.push(`line ${line}: expected ${header.length} CSV fields but found ${cells.length}`);
			return;
		}
		const namespace = cells[indexes.namespace] ?? '';
		const key = cells[indexes.key] ?? '';
		const value = cells[indexes.translation] ?? '';
		const source = catalogs.messages[SOURCE_LOCALE]?.[namespace]?.[key];
		if (source === undefined) {
			errors.push(`line ${line}: ${namespace}:${key} does not exist`);
			return;
		}
		if ((cells[indexes.source] ?? '') !== source) {
			errors.push(`line ${line}: ${namespace}:${key} Korean source changed since export; export again`);
			return;
		}
		if (!value.trim()) return;
		const expected = inspect(source);
		const actual = inspect(value);
		if (expected.error) errors.push(`line ${line}: ${namespace}:${key} Korean source ${expected.error}`);
		else if (expected.richErrors.length) errors.push(`line ${line}: ${namespace}:${key} Korean source ${expected.richErrors.join('; ')}`);
		else if (actual.error) errors.push(`line ${line}: ${namespace}:${key} ${actual.error}`);
		else if (actual.richErrors.length) errors.push(`line ${line}: ${namespace}:${key} ${actual.richErrors.join('; ')}`);
		else if (actual.args.join(',') !== expected.args.join(',')) errors.push(`line ${line}: ${namespace}:${key} must use {${expected.args.join('}, {')}}`);
		else if (actual.tags.join('') !== expected.tags.join('')) errors.push(`line ${line}: ${namespace}:${key} must keep ${expected.tags.join(' ')}`);
		else if (HANGUL.test(value)) errors.push(`line ${line}: ${namespace}:${key} still contains Korean text`);
		else changes.push({ namespace, key, value });
	});
	if (errors.length) return { errors, updated: 0 };
	for (const { namespace, key, value } of changes) {
		catalogs.messages[locale][namespace] ??= {};
		catalogs.messages[locale][namespace][key] = value;
		if (options.markReviewed) {
			reviews[locale][`${namespace}:${key}`] = sourceHash(catalogs.messages[SOURCE_LOCALE][namespace][key]);
		}
	}
	return { errors, updated: changes.length };
}

/**
 * Marks existing, valid translations as reviewed against the current Korean source.
 * @param {Catalogs} catalogs
 * @param {ReviewManifests} reviews
 * @param {string} locale
 * @param {string} namespace
 * @param {string[]} [keys] defaults to every key in the namespace
 */
export function markReviewed(catalogs, reviews, locale, namespace, keys) {
	const loadFailures = catalogLoadFailures(catalogs);
	if (loadFailures.length) throw new Error(loadFailures.join('\n'));
	const source = catalogs.messages[SOURCE_LOCALE]?.[namespace];
	if (!source) throw new Error(`unknown namespace ${namespace}`);
	const selected = new Set(keys?.length ? keys : Object.keys(source));
	for (const key of selected) {
		if (!Object.hasOwn(source, key)) throw new Error(`unknown key ${namespace}:${key}`);
		if (reviewState(catalogs, reviews, locale, namespace, key) === 'missing') throw new Error(`${locale} ${namespace}:${key} has no translation`);
	}
	const invalid = validateCatalogs(catalogs).find((finding) =>
		finding.level === 'error' && finding.namespace === namespace &&
		(finding.locale === SOURCE_LOCALE || finding.locale === locale) &&
		(!finding.key || selected.has(finding.key)),
	);
	if (invalid) throw new Error(`cannot review ${locale} ${namespace}:${invalid.key ?? ''}: ${invalid.detail}`);
	for (const key of selected) reviews[locale][`${namespace}:${key}`] = sourceHash(source[key]);
	return selected.size;
}

/**
 * Writes catalogs in Korean key order and prunes review entries for deleted keys.
 * @param {Catalogs} catalogs
 * @param {ReviewManifests} reviews
 * @param {string} [dir]
 */
export async function writeCatalogs(catalogs, reviews, dir = I18N_DIR) {
	const loadFailures = catalogLoadFailures(catalogs);
	if (loadFailures.length) throw new Error(loadFailures.join('\n'));
	const sourceNamespaces = catalogs.messages[SOURCE_LOCALE];
	for (const locale of LOCALES) {
		for (const namespace of Object.keys(sourceNamespaces)) {
			const current = catalogs.messages[locale]?.[namespace];
			if (!current) continue;
			/** @type {Messages} */
			const ordered = {};
			for (const key of Object.keys(sourceNamespaces[namespace])) {
				if (Object.hasOwn(current, key)) ordered[key] = current[key];
			}
			for (const key of Object.keys(current)) {
				if (!Object.hasOwn(ordered, key)) ordered[key] = current[key];
			}
			await writeFile(path.join(dir, 'messages', locale, `${namespace}.json`), `${JSON.stringify(ordered, null, '\t')}\n`);
		}
	}
	for (const locale of TRANSLATION_LOCALES) {
		/** @type {Record<string, string>} */
		const kept = {};
		for (const id of Object.keys(reviews[locale] ?? {}).sort()) {
			const separator = id.indexOf(':');
			const namespace = id.slice(0, separator);
			const key = id.slice(separator + 1);
			if (Object.hasOwn(sourceNamespaces[namespace] ?? {}, key)) kept[id] = reviews[locale][id];
		}
		await writeFile(path.join(dir, 'review', `${locale}.json`), `${JSON.stringify(kept, null, '\t')}\n`);
	}
}
