#!/usr/bin/env python3
"""Generate portable text-only theme assets from the canonical character registry."""
from __future__ import annotations
import argparse
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'frontend/src/lib/design/characterAssets.json'
DEST = ROOT / 'frontend/static/theme/afterglow'
CATEGORIES = {'state': '상태', 'infrastructure': '인프라', 'experience': 'AI · 미디어', 'workspace': '워크스페이스', 'transfer': '전송 · 작업'}

CATALOG_HTML = '''<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Afterglow · Universal character assets</title><link rel="stylesheet" href="catalog.css"><script src="catalog.js" defer></script></head>
<body><header><p class="eyebrow">AFTERGLOW / UNIVERSAL CHARACTER THEME</p><h1>어디서든 같은 시각 언어.</h1><p>인프라부터 미디어, 작업 상태까지. 문자로 구성한 공통 에셋 라이브러리입니다.</p><div class="toolbar"><label>환경 <select id="category"><option value="all">전체 에셋</option></select></label><button id="appearance" type="button" aria-pressed="false">라이트 테마 보기</button><a href="manifest.json" download>전체 명세 JSON ↓</a><a href="motion.html">Progress · Status 타입 ↗</a></div><p id="count" role="status" aria-live="polite"></p></header><main id="catalog"></main><footer><p>그래픽은 문자로만 구성됩니다. 실제 데이터·상태 설명·오류 복구는 사용하는 화면이 제공합니다.</p><p>SVG는 투명 배경의 기본 웜 색상 파일이며, 앱의 실시간 테마 전환에는 AssetGlyph 또는 TXT의 상속 색상을 사용합니다.</p><a href="README.md">사용 가이드 ↗</a></footer></body></html>
'''
CATALOG_CSS = '''
:root{color-scheme:dark;--base:#101113;--surface:#151618;--ink:#f1f0ee;--muted:#a5a5ab;--line:#2b2d31;--warm:#f4976c;--light:#e8c19a;font-family:Inter,ui-sans-serif,system-ui,sans-serif;background:var(--base);color:var(--ink)}
:root[data-theme=light]{color-scheme:light;--base:#f4f5f7;--surface:#fff;--ink:#242529;--muted:#62656b;--line:#d6d9df;--warm:#9a3d1c;--light:#9a3d1c}
*{box-sizing:border-box}body{margin:0;padding:clamp(1.25rem,4vw,4rem);max-width:1600px;margin-inline:auto}header{margin-bottom:2rem}.eyebrow{font:.6875rem ui-monospace,SFMono-Regular,Consolas,monospace;letter-spacing:.16em;color:var(--light)}h1{font-size:clamp(1.8rem,3.4vw,3rem);font-weight:450;letter-spacing:-.04em}p{font-size:.875rem;color:var(--muted);line-height:1.7}.toolbar{display:flex;flex-wrap:wrap;align-items:center;gap:1rem}.toolbar label{display:flex;align-items:center;gap:.6rem;font-size:.8125rem}button,select,.toolbar>a{font:inherit;font-size:.8125rem;min-height:44px;padding:.65rem .9rem;background:var(--surface);color:var(--ink);border:1px solid var(--line);border-radius:.4rem}button,select{cursor:pointer}a{color:var(--warm);text-decoration:none}button:hover,a:hover{color:var(--warm)}button:focus-visible,select:focus-visible,a:focus-visible{outline:2px solid var(--warm);outline-offset:4px}#catalog{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:1rem}.asset{background:var(--surface);border:1px solid var(--line);border-radius:.75rem;overflow:hidden;min-width:0;padding:1.25rem}.art{min-height:11.5rem;display:grid;align-items:center;justify-content:center;overflow:hidden}pre{font:clamp(10px,.85vw,13px)/1.35 ui-monospace,SFMono-Regular,Consolas,monospace;color:var(--warm);margin:0;white-space:pre;user-select:none}h2{font-size:.875rem;font-weight:500;margin:.75rem 0 .3rem}.identifier{font:.6875rem ui-monospace,monospace;color:var(--muted);overflow-wrap:anywhere}.links{display:flex;gap:1rem;border-top:1px solid var(--line);padding-top:.5rem;margin-top:1rem}.links a{min-height:44px;display:inline-flex;align-items:center;font:.75rem ui-monospace,monospace}footer{margin-top:2rem}footer a{display:inline-flex;align-items:center;min-height:44px;font-size:.8125rem}[hidden]{display:none!important}@media(max-width:1199px){#catalog{grid-template-columns:repeat(3,minmax(0,1fr))}}@media(max-width:1023px){#catalog{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:639px){#catalog{grid-template-columns:minmax(0,1fr)}pre{font-size:12px}.toolbar{align-items:stretch}.toolbar label{width:100%}.toolbar select{min-width:0;flex:1}.art{min-height:10rem}}
'''
CATALOG_JS = '''
'use strict';
const registry = __REGISTRY__;
const categories = __CATEGORIES__;
const catalog = document.querySelector('#catalog');
const filter = document.querySelector('#category');
for (const [id,label] of Object.entries(categories)) { const option=document.createElement('option');option.value=id;option.textContent=label;filter.append(option); }
for (const [id,asset] of Object.entries(registry)) {
 const card=document.createElement('article');card.className='asset';card.dataset.category=asset.category;
 const art=document.createElement('div');art.className='art';
 const pre=document.createElement('pre');pre.setAttribute('aria-hidden','true');pre.textContent=asset.art;art.append(pre);
 const heading=document.createElement('h2');heading.textContent=asset.label;
 const code=document.createElement('span');code.className='identifier';code.textContent=id+' / '+asset.category;
 const links=document.createElement('div');links.className='links';
 for (const ext of ['svg','txt']) { const link=document.createElement('a');link.href=id+'.'+ext;link.download=id+'.'+ext;link.textContent=ext.toUpperCase()+' ↓';link.setAttribute('aria-label',asset.label+' '+ext.toUpperCase()+' 다운로드');links.append(link); }
 card.append(art,heading,code,links);catalog.append(card);
}
function update(){let count=0;for(const card of catalog.children){card.hidden=filter.value!=='all'&&card.dataset.category!==filter.value;if(!card.hidden)count++;}document.querySelector('#count').textContent=count+'개 에셋 · 정적 문자 그래픽';}
filter.addEventListener('change',update);update();
document.querySelector('#appearance').addEventListener('click',event=>{const light=document.documentElement.dataset.theme!=='light';document.documentElement.dataset.theme=light?'light':'dark';event.currentTarget.setAttribute('aria-pressed',String(light));event.currentTarget.textContent=light?'다크 테마 보기':'라이트 테마 보기';});
'''
README = '''# Afterglow universal character theme

These portable assets are generated from `frontend/src/lib/design/characterAssets.json` by `python3 scripts/generate-character-assets.py`. Do not hand-edit exported TXT/SVG/catalog/manifest files. `--check` reports missing, changed or obsolete generated assets without writing.

Open `index.html` directly to browse/filter the full catalogue in light/dark appearances. It works from disk without fetching JSON or using a server. All artwork is text-only, static and decorative. No simulated work, percentages, provider calls or media capture occur.

## Files

- `<id>.txt`: exact Unicode character layout; preserve whitespace in a monospace `<pre>` or terminal.
- `<id>.svg`: transparent, text-only SVG using generic monospace; no shapes, paths, embedded images or external fonts. Default warm color is baked as a fallback. Host SVG text font availability may alter appearance; fixed glyph fidelity is not claimed.
- `manifest.json`: version, categories, labels, art and relative file names.
- `index.html`, `catalog.css`, `catalog.js`: standalone review catalogue.

## Integration

In Afterglow use `<AssetGlyph variant="compute" />` and the canonical registry, not raw copies. The existing component supplies theme/font/forced-color behavior; the page owns translated status, headings and recovery actions. Use `LoadingState` and `ProgressTrack` for actual pending or measured progress; `processing`/`progress` files are static illustrations and must never manufacture backend authority or percentages. Treat decorative SVG/TXT as `aria-hidden`, or provide a localized accessible name when the image conveys meaning. Links, controls, real charts, topology, provider branding, uploaded/generated media and operator logos retain their actual semantics/content.

For other frameworks use manifest/TXT with `white-space: pre`, a monospace font, line-height around 1.2–1.35, and host theme colors. SVG loaded through `<img>` is an isolated image: parent CSS variables do not recolor it. For live theme colors use text/inline trusted SVG. No theme persistence or global preference changes are performed by the standalone catalogue.
'''

