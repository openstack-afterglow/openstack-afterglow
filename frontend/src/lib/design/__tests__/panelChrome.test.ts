// SlidePanel 안에 렌더되는 자식 패널이 **자기 닫기 버튼을 그리지 않는다**는 정적 규칙.
//
// 배경: 사용자가 네트워크 상세에서 × 가 두 개 보인다고 신고했고, 전수 조사에서 같은 부류가 21곳 더 나왔다.
// `SlidePanel.svelte` 는 `[data-slide-panel-close]` 버튼을 항상 그리므로 자식이 또 그리면 헤더에 닫기가 두 개 보인다.
//
// 런타임 테스트로는 못 잡는다 — 자식 컴포넌트를 단독 렌더하면 SlidePanel 이 없어서 중복이 드러나지 않고,
// 21개 패널마다 SlidePanel 조합 테스트를 만드는 것도 유지되지 않는다. 그래서 소스 스캔으로 고정한다.
import { describe, expect, it } from 'vitest';
import { readdir, readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../../..');
const sourceRoot = path.join(repoRoot, 'frontend/src');

async function collectSvelte(dir: string): Promise<string[]> {
	const entries = await readdir(dir, { withFileTypes: true });
	const nested = await Promise.all(
		entries.map(async (entry) => {
			const full = path.join(dir, entry.name);
			if (entry.isDirectory()) return collectSvelte(full);
			if (entry.isFile() && entry.name.endsWith('.svelte')) return [full];
			return [];
		}),
	);
	return nested.flat();
}

const rel = (p: string) => path.relative(repoRoot, p).split(path.sep).join('/');

/** `<SlidePanel …>` 여닫는 구간 안에서 직접 렌더되는 자식 컴포넌트 이름 */
function slidePanelChildren(source: string): string[] {
	const out: string[] = [];
	const re = /<SlidePanel\b[\s\S]*?<\/SlidePanel>/g;
	for (const block of source.match(re) ?? []) {
		for (const m of block.matchAll(/<([A-Z][A-Za-z0-9_]*)\b/g)) {
			if (m[1] !== 'SlidePanel') out.push(m[1]);
		}
	}
	return [...new Set(out)];
}

/**
 * 닫기 성격의 버튼. 다음 셋 중 하나면 닫기로 본다.
 * - 본문이 닫기 글리프(×, ✕, &times;)뿐인 버튼
 * - `aria-label` 에 "닫기" 가 들어간 버튼
 * - 본문이 `✕ 닫기` / `← 목록으로` 같은 dismiss 문구인 버튼
 *
 * 푸터의 `취소`/`닫기` 텍스트 버튼은 별개 어포던스라 제외한다(글리프도 aria-label 도 없다).
 */
function findCloseButtons(source: string): Array<{ line: number; snippet: string }> {
	const hits: Array<{ line: number; snippet: string }> = [];
	const lineOf = (idx: number) => source.slice(0, idx).split('\n').length;
	for (const m of source.matchAll(/<button\b[^>]*>([\s\S]{0,80}?)<\/button>/g)) {
		const tag = m[0].slice(0, m[0].indexOf('>') + 1);
		const body = m[1].replace(/<!--[\s\S]*?-->/g, '').trim();
		const ariaClose = /aria-label="[^"]*닫기[^"]*"/.test(tag);
		const glyphOnly = /^(×|✕|&times;)$/.test(body);
		const dismissText = /^(✕\s*닫기|×\s*닫기|←\s*목록으로)$/.test(body);
		if (ariaClose || glyphOnly || dismissText) {
			hits.push({ line: lineOf(m.index ?? 0), snippet: body.slice(0, 24) || tag.slice(0, 40) });
		}
	}
	return hits;
}

describe('SlidePanel 자식은 자기 닫기 버튼을 그리지 않는다', () => {
	it('SlidePanel 이 그리는 닫기 버튼은 정확히 하나다', async () => {
		const source = await readFile(path.join(sourceRoot, 'lib/components/SlidePanel.svelte'), 'utf8');
		const marks = source.match(/data-slide-panel-close/g) ?? [];
		// 정의 1회 + 초기 포커스/포커스 트랩 셀렉터 참조들. 버튼 자체는 하나여야 한다.
		expect(source.match(/<button[^>]*data-slide-panel-close/g) ?? []).toHaveLength(1);
		expect(marks.length).toBeGreaterThanOrEqual(1);
	});

	it('SlidePanel 안에서 렌더되는 컴포넌트 트리 전체에 닫기 버튼이 없다', async () => {
		const files = await collectSvelte(sourceRoot);
		const byName = new Map<string, string>();
		for (const f of files) byName.set(path.basename(f, '.svelte'), f);

		// 1) SlidePanel 사용처에서 직속 자식을 모으고
		const seeds = new Set<string>();
		for (const f of files) {
			if (f.endsWith('SlidePanel.svelte')) continue;
			for (const name of slidePanelChildren(await readFile(f, 'utf8'))) seeds.add(name);
		}
		expect(seeds.size, 'SlidePanel 사용처를 하나도 못 찾았다면 스캐너가 깨진 것이다').toBeGreaterThan(5);

		// 2) 그 아래로 전이 확장한다 — 실제 위반은 대부분 Panel → Header 한 단 아래에 있다.
		//    자체 대화상자(ui/ 프리미티브, role=dialog·aria-modal 보유)는 자기 크롬을 소유하므로 확장에서 끊는다.
		const source = new Map<string, string>();
		const readOnce = async (name: string): Promise<string | null> => {
			const file = byName.get(name);
			if (!file) return null;
			if (!source.has(name)) source.set(name, await readFile(file, 'utf8'));
			return source.get(name)!;
		};
		// 자기 크롬을 소유하는 표면: ui/ 프리미티브, 대화상자 선언, 또는 전면 오버레이 구조.
		// 패널 안에서 열리는 중첩 모달·오버레이(K3s 인증서/쉘/에디터 등)는 자기 × 를 갖는 것이 정상이다.
		const ownsChrome = (name: string, src: string) =>
			(byName.get(name) ?? '').includes('/lib/components/ui/')
			|| /role="dialog"|aria-modal/.test(src)
			|| /(?:fixed|absolute)\s+inset-0/.test(src);

		const tree = new Set<string>();
		const queue = [...seeds];
		while (queue.length) {
			const name = queue.shift()!;
			if (tree.has(name)) continue;
			const src = await readOnce(name);
			if (src === null) continue;
			if (ownsChrome(name, src)) continue; // 자체 크롬 소유 → 이 아래는 보지 않는다
			tree.add(name);
			for (const m of src.matchAll(/<([A-Z][A-Za-z0-9_]*)\b/g)) {
				if (m[1] !== 'SlidePanel' && !tree.has(m[1])) queue.push(m[1]);
			}
		}
		expect(tree.size, '전이 확장이 되지 않았다면 스캐너가 깨진 것이다').toBeGreaterThan(seeds.size);

		const offenders: string[] = [];
		for (const name of [...tree].sort()) {
			const src = source.get(name);
			const file = byName.get(name);
			if (!src || !file) continue;
			for (const hit of findCloseButtons(src)) {
				offenders.push(`${rel(file)}:${hit.line} — ${hit.snippet}`);
			}
		}
		expect(
			offenders,
			'SlidePanel 이 이미 닫기 버튼을 그린다. 자식에서 지우고, 투어가 그 버튼을 노리면 셀렉터를 [data-slide-panel-close] 로 재배선하라.',
		).toEqual([]);
	});

	it('튜토리얼 투어는 자식 패널의 닫기 버튼을 셀렉터로 노리지 않는다', async () => {
		const tours = await readFile(path.join(sourceRoot, 'lib/tutorial/tours.ts'), 'utf8');
		// 자식이 그리던 data-tour 는 제거됐다 — 남아 있으면 투어가 조용히 깨진다
		expect(tours).not.toMatch(/data-tour="[^"]*detail-close"/);
	});
});
