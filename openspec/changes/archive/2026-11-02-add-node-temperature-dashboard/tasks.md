## Implementation Tasks

- [x] 관리자 catalog와 UID 설정, 예시 및 Kubernetes/Helm 경로를 동기화하고 API 회귀 검증.
- [x] 서버 온도 navigation, 번역, route 및 기존 embed의 시간대/refresh 옵션 구현.
- [x] 실제 compiled 화면과 Grafana를 검증하고 architecture/API 문서 및 changelog 갱신 후 archive.

## Verification Evidence

- API precedence8/catalog authorization5/embed6tests; config target backend611/frontend12tests 통과.
- Kubernetes/config2helm/Helm 실제 render default 및 override UID readback 통과.
- Isolated Vite/Chromium actual route + live Grafana 온도 그래프/°C 값 확인. Afterglow identity/catalog만 synthetic.
-9locale×2theme×3width54조건 page overflow0. Mobile drawer 선택/닫힘·command palette 검색/Enter 확인.
- Frontend check0errors/17warnings; i18n0errors/45warnings; scan0hard-coded Korean. 전체 test:gate/commit/push/deploy 미실행.
- 증거: `~/.local/share/afterglow-proofs/node-temperatures-20261102/` 및 `docs/testing.md` 서버 온도 절.
- Interaction static segment 등록 후 실제 canonical_page smoke에서 고정 온도 경로 보존·opaque child 식별자 :id 치환 확인. 새 timezone/refresh 옵션은 실제 브라우저54조건 URL assertion으로 검증했다.
