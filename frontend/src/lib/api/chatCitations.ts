import { marked } from 'marked';
import { t } from '$lib/i18n/ns/chat-panel';

export type CitationSourceKind = 'web' | 'document' | 'data_source' | 'tool_result' | 'user_input' | 'asset';
export interface Citation {
	source_kind: CitationSourceKind;
	citation_id?: string;
	source_id?: string;
	asset_id?: string;
	url?: string;
	document_index?: number;
	title?: string | null;
	snippet?: string | null;
	observed_at?: string;
	provenance?: Record<string, unknown>;
}
export const SOURCE_IDENTIFIER = /^[A-Za-z0-9_-]{1,200}$/;
const ASSET_IDENTIFIER = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
export const CITATION_SOURCE_KINDS: readonly CitationSourceKind[] = ['web', 'document', 'data_source', 'tool_result', 'user_input', 'asset'];

function parseSafeCitationHttpUrl(value: string): URL | null {
	try {
		const url = new URL(value);
		return (url.protocol === 'http:' || url.protocol === 'https:') && !url.username && !url.password ? url : null;
	} catch { return null; }
}

/** Transport links may be freshly signed; citation links use the stricter policy below. */
export function isSafeCitationHttpUrl(value: string): boolean {
	return parseSafeCitationHttpUrl(value) !== null;
}

const SOURCE_CREDENTIAL_PARAMETERS: Record<string, true> = {
	token: true, access_token: true, refresh_token: true, id_token: true, api_key: true, apikey: true, 'api-key': true,
	password: true, secret: true, client_secret: true, private_token: true, authorization: true, credential: true,
	signature: true, sig: true, key: true, temp_url_sig: true, temp_url_expires: true,
};

