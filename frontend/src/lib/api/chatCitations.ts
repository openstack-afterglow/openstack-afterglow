/**
 * 채팅 답변 출처(citations) — 표시/집계 순수 함수.
 *
 * 백엔드는 web URL 또는 provider 입력 문서의 index 기반 citation을 저장/스트리밍한다.
 * 메시지 상단 출처 리스트와 "대화 전체 출처" 패널이 이 유틸을 공유한다.
 */

export interface Citation {
	source_kind: 'web' | 'document';
	url?: string;
	document_index?: number;
	title?: string | null;
	snippet?: string | null;
}

/** URL 에서 표시용 도메인(호스트, www 제거) 추출. */
export function citationDomain(url: string | undefined): string {
	if (!url) return '입력 문서';
	try {
		const host = new URL(url).hostname;
		return host.replace(/^www\./, '');
	} catch {
		return url.replace(/^https?:\/\//, '').split('/')[0] || url;
	}
}

/** 출처의 표시 라벨 — title 우선, 문서 index 또는 도메인. */
export function citationLabel(c: Citation): string {
	const title = c.title?.trim();
	if (title) return title;
	if (c.source_kind === 'document') return `문서 ${(c.document_index ?? 0) + 1}`;
	return citationDomain(c.url);
}

/** http/https URL 만 허용(javascript:·data: 등 스킴 클릭 실행 방어). */
function isSafeHttpUrl(url: string): boolean {
	try {
		const u = new URL(url);
		return u.protocol === 'http:' || u.protocol === 'https:';
	} catch {
		return false;
	}
}

/** unknown(저장/스트림) → Citation[] 방어적 정규화. */
export function normalizeCitations(value: unknown): Citation[] {
	if (!Array.isArray(value)) return [];
	const out: Citation[] = [];
	for (const raw of value) {
		if (!raw || typeof raw !== 'object') continue;
		const c = raw as Record<string, unknown>;
		const title = typeof c.title === 'string' ? c.title : null;
		const snippet = typeof c.snippet === 'string' ? c.snippet : null;
		if (typeof c.url === 'string' && isSafeHttpUrl(c.url)) {
			out.push({ source_kind: 'web', url: c.url, title, snippet });
			continue;
		}
		if (c.source_kind === 'document' && Number.isInteger(c.document_index) && (c.document_index as number) >= 0) {
			out.push({ source_kind: 'document', document_index: c.document_index as number, title, snippet });
		}
	}
	return out;
}

/**
 * 여러 메시지의 출처를 URL 또는 입력 문서 index 기준으로 중복 제거한다.
 * 더 풍부한 항목(title/snippet 보유)으로 업그레이드한다.
 */
export function aggregateCitations(messages: { citations?: unknown }[]): Citation[] {
	const bySource = new Map<string, Citation>();
	for (const message of messages) {
		for (const citation of normalizeCitations(message.citations)) {
			const key =
				citation.source_kind === 'web'
					? `web:${citation.url}`
					: `document:${citation.document_index}`;
			const existing = bySource.get(key);
			if (!existing) {
				bySource.set(key, citation);
			} else {
				if (!existing.title && citation.title) existing.title = citation.title;
				if (!existing.snippet && citation.snippet) existing.snippet = citation.snippet;
			}
		}
	}
	return [...bySource.values()];
}
