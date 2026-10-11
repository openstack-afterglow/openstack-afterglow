## Implementation Tasks

- [x] Lumen 상단의 이미지 Studio 버튼을 제거한다.
- [x] Lumen 상단의 오디오 Studio 버튼을 제거한다.
- [x] Lumen 상단의 실시간 음성 버튼을 제거한다.
- [x] 세 버튼 전용 번역 키를 네 locale에서 삭제하고 i18n check·scan으로 확인한다.
- [x] 실제 Chromium에서 네 locale·light/dark·반응형 폭의 버튼 부재, 기존 채팅 컨트롤과 Studio 탐색 유지를 검증한다.
- [x] 상세 문서·changelog·architecture scoped review를 갱신하고 이 change를 archive한다.

## Verification

- Actual current-source Vite frontend in an isolated directory; the changed ChatPanel and four locale catalogs match working-tree bytes. Existing Compose services, private configuration and operational databases were not touched.
- Chromium: ko/en/ja/zh-CN × light/dark × 390/767/768/1023/1024/1440/1568px = 56 conditions. Full chat/image/audio/tools permissions are explicitly granted by synthetic fixtures, so absence is not permission hiding. Removed header actions0, document horizontal overflow0, visible header controls within viewport in every condition.
- Retained controls exercised: model picker and selection, agent picker, sources open/close, temporary chat on/off, mobile history open/Escape and global drawer Studio destinations. Both Studio sidebar links navigate to their existing pages; the direct realtime page still renders. Media generation/provider inference was not executed.
- i18n check:0errors/0warnings,37namespaces/9,528source messages. i18n scan:0hard-coded Korean lines/991files. Svelte check:2,355files/0errors; existing `DocCodeBlock.svelte:26` accessibility warning1 remains unchanged. No new permanent implementation/wiring test was added; the actual changed UI was exercised instead.
- Browser JavaScript exceptions0. The external Google Fonts stylesheet was deliberately blocked by the QA network policy; that request failure is not classified as an application exception. Identity/API fixtures do not qualify live Keystone, provider or production behavior.
- Scoped architecture staged stamp/check passed: HEAD plus5current source files, source2,546files, digest `d6eb75663176f55138588685991f3bd53fd1941d8dafb3a717eedeec23bffb06`. Actual Git index and shared review marker preserved. Full test:gate, commit/push, images and production deployment not run.
- OpenSpec rapid artifact status and all6tasks are complete. The generic `openspec validate --strict` rejects this repository's no-specs rapid change for having no delta specs; no artificial spec layer was added. The prescribed `openspec archive --skip-specs --yes` succeeded as `2026-10-11-remove-lumen-header-studio-actions` with that non-blocking warning. Owned QA frontend/browser/profile and temporary index were stopped/removed; user workloads were preserved.
- Optional GBrain sync was unavailable (`command -v gbrain` returned no CLI). No engine setup or agent-context rewrite was attempted; repository/tool-based source discovery remains authoritative.
