import {
	DEFAULT_LOCALE,
	FALLBACK_CHAIN,
	INTL_LOCALES,
	LOCALE_COOKIE,
	LOCALE_COOKIE_MAX_AGE_SECONDS,
	type Locale,
} from './locales';
import { formatMessage, parseMessage, type MessageNode, type MessageValues } from './messageFormat.js';
import { RICH_VALUE_CLOSE, RICH_VALUE_OPEN, buildRichSegments, type RichSegment } from './rich';

/**
 * The active interface language.
 *
 * On the server this module is shared by every request, so the root layout calls `initLocale`
 * synchronously at the start of each render and nothing may translate in `load` functions or at
 * module scope. Svelte's server render is synchronous, so one request cannot observe another's
 * locale mid-render.
 */
let current = $state<Locale>(DEFAULT_LOCALE);
/** In-context review mode: every message renders as `namespace:key`. Client-only. */
let showKeys = $state(false);

export const KEY_DEBUG_STORAGE_KEY = 'afterglow.i18n.debug';

export function getLocale(): Locale {
	return current;
}

/** BCP 47 tag for `Intl` formatters and `toLocale*String` in the active language. */
export function intlLocale(): string {
	return INTL_LOCALES[current];
}

/** Render-time initialization for SSR and hydration; never persists the preference. */
export function initLocale(locale: Locale): void {
	current = locale;
}

/** User choice: persists for SSR, updates `<html lang>` and re-renders every message. */
export function setLocale(locale: Locale): void {
	current = locale;
	if (typeof document === 'undefined') return;
	const secure = location.protocol === 'https:' ? '; Secure' : '';
	document.cookie = `${LOCALE_COOKIE}=${locale}; path=/; max-age=${LOCALE_COOKIE_MAX_AGE_SECONDS}; SameSite=Lax${secure}`;
	document.documentElement.lang = locale;
}

/** Called after hydration so the server and client markup agree on the first render. */
export function restoreKeyDebugMode(): void {
	try {
		showKeys = localStorage.getItem(KEY_DEBUG_STORAGE_KEY) === 'keys';
	} catch {
		showKeys = false;
	}
}

export interface Translator<Key extends string> {
	(key: Key, values?: MessageValues): string;
	/** Segments for `<RichText>` when the message contains `<strong>`, `<code>` or snippet tags. */
	rich(key: Key, values?: MessageValues): RichSegment[];
}

const CATALOG_LOCALE = /\/messages\/([^/]+)\/[^/]+\.json$/;
const INVALID = Symbol('invalid message');
const warned = new Set<string>();

function warnOnce(id: string, detail: string): void {
	if (!import.meta.env?.DEV || warned.has(id)) return;
	warned.add(id);
	console.warn(`[i18n] ${detail}`);
}

/**
 * Binds one namespace's catalogs (all locales, bundled with the code that imports them).
 * Keys are typed from the Korean source catalog, so `svelte-check` rejects unknown keys.
 */
export function defineMessages<Source extends Record<string, string>>(
	namespace: string,
	modules: Record<string, Record<string, string>>,
): Translator<Extract<keyof Source, string>> {
	const catalogs = new Map<string, Record<string, string>>();
	for (const [path, messages] of Object.entries(modules)) {
		const locale = CATALOG_LOCALE.exec(path)?.[1];
		if (locale) catalogs.set(locale, messages);
	}
	const parsed = new Map<string, MessageNode[] | typeof INVALID>();

	const resolve = (key: string): { intl: string; nodes: MessageNode[] } | null => {
		for (const locale of FALLBACK_CHAIN[current]) {
			const source = catalogs.get(locale)?.[key];
			if (typeof source !== 'string') continue;
			const cacheKey = `${locale}\u0000${key}`;
			let nodes = parsed.get(cacheKey);
			if (nodes === undefined) {
				try {
					nodes = parseMessage(source);
				} catch (error) {
					nodes = INVALID;
					warnOnce(cacheKey, `${locale} ${namespace}:${key} is not a valid message: ${String(error)}`);
				}
				parsed.set(cacheKey, nodes);
			}
			if (nodes !== INVALID) return { intl: INTL_LOCALES[locale], nodes };
		}
		warnOnce(`${namespace}:${key}`, `missing message ${namespace}:${key}`);
		return null;
	};

	const translate = (key: string, values?: MessageValues): string => {
		if (showKeys) return `${namespace}:${key}`;
		const message = resolve(key);
		return message ? formatMessage(message.nodes, values, message.intl) : `${namespace}:${key}`;
	};

	const rich = (key: string, values?: MessageValues): RichSegment[] => {
		if (showKeys) return [{ type: 'text', value: `${namespace}:${key}` }];
		const message = resolve(key);
		if (!message) return [{ type: 'text', value: `${namespace}:${key}` }];
		const inserted: string[] = [];
		const formatted = formatMessage(message.nodes, values, message.intl, (value) => {
			inserted.push(String(value));
			return `${RICH_VALUE_OPEN}${inserted.length - 1}${RICH_VALUE_CLOSE}`;
		});
		return buildRichSegments(formatted, inserted);
	};

	return Object.assign(translate, { rich });
}