def load_assets() -> dict:
    data = json.loads(SOURCE.read_text())
    if not isinstance(data, dict) or not data:
        raise ValueError('registry must be a nonempty object')
    for key, value in data.items():
        if not re.fullmatch(r'[a-z][a-z0-9-]*', key):
            raise ValueError(f'invalid asset id: {key}')
        if value.get('category') not in CATEGORIES or not all(isinstance(value.get(k), str) and value[k] for k in ('label', 'art')):
            raise ValueError(f'invalid asset: {key}')
        if any(ord(c) < 32 and c != '\n' for c in value['art']):
            raise ValueError(f'unsupported control character: {key}')
    return data

def outputs(data: dict) -> dict[str, str]:
    result = {}
    manifest = {'version': 1, 'theme': 'afterglow', 'categories': CATEGORIES, 'assets': {}}
    for key, asset in data.items():
        art = asset['art']; lines = art.split('\n')
        width = max(len(line) for line in lines) * 9 + 24; height = len(lines) * 18 + 20
        rows = '\n'.join(f'  <text x="12" y="{24 + i * 18}">{html.escape(line)}</text>' for i, line in enumerate(lines))
        result[key + '.txt'] = art + '\n'
        result[key + '.svg'] = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-labelledby="afterglow-{key}-title" style="color:var(--afterglow-artwork-warm,#f4976c)">