/** Decode parameter names once; ordinary search values and document anchors are not secrets. */
export function isPortableCitationHttpUrl(value: string): boolean {
	const url = parseSafeCitationHttpUrl(value);
	if (!url || /[\u0000-\u0020<>"\\]/.test(value)) return false;
	let fragment = url.hash.slice(1);
	const separator = fragment.indexOf('?');
	if (separator >= 0 && !/[=&]/.test(fragment.slice(0, separator))) fragment = fragment.slice(separator + 1);
	// Bare section names are not credential parameters without an assignment.
	if (!fragment.includes('=')) fragment = '';
	for (const component of [url.search.slice(1), fragment]) {
		if (!component) continue;
		// Native parse_qsl counts empty fields toward its 128-field bound.
		if (component.split('&').length > 128) return false;
		// Prefixing avoids URLSearchParams treating a literal leading '?' as syntax.
		for (const key of new URLSearchParams(`__source_guard__=&${component}`).keys()) {
			const name = key.toLowerCase();
			if (SOURCE_CREDENTIAL_PARAMETERS[name] === true || name.startsWith('x-amz-') || name.startsWith('x-goog-')) return false;
		}
	}
	return true;
}

/** The sole non-HTTP locator is an exact server-registered uploaded asset. */
export function citationAssetFallback(citation: Citation): string | null {
	return citation.source_kind === 'asset' && citation.asset_id && ASSET_IDENTIFIER.test(citation.asset_id)
		&& citation.url === `source://assets/${citation.asset_id}` ? citation.asset_id : null;
}
export function citationHref(citation: Citation): string | null {
	if (citation.url && isPortableCitationHttpUrl(citation.url)) {
		const destination = new URL(citation.url);
		if (typeof window !== 'undefined' && destination.origin === window.location.origin
			&& !destination.search && !destination.hash
			&& /^\/lumen\/sources\/(?:assets\/[A-Za-z0-9_-]+|runs\/[A-Za-z0-9_-]+\/[A-Za-z0-9_-]+)$/.test(destination.pathname)) return destination.pathname;
		return citation.url;
	}
	const assetId = citationAssetFallback(citation);
	return assetId ? `/lumen/sources/assets/${encodeURIComponent(assetId)}` : null;
}
export function citationDomain(url: string | undefined): string {
	if (!url || url.startsWith('source://')) return t('citations.inputDocument');
	try { return new URL(url).hostname.replace(/^www\./, ''); }
	catch { return url.replace(/^https?:\/\//, '').split('/')[0] || url; }
}

export function citationSourceLabel(citation: Citation): string {
	switch (citation.source_kind) {
		case 'web': return citationDomain(citation.url);
		case 'document': return t('message.inputDocument');
		case 'data_source': return t('citations.dataSource');
		case 'tool_result': return t('citations.toolResult');
		case 'user_input': return t('citations.userInput');
		case 'asset': return t('citations.asset');
	}
}
export function citationLabel(c: Citation): string {
	if (c.title?.trim()) return c.title.trim();
	if (c.source_kind === 'document' && c.document_index !== undefined) return t('citations.document', { index: c.document_index + 1 });
	return c.source_id ?? c.asset_id ?? (c.url ? citationDomain(c.url) : c.citation_id ?? t('message.sources'));
}

/** Preserve registered identity and provenance; legacy input-document indices remain valid. */
export function normalizeCitations(value: unknown): Citation[] {
	if (!Array.isArray(value)) return [];
	const out: Citation[] = [];
	for (const raw of value) {
		if (!raw || typeof raw !== 'object') continue;
		const c = raw as Record<string, unknown>;
		const kind = c.source_kind === undefined ? 'web' : c.source_kind;
		if (!CITATION_SOURCE_KINDS.includes(kind as CitationSourceKind)) continue;
		const citation: Citation = {
			source_kind: kind as CitationSourceKind,
			title: typeof c.title === 'string' ? c.title : null,
			snippet: typeof c.snippet === 'string' ? c.snippet : null
		};
		for (const key of ['citation_id', 'source_id', 'asset_id', 'observed_at'] as const) {
			if (typeof c[key] === 'string' && c[key]) citation[key] = c[key];
		}
		if (c.provenance && typeof c.provenance === 'object' && !Array.isArray(c.provenance)) citation.provenance = c.provenance as Record<string, unknown>;
		if (Number.isInteger(c.document_index) && (c.document_index as number) >= 0) citation.document_index = c.document_index as number;
		if (typeof c.url === 'string') {
			citation.url = c.url;
			if (!isPortableCitationHttpUrl(c.url) && !citationAssetFallback(citation)) continue;
		}
		if (kind === 'web' && !citation.url) continue;
		if (kind === 'asset' && (!citation.asset_id || !SOURCE_IDENTIFIER.test(citation.asset_id))) continue;
		if (kind === 'document' && citation.document_index === undefined && !citation.source_id && !citation.asset_id) continue;
		if (!['web', 'document', 'asset'].includes(kind as string) && !citation.source_id) continue;
		out.push(citation);
	}
	return out;
}

/** Keep raw answer Markdown intact and append missing portable registered links. */
export function copyMarkdownWithCitations(content: string, value: unknown): string {
	const citations = normalizeCitations(value);
	if (!citations.some((citation) => citation.url)) return content;
	const links: string[] = [];
	const seen = new Set<string>();
	marked.walkTokens(marked.lexer(content), (token) => {
		if ((token.type === 'link' || token.type === 'image') && typeof token.href === 'string') seen.add(token.href);
	});
	for (const citation of citations) {
		const url = citation.url;
		if (!url || seen.has(url)) continue;
		if (!citationAssetFallback(citation)) {
			if (!isPortableCitationHttpUrl(url)) continue;
			const parsed = new URL(url);
			// Legacy UI copy exclusions must not broaden the native citation wire validator.
			if ([...parsed.searchParams.keys()].some((key) => /^auth$/i.test(key))) continue;
			// Asset/run links are permanent pages, never object-store signatures.
			if (['tool_result', 'user_input', 'asset'].includes(citation.source_kind) && (parsed.search || parsed.hash || !/^\/lumen\/sources\/(?:assets\/[A-Za-z0-9_-]+|runs\/[A-Za-z0-9_-]+\/[A-Za-z0-9_-]+)$/.test(parsed.pathname))) continue;
		}
		seen.add(url);
		const label = citationLabel(citation).replace(/[\r\n]+/g, ' ').replace(/[\\[\]]/g, '\\$&');
		const destination = url.replace(/[<>\r\n\\]/g, (character) => encodeURIComponent(character));
		links.push(`- [${label}](<${destination}>)`);
	}
	return links.length ? `${content}\n\n## ${t('message.sources')}\n\n${links.join('\n')}` : content;
}

export function aggregateCitations(messages: { citations?: unknown; parts?: unknown }[]): Citation[] {
	const bySource = new Map<string, Citation>();
	for (const message of messages) {
		const canonical = Array.isArray(message.parts) ? message.parts.filter((part) => part && typeof part === 'object' && part.type === 'citation') : [];
		for (const citation of normalizeCitations([...(Array.isArray(message.citations) ? message.citations : []), ...canonical])) {
			const key = citation.source_kind === 'data_source' && citation.source_id ? `data_source:${citation.source_id}`
				: citation.url ? `${citation.source_kind}:${citation.url}`
				: citation.source_id ? `${citation.source_kind}:${citation.source_id}`
				: citation.asset_id ? `asset:${citation.asset_id}`
				: `document:${citation.document_index}`;
			const existing = bySource.get(key);
			if (!existing) bySource.set(key, citation);
			else {
				if (!existing.title && citation.title) existing.title = citation.title;
				if (!existing.snippet && citation.snippet) existing.snippet = citation.snippet;
				for (const key of ['url', 'citation_id', 'source_id', 'asset_id', 'observed_at'] as const) {
					if (!existing[key] && citation[key]) existing[key] = citation[key];
				}
				if (!existing.provenance && citation.provenance) existing.provenance = citation.provenance;
			}
		}
	}
	return [...bySource.values()];
}
