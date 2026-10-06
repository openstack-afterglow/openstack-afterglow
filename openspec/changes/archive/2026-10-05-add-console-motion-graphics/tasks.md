## Implementation

- [x] Motion token·keyframe·utility class와 reduced-motion 계약을 `layout.css`·`tokens.ts`·`DESIGN.md`·design-system test에 정의한다.
- [x] `ProgressTrack`·`StepProgress`·`ProvisionPipeline`·`ActivityIndicator`·`AnimatedNumber` primitive와 motion helper를 구현하고 동작 테스트를 추가한다.
- [x] VM 생성 wizard 단계 전환과 배포 진행, 같은 형식의 진행 표면에 적용한다.
- [x] Lumen 대기·추론·도구 실행·스트리밍·미디어 생성 대기에 적용한다.
- [x] 토폴로지 lane/canvas·네트워크 상세·미니 토폴로지에 적용한다.
- [x] Object Storage·이미지 업로드 dock, drop overlay, 다운로드 준비 상태에 적용한다.
- [x] Route 진입과 공통 UI primitive(skeleton, table, empty state, alert, modal, toast, tabs, 사용량·통계)에 적용한다.
- [x] 실제 Chromium에서 before/after, reduced-motion, 반응형, light/dark를 확인한다.
- [x] `DESIGN.md`·`ARCHITECTURE.md`·`CHANGELOG.md`를 갱신하고 change를 archive한다.

## Verification

- Svelte check: 2,174 files 0 errors/0 warnings. 전체 frontend unit 최종 실행: 306 files/2,101 tests 통과. 중간 실행에서 동시 세션이 작성 중이던 관리자 모델 가격 test 1건(`admin_models_cache_pricing.test.ts`)이 실패했으나 그 세션이 03:19에 수정한 뒤 통과했다.
- 실제 Chromium before/after: HEAD worktree(5181)와 현재 source 복사본(5182)을 같은 QA 전용 설정·tutorial mockup·throttled upload mock(8790)과 같은 scripted harness로 1440×900 dark에서 녹화했다. VM wizard 실제 흐름(이미지→플레이버→설정→배포→완료 후 닫힘), VM 배포 진행, Drover 생성 완료·실패, Lumen 대기·추론·도구·스트리밍, 업로드 dock 성공·실패, 공용 primitive gallery, 토폴로지 canvas/lane 첫 도착, 개요·버킷을 비교했다. 증거: `~/.gstack/projects/afterglow/designs/console-motion-audit-20261006/` (`console-motion-before-after.png`, 녹화 mp4, 비교 strip).
- Reduced-motion: 배포 진행 중 실행 중 animation 0, packet·ripple 숨김, 비결정 track은 전체 폭·낮은 불투명도, `진행 중` 문구 유지.
- 반응형: 390·767·768·1023·1024·1440px에서 배포·Drover·업로드·채팅 화면 가로 넘침 0, motion primitive 최소 글꼴 12px. Light theme의 Drover 실패·배포·skeleton 확인.
- QA 중 발견해 고친 결함: 업로드 dock의 44px 닫기 target이 행을 늘리던 배치, `SlidePanel` drawer 진입이 opacity만 남던 회귀, dark theme에서 skeleton sweep이 어두운 띠로 보이던 색(테마별 `--motion-skeleton-highlight` 추가), `UsageBar` scale 전환에 맞춘 landing meter test, 호출자가 사라진 `usageBar()`/`usageGrad()` 삭제.
- Architecture: 공유 review block(동시 세션의 hypervisor 검토)과 실제 index는 보존했다. HEAD+motion frontend 파일 496개의 격리 index(2,204 files, `source_sha256=f2aab4bba894d9acfcfacc85c6cbea24bbc39074fd0a1ac61ad6f5b7c197bc78`)에서 `check_architecture.py --staged` 통과. 동시 편집 중인 `ChatConfiguration.svelte`와 가격 test 2개는 HEAD 내용으로 두었다.
- 미실행: 전체 `npm run test:gate`(working `docs:check`는 공유 review block을 덮어써야 해서 실행하지 않았고 backend/contract/functional은 이 frontend 전용 변경과 무관), 실제 OpenStack 배포·Lumen provider streaming·RGW 전송·운영 배포·commit.
