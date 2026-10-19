## Implementation Tasks

- [x] 현재 언어 cookie·docs URL·SSR·클라이언트 내비게이션 경로를 추적하고 실제 브라우저에서 분리 현상을 확인한다.
- [x] docs URL 우선·공통 cookie fallback, 한국어 명시 선택, SSR cookie 기록과 preload 무변경을 구현한다.
- [x] 재사용 root layout과 docs loader·shell·404를 공통 언어로 갱신하고 기존 동작 회귀를 정리한다.
- [x] 관련 frontend 검사와 실제 브라우저로 네 언어의 메인·문서·로그인·인증 후 이동, 새로고침, JS 없는 문서 선택 및 preload를 검증한다.
- [x] 검증 증거와 공통 언어 계약을 기존 문서·changelog·architecture에 반영하고 architecture guard를 실행한 뒤 archive한다.

## Verification

- 현재 source 실제 Chromium 수정 전 재현 → 수정 후4locale loop, 합성 domain/password login·logout, preload/no-JS/error·기사 query/hash와24responsive/theme조건/48surfaces 통과. 실제 SSR24응답의 언어 일치·404 유지와 Korean Set-Cookie 확인.
- Node24.14.1 전체 frontend383files/3,910tests + Node9passed; focused6files/108passed. PTY Homebrew Node26의 experimental Web Storage/jsdom 충돌 실패는 원본 기록을 보존하고 기존 compatible runtime에서 전체 재검증했다.
- i18n45namespace/10,381message 0errors/0warnings, scan1,108files 0hard-coded Korean. Svelte check는 범위 밖 database instances PageState.instanceId1error와 기존3warnings가 남는다. 전체 test:gate·production build·실인증·운영 배포는 실행하지 않았다.
- 별도 frozen public-source dev/index의 architecture stamp·working·staged check: `a166d8c1b3693e1653e3fe4e11cc341349c5b0208958a916db9c4f522ca27e40`,2,945files. 동시 WIP도 포함한 digest이며 scope 밖 검토가 아니다. 공유 index·review marker·기존 서비스 보존, scratch browser/server/profile/snapshot 정리.
- 상세 근거: `docs/testing.md`의 공통 언어 쿠키 통일 검증. Durable receipt: `~/.local/share/afterglow-proofs/locale-cookie-20261016/`.
