/**
 * 채팅 마크다운 렌더링 + 코드 하이라이트.
 *
 * - marked 로 마크다운 → HTML, DOMPurify.sanitize 로 XSS 방어(<script> 등 제거).
 * - shiki 는 무거우므로 동적 import 로 지연 로딩하고, 스트리밍 중에는 호출하지 않는다
 *   (델타마다 재하이라이트하면 버벅임). 스트리밍 완료 후 한 번만 코드블록을 하이라이트한다.
 * - shiki 출력은 자체적으로 코드 텍스트를 HTML escape 하므로(XSS 안전) DOMPurify 를
 *   거치지 않고 삽입한다. 이렇게 해야 dual-theme 용 CSS 커스텀 프로퍼티가 제거되지 않는다.
 */
import { marked, type TokenizerAndRendererExtension } from 'marked';
import DOMPurify from 'dompurify';

marked.setOptions({ breaks: true, gfm: true });

// content-keyed 파싱/살균 결과 캐시. 완료된(스트리밍 끝난) 메시지는 content 가
// 고정이므로 재파싱/재살균을 피한다(예: tmp→real id 스왑으로 컴포넌트가 재마운트돼도 히트).
// 스트리밍 중 partial 은 매번 달라 캐시 이득이 없으므로 캐시를 쓰지 않는다(무한 증가 방지).
const RENDER_CACHE = new Map<string, string>();
const RENDER_CACHE_MAX = 200;

const mathBlockExtension: TokenizerAndRendererExtension = {
	name: 'chatMathBlock',
	level: 'block',
	start(src) {
		const match = /(?:^\n?|\n)(?:\$\$|\\\[)/.exec(src);
		return match?.index;
	},
	tokenizer(src) {
		const match =
			/^\$\$([^\n]+?)\$\$(?:\n|$)/.exec(src) ??
			/^\$\$[ \t]*\n([\s\S]*?)\n\$\$[ \t]*(?:\n|$)/.exec(src) ??
			/^\\\[[ \t]*\n([\s\S]*?)\n\\\][ \t]*(?:\n|$)/.exec(src);
		if (!match) return;
		return { type: 'chatMathBlock', raw: match[0], text: match[1] };
	},
	renderer(token) {
		return `<div class="math-display" data-chat-math="afterglow:${encodeURIComponent(token.text)}"></div>`;
	}
};

// CommonMark rejects a closing ** directly after punctuation when the following
// Korean text has no separator. Only intercept that unsupported shape; ordinary
// strong tokens continue through Marked's native tokenizer.
const chatStrongExtension: TokenizerAndRendererExtension = {
	name: 'chatStrong',
	level: 'inline',
	start(src) {
		const index = src.indexOf('**');
		return index >= 0 ? index : undefined;
	},
	tokenizer(src) {
		const match = /^\*\*((?:(?!\*\*)[^\n])*?[)\]:;,.!?])\*\*(?=\S)/.exec(src);
		if (!match) return;
		return {
			type: 'chatStrong',
			raw: match[0],
			text: match[1],
			tokens: this.lexer.inlineTokens(match[1])
		};
	},
	renderer(token) {
		return `<strong>${this.parser.parseInline(token.tokens ?? [])}</strong>`;
	}
};

const mathInlineExtension: TokenizerAndRendererExtension = {
	name: 'chatMathInline',
	level: 'inline',
	start(src) {
		const match = /(?<!\\)(?:\$|\\\()/.exec(src);
		return match?.index;
	},
	tokenizer(src) {
		const match =
			/^\$((?:\\.|[^$\\\n])+?)\$/.exec(src) ?? /^\\\(([\s\S]*?)\\\)/.exec(src);
		if (!match) return;
		return { type: 'chatMathInline', raw: match[0], text: match[1] };
	},
	renderer(token) {
		return `<span class="math-inline" data-chat-math="afterglow:${encodeURIComponent(token.text)}"></span>`;
	}
};

marked.use({ extensions: [mathBlockExtension, chatStrongExtension, mathInlineExtension] });

/**
 * 마크다운을 살균된 HTML 로 변환한다. 코드블록은 아직 하이라이트하지 않은
 * plain <pre><code class="language-xxx"> 형태(스트리밍 중에도 안전하게 즉시 렌더).
 * @param opts.cache 완료된 메시지에 한해 결과를 캐시(스트리밍 중에는 false 로 호출).
 */
export function renderMarkdown(source: string, opts?: { cache?: boolean }): string {
	const useCache = opts?.cache ?? false;
	const key = source ?? '';
	if (useCache) {
		const hit = RENDER_CACHE.get(key);
		if (hit !== undefined) return hit;
	}
	const raw = marked.parse(key, { async: false }) as string;
	const html = DOMPurify.sanitize(raw, {
		ADD_ATTR: ['target', 'rel', 'data-chat-math'],
		FORBID_TAGS: ['style', 'form', 'input', 'button'],
		FORBID_ATTR: ['onerror', 'onload', 'onclick']
	});
	if (useCache) {
		if (RENDER_CACHE.size >= RENDER_CACHE_MAX) {
			const oldest = RENDER_CACHE.keys().next().value;
			if (oldest !== undefined) RENDER_CACHE.delete(oldest);
		}
		RENDER_CACHE.set(key, html);
	}
	return html;
}

type CodeToHtml = (code: string, options: Record<string, unknown>) => Promise<string>;

let codeToHtmlPromise: Promise<CodeToHtml> | null = null;

/** shiki 를 지연 로딩해 codeToHtml 를 반환(모듈 단위 싱글턴). */
function getCodeToHtml(): Promise<CodeToHtml> {
	if (!codeToHtmlPromise) {
		codeToHtmlPromise = import('shiki').then(
			(mod) => (mod as unknown as { codeToHtml: CodeToHtml }).codeToHtml
		);
	}
	return codeToHtmlPromise;
}

function langFromClass(el: Element): string {
	const cls = el.getAttribute('class') ?? '';
	const m = cls.match(/language-([\w+-]+)/);
	return m ? m[1] : 'text';
}

/**
 * 주어진 컨테이너 내부의 모든 <pre><code> 블록을 shiki 로 하이라이트한다.
 * 완료(스트리밍 종료) 후 한 번만 호출한다. 이미 처리된 블록은 건너뛴다.
 */
export async function highlightCodeBlocks(container: HTMLElement): Promise<void> {
	const blocks = Array.from(container.querySelectorAll('pre > code')).filter((el) => {
		const pre = el.closest('pre');
		return !pre?.hasAttribute('data-shiki') && !el.classList.contains('language-mermaid');
	});
	if (blocks.length === 0) return;

	const codeToHtml = await getCodeToHtml();

	for (const code of blocks) {
		const pre = code.closest('pre');
		if (!pre) continue;
		const lang = langFromClass(code);
		const text = code.textContent ?? '';
		try {
			const html = await codeToHtml(text, {
				lang,
				themes: { light: 'github-light', dark: 'github-dark' },
				defaultColor: false
			});
			// shiki 는 <pre class="shiki">...</pre> 전체를 반환. 기존 pre 를 교체.
			const tpl = document.createElement('template');
			tpl.innerHTML = html.trim();
			const next = tpl.content.firstElementChild;
			if (next instanceof HTMLElement) {
				next.setAttribute('data-shiki', '');
				pre.replaceWith(next);
			} else {
				pre.setAttribute('data-shiki', '');
			}
		} catch {
			// 미지원 언어 등: 원본 유지, 재시도 방지 플래그만
			pre.setAttribute('data-shiki', '');
		}
	}
}