<title id="afterglow-{key}-title">{html.escape(asset['label'])}</title>
<g fill="currentColor" font-family="monospace" font-size="14" xml:space="preserve">
{rows}
</g></svg>
'''
        manifest['assets'][key] = {**asset, 'txt': key + '.txt', 'svg': key + '.svg'}
    result['manifest.json'] = json.dumps(manifest, ensure_ascii=False, indent=2) + '\n'
    result['index.html'] = CATALOG_HTML
    result['catalog.css'] = CATALOG_CSS.strip() + '\n'
    result['catalog.js'] = CATALOG_JS.replace('__REGISTRY__', json.dumps(data, ensure_ascii=False)).replace('__CATEGORIES__', json.dumps(CATEGORIES, ensure_ascii=False)).strip() + '\n'
    result['README.md'] = README
    helper = (ROOT / 'frontend/src/lib/design/characterFormats.js').read_text()
    result['character-formats.js'] = '(() => {\n' + helper.replace('export ', '') + '\nwindow.AfterglowCharacterFormats = {circularProgress, linearProgress, statusSignal, settledSignal};\n})();\n'
    for name in ('motion.html', 'motion.css', 'motion.js'):
        result[name] = (ROOT / 'scripts/character-assets' / name).read_text()
    return result

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='compare exports without writing')
    args = parser.parse_args()
    data = load_assets(); expected = outputs(data)
    mismatches = [name for name, content in expected.items() if not (DEST / name).is_file() or (DEST / name).read_text() != content]
    obsolete = [p.name for p in DEST.glob('*') if p.suffix in {'.txt', '.svg'} and p.name not in expected]
    if args.check:
        if mismatches or obsolete:
            print('asset exports differ: ' + ', '.join(mismatches + obsolete))
            return 1
        print(f'checked {len(data)} assets / {len(expected)} exported files')
        return 0
    DEST.mkdir(parents=True, exist_ok=True)
    for name, content in expected.items():
        (DEST / name).write_text(content)
    print(f'generated {len(data)} assets / {len(expected)} exported files')
    if obsolete:
        print('preserved obsolete user files for review: ' + ', '.join(obsolete))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
