## Context

이전 변경(`openspec/changes/archive/2026-10-01-consumer-landing-motion`)은 hero의 `LandingOpsBoard`, `#overview`의 `LandingJourney`, 제품 화면 미리보기를 만들었다. 실제 Chromium 녹화 결과는 `~/.gstack/projects/afterglow/designs/landing-motion-audit-20261002/before/`에 있다(`hero-run.mp4`, `hero-run-sheet.png`, `board-scenarios.png`, `journey-scroll.mp4`, `journey-scroll-sheet.png`, `product-views.png`, `capabilities.png`, `mobile-pair.png`). 확인된 문제는 다음과 같다.

| # | 위치 | 문제 |
| --- | --- | --- |
| F1 | 미리보기 | 단계 이름과 그림 변화가 맞지 않는다(정책 확인 단계에 네트워크 점선이 진해진다). 동작은 opacity 0.25 → 1 전환뿐이다. |
| F2 | 미리보기 · 클러스터 | 서버 더미 세 개가 서로, 그리고 양옆 블록과 겹친다. |
| F3 | 미리보기 · 공유 데이터 | GPU 서버 그림을 그대로 쓰고 칩 모양만 바꿨다. |
| F4 | 미리보기 | 대기 상태가 흐린 wireframe이라 깨진 화면처럼 보인다. 그림 라벨은 실제 객체와 떨어진 하단 grid에 있다. |
| F5 | 미리보기 | 단계 목록의 `✓` 글자가 `√`로 렌더링된다. |
| F6 | 스토리 | 서로 무관한 그림 네 장을 crossfade로 바꾼다. 객체가 이어지지 않고 연결선에 방향이 없다. scrub의 y·scale drift는 의미 없이 떠다닌다. |
| F7 | 스토리 · 재사용 | "새 환경 A" 위에 마름모가 떠 있고, 잠금 표시와 레이어 뜻이 모호하다. |
| F8 | 제품 화면 | `fit="cover"`로 아이콘을 잘라 확대해, 콘솔 화면이 아닌 큰 도형이 보인다. |
| F9 | 기능·워크플로우 그림 | SVG `font-family="serif"`/`"monospace"`가 대체 글꼴로 그려지고, "권한과 감사 로그"가 방패 외곽선과 겹친다. |

제약: DESIGN.md Motion(opacity·translate·scale만 animate, 반복 animation은 loading·progress·status만, 새 duration·easing 금지), Accessibility(색·애니메이션만으로 상태 전달 금지, 라벨 대비 AA, 200% 확대), 글자 최소 `0.75rem`(rem 단위). SVG 안의 글자는 viewBox 축소에 따라 모바일에서 12px 아래로 내려가므로, 장면의 글자는 HTML로 그리고 SVG는 아이콘·선 같은 장식에만 쓴다.

## Goals / Non-Goals

**Goals**
- 각 단계가 해당 기능의 실제 동작 하나를 보여준다. 예: 쿼터 막대가 요청량만큼 차고, VM 상태가 생성 중에서 실행 중으로 바뀌고, Pod가 노드에 배치되고, 레이어가 저장된다.
- 객체 연속성을 지킨다. 같은 객체가 단계를 넘어 유지되고 상태만 바뀐다.
- 시각 언어를 하나로 맞춘다. 미리보기, 스토리, 제품 화면이 같은 panel·status·connector 규칙을 쓴다.
- `gsap` 의존성을 제거한다. 스크롤 위치에 맞춘 이동·확대 효과를 없애고, 단계가 바뀔 때 token duration으로 전환한다.

**Non-Goals**
- 문구(hero, 단계 article 본문, section head) 재작성, 기능 카드·워크플로우 배치 변경, backend/API/site config 변경.

## Decisions

### D1. 공통 시각 어휘

세 컴포넌트가 아래 규칙을 각자 scoped CSS로 구현한다. class 이름은 맞추지 않아도 되지만 값은 정확히 따른다.

- **Scene window**: `border: 1px solid var(--color-line-2)`, `border-radius: var(--radius-lg)`, `background: var(--color-surface-canvas)`, `overflow: hidden`, `container-type: inline-size`.
  - Bar: `padding: 0.5rem 0.75rem`, `border-bottom: 1px solid var(--color-line)`. 왼쪽 route는 `font-family: var(--font-mono)`, 0.75rem, `--color-ink-2`. 오른쪽 "예시 화면"은 sans, 0.75rem, `--color-ink-2`. Bar 전체는 `aria-hidden`.
- **Panel**: `border: 1px solid var(--color-line)`, `border-radius: var(--radius-md)`, `background: var(--color-surface-raised)`, `padding: 0.75rem`, `min-width: 0`. 상태는 `data-state`로 표시한다.
  - `waiting`: `border-style: dashed`, `border-color: var(--color-line-2)`, `background: var(--color-surface-base)`, 본문에 0.75rem `--color-ink-2` 대기 문구.
  - `active`: `border-color: var(--color-accent)`, `box-shadow: 0 0 0 3px var(--accent-soft)`.
  - `done`·`ready`: 기본 border.
  - **opacity로 대기·미완료를 표현하지 않는다.**
- **Typography**:
  - Panel 제목: 0.8125rem/600, `--color-ink-0`.
  - Row label: 0.75rem, `--color-ink-2`.
  - Row value: 0.75rem/600, `--color-ink-0`, `font-variant-numeric: tabular-nums`.
  - 식별자(VM·레이어·네트워크 이름): `var(--font-mono)` 0.75rem, `--color-ink-1`.
  - 작은 글자 색은 `--color-ink-0/1/2`, `--color-warm-text`, `--color-state-success-text`만 쓴다. `--color-accent`, raw `--color-warm`, raw `--color-state-*`는 border·fill·icon·dot 같은 장식에만 쓴다.
- **Status**: dot(0.375rem 원)과 글자(0.75rem/500)를 함께 쓴다.

  | 상태 | dot | 글자 색 | 비고 |
  | --- | --- | --- | --- |
  | waiting | `--color-line-2` | `--color-ink-2` | |
  | working | `--color-accent` | `--color-ink-1` | dot에 `--motion-duration-status-pulse` + `--motion-ease-in-out` opacity pulse. 일시정지 시 `animation-play-state: paused`. working 상태일 때만 반복한다. |
  | done | `--color-state-success` | `--color-state-success-text` | |

- **Check icon**: inline SVG 0.875rem, `stroke: var(--color-state-success)`, stroke-width 2, `aria-hidden`. 글자 `✓`는 쓰지 않는다.
- **Connector**: 2px 선. idle은 `--color-line-2`, 연결 후는 `--color-accent`. 끝에 작은 삼각형 화살촉(`clip-path`)을 둔다.
  - 등장: `transform: scaleX(0)→1`(가로, origin start) 또는 `scaleY`(세로), `var(--motion-duration-data) var(--motion-ease-out)`.
  - 점선 흐름 같은 무한 반복은 쓰지 않는다.
  - Connector는 grid/flex의 고정 gap(가로 1.5rem, 세로 1rem) 안에 그린다. 레이아웃이 바뀌어도 어긋나지 않게 하려면 절대 좌표 SVG 선을 쓰지 않는다.
- **Enter**: `opacity 0→1` + `translateY(0.5rem)→0`, `var(--motion-duration-panel) var(--motion-ease-out)`. 순차 등장은 `transition-delay: calc(var(--motion-duration-base) * var(--i))`(i ≤ 4).
- **Quota**: `$lib/components/ui/UsageBar.svelte`(`size="sm"`, `label`, `value`, `max`, `unit`)를 그대로 쓴다. 요청 반영은 `value`를 `used`에서 `used + request`로 바꾸는 것으로 표현한다(primitive의 width transition).
- **Icon**: 각 컴포넌트에 1rem stroke icon(1.5px, `currentColor`, `aria-hidden`)을 inline으로 둔다. 종류는 server, gpu chip, network, database/share, layer, lock, user, k8s node, check.
- 장면 안에 gradient, glow, blob, 중앙 정렬 남용, 이모지를 쓰지 않는다.

### D2. 환경 구성 미리보기 (`LandingOpsBoard.svelte`)

**구조**

1. Header: 기존 kicker, 제목, disclaimer.
2. 시나리오 `ToggleGroup`(기존).
3. 요청 요약: 예시 요청 시각·프로젝트, h3 요청명, 단일 실행 `Button`.
   - 상태별 variant: idle·paused·complete는 `accent`, running은 `secondary`.
   - 문구: `환경 구성 체험` / `일시정지` / `계속하기` / `다시 체험`.
4. Scene window. route는 아래 시나리오 표를 따른다. body는 panel 4개다.
   - container ≥ 26rem: `grid-template-columns: repeat(2, minmax(0, 1fr))`, gap 0.5rem.
   - 그보다 좁으면 1열.
5. Progress: 상태 문장(`role="status"`, `aria-live="polite"`), `n / 4 완료`, `<progress>`, 단계 목록. 완료 단계는 SVG check, 진행 단계는 `aria-current="step"`.
6. 기존 `.configuration`(정책/자원 `dl`)과 `.output` section은 삭제한다. 정책·자원·결과는 panel 2–4가 모든 화면 폭에서 항상 보이게 유지한다.

**Panel**: request, policy, resource, reuse. 각 panel은 `<section aria-labelledby>`와 h4 제목을 갖고, row는 `dl`이다.

| 모드 | request | policy | resource | reuse |
| --- | --- | --- | --- | --- |
| idle | `ready` "작성됨" | `waiting` "확인 전" | `waiting` "생성 전" | `waiting` "결과 대기" |
| running·paused, 단계 k | k보다 앞이면 `done`, k이면 `active`, k보다 뒤면 `waiting` | ← | ← | ← |
| complete | 모두 `done` | ← | ← | ← |

panel별 working(active)/done 문구는 아래 시나리오 표를 따른다.

**단계 안의 동작**
- request active: 3개 row의 check가 순차 등장한다.
- policy active: UsageBar `value`가 `used + request`로 바뀌고, check row가 순차 등장한다.
- resource active: 시나리오 객체가 순차 등장하고 connector가 그려진다. status는 working이다.
- reuse active: 결과 chip이 resource panel 방향에서 `translateX(-0.5rem)→0`으로 들어온다.
- complete와 reduced-motion: 모든 객체가 최종 상태다.

**시간**: `const STEP_MS = MOTION_DURATION_MS.statusPulse + MOTION_DURATION_MS.data`(1900ms). 단계 4개.

**유지할 계약**: explicit start, generation fencing, IntersectionObserver로 화면 밖 정지(실행 중일 때만 관찰), `document.hidden` 정지, reduced-motion 즉시 완료와 동적 변경, 시나리오 변경 시 취소·idle 복귀, 정지 상태 재개, unmount 정리, replay 시 장면 remount.
- `toggleRun`은 `event.detail` 가드 없이 순수 toggle이다. double activation은 실행 후 정지로 끝난다.

**시나리오 데이터**(모두 "예시")

| | GPU 연구 | 클러스터 실습 | 공유 데이터 |
| --- | --- | --- | --- |
| route | `afterglow / compute / instances / new` | `afterglow / containers / clusters / new` | `afterglow / file-storage / shares / new` |
| request rows | 이미지 `PyTorch 2.4 · CUDA 12`; 사양 `GPU 1 · vCPU 16 · 64 GB`; 네트워크 `lab-vision-net` | 템플릿 `Kubernetes 1.30`; 워커 `3 × vCPU 8 · 32 GB`; 실습팀 `24명 · 14일` | 공유 공간 `2 TB · NFS`; 구성원 `lab-genomics 7명`; 접근 `연구원 읽기·쓰기` |
| policy rows | meter GPU 0+1/2; meter vCPU 8+16/64; check 정책 `GPU 사용 승인` | meter 인스턴스 1+4/8; meter vCPU 8+24/64; check 기간 `14일 실습` | meter 스토리지 3+2/10 (`unit=" TB"`); check 접근 `규칙 3개 승인`; check 보존 `30일` |
| policy 문구 | 확인 중 → 범위 내 | 확인 중 → 범위 내 | 확인 중 → 승인 |
| resource | instance row: server icon, `vision-train-01`, `GPU 1 · vCPU 16 · 64 GB`, 연결 chip `lab-vision-net`(네트워크)·`dataset-shared`(공유 데이터 · 읽기). connector는 instance에서 chip으로 | `course-dl-k8s`; node `control-plane`(제어)와 `worker-1..3`이 가로 grid. worker마다 Pod 사각형 4개가 순차 등장, 하단 `Pod 12` | share row `genomics-share`(`2 TB · NFS`); mount row 3개 `vm-seq-01`, `vm-seq-02`, `notebook-07`이 share에서 내려오는 connector와 함께 등장 |
| resource 문구 | 생성 중 → 실행 중 | 노드 준비 중 → Ready 3/3 | 연결 중 → 연결됨 3 |
| reuse | lock+layer icon, `pytorch-vision-lab`, "불변 레이어", "다음 VM이 이 레이어에서 시작합니다" | `distributed-training`, "클러스터 템플릿", "다음 수업을 같은 구성으로 시작합니다" | `genomics-baseline`, "스냅샷 · 매일 02:00", "새 분석은 이 시점에서 시작합니다" |
| reuse 문구 | 저장 중 → 저장됨 | 저장 중 → 템플릿 저장됨 | 생성 중 → 스냅샷 생성됨 |

### D3. 연속 수명주기 장면 (`LandingJourney.svelte`)

**유지**: step article 4개와 문구, 단계 선택 `Button` 4개(`aria-pressed`, 44px), caption(단계 이름 / artifact, caption 문장), 설명용 예시 note, `selectionHeld` 규칙, `scrollToStage`의 reduced-motion 분기.

**제거**: `gsap`와 `gsap/ScrollTrigger` import, scrub tween, `[data-drift]`.

**활성화**
- `roomy = matchMedia('(min-width: 1024px) and (min-height: 700px)')`와 `!reduced`일 때만 `motion-enabled`(sticky 2열)이다.
- 이때 passive `scroll`·`resize` listener와 `requestAnimationFrame` 1회 throttle로 기존 `activateFromGeometry`를 호출한다.
- media 변경 시 재구성하고, unmount 시 listener와 rAF를 정리한다.
- compact·reduced에서는 버튼으로만 바뀐다.

**장면**: `figure` 안의 scene window(D1)이며 body는 `aria-hidden="true"`다. caption이 현재 단계를 말한다. body는 dashed `--color-line-2` 프로젝트 경계와 `PROJECT · lab-vision` 라벨(mono, `--color-ink-2`)을 갖는다.

- **Wide**(container ≥ 32rem)
  - `grid-template-columns: minmax(0, 0.9fr) minmax(0, 1.25fr) minmax(0, 0.9fr)`, column-gap 1.5rem.
  - areas `"members core links" "detail detail detail"`.
  - connector: members → core 1개, core → link node 2개(가로).
- **Narrow**: 1열(members, core, links, detail), row-gap 1rem, 세로 connector. members와 links는 줄바꿈되는 chip row로 바뀐다.

**지속 객체**
- members: avatar 이니셜과 역할 3개. `교수자 · 관리`, `연구원 · 사용`, `학생 · 조회`.
- core card: 한 프레임 안에서 내용 4종을 같은 grid cell에 겹쳐 두고, 높이를 고정해 crossfade한다.
  - 신청: `환경 요청`. rows 이미지 `PyTorch 2.4`, 크기 `GPU 1 · vCPU 16`, 네트워크 `lab-net`, 데이터 `공유 읽기`. status done "제출됨".
  - 배정: `vision-train-01` · VM. rows 이미지·크기. status done "실행 중".
  - 관측: 배정과 같고 row `GPU 71% · 메모리 48%`가 추가된다.
  - 재사용: status done "레이어 저장됨", row `v1 · 불변`.
- links: `lab-net`(네트워크), `shared-dataset`(공유 데이터 · 읽기).
  - 신청: dashed waiting "연결 전".
  - 배정 이후: solid. connector가 그려지고 유지된다.

**Detail 영역**: 4개를 같은 grid cell에 겹쳐 두고, 높이는 최대값으로 고정한다. 비활성은 `opacity: 0; visibility: hidden`이고 순차 등장은 D1을 따른다.
- 신청: "요청에 담는 항목". check chip 4개 `이미지`, `컴퓨팅 크기`, `네트워크`, `데이터 접근`.
- 배정: "쿼터·정책 확인 후 생성". UsageBar GPU 1/2, vCPU 24/64, 메모리 96/256(`unit=" GB"`). note "확인은 생성 성공이나 용량 예약을 뜻하지 않습니다".
- 관측: 두 열.
  - "사용 지표 · 예시": SVG polyline sparkline. 위에 덮인 panel이 `scaleX 1→0`(origin right)으로 걷히며 드러난다.
  - "활동 기록 · 예시": 3행이 순차 등장. `09:41 연구원 · VM 생성 요청`, `09:42 시스템 · 네트워크 연결`, `10:05 교수자 · 쿼터 조정`.
- 재사용: `불변 레이어 v1`(lock)에서 분기 connector 2개가 `새 환경 A`, `새 환경 B`로 이어진다. 각 환경에 `+ 변경 분리` chip이 있다.

**Sticky rail 크기**: 1024×700과 1440×900에서 scene frame(버튼, 장면, caption, note)이 viewport 안에 잘림 없이 들어가야 한다.

### D4. 제품 화면 (`LandingConsolePreview.svelte` 신규, `LandingPage.svelte`에서 사용)

- `view: 'project' | 'cluster' | 'network'`. `LandingPage`의 stage bar(route, 예시 화면)와 `{#key}` remount는 유지하고, `LandingFigure` plate만 바꾼다. 화면 높이는 view와 상관없이 같아야 한다(전환 시 레이아웃이 뛰지 않게).
- 공통: 좁은 왼쪽 rail(icon 5개, 현재 항목만 `--color-surface-selected`)과 main.
- **project**: `lab-vision · 프로젝트 개요`.
  - counter tile 3개: 인스턴스 4, 볼륨 6, 클러스터 1.
  - UsageBar 4개: vCPU 40/64, 메모리 160/256 GB, GPU 1/2, 스토리지 3.2/10 TB.
  - 최근 활동 3행: mono 시각과 문장.
- **cluster**: `course-dl-k8s`와 done status `Ready`.
  - node 4행: `control-plane` 제어 CPU 18% Pod 6, `worker-1` 62% 8, `worker-2` 55% 8, `worker-3` 48% 8.
  - CPU는 UsageBar `size="xs" showValue={false}`에 숫자를 별도 표시한다.
  - 하단 `Pod 30 · 네임스페이스 24`.
- **network**: `외부망 → router-lab → lab-net → vm-a / vm-b / vm-c` 토폴로지. D1 connector와 node card, 범례 3개(외부, 라우터, 내부)를 쓴다.
- 전환 시 row·node가 D1 enter로 1회 순차 등장한다. 반복 animation은 없다.
- `PlateGraphic.svelte`: `.plate-graphic :global(text) { font-family: var(--font-sans); }`, `.plate-graphic :global(text[font-family='monospace']) { font-family: var(--font-mono); }`. 글꼴을 바꾼 뒤 `security` plate의 라벨이 방패와 겹치면 해당 text의 y만 조정한다.

### D5. 테스트

- **`LandingOpsBoard.test.ts`**
  - 시작·정지·재개·재실행, 화면 밖과 hidden, reduced, 시나리오 전환, unmount 계약을 유지한다.
  - double activation 테스트를 toggle 계약으로 바꾼다: 두 번 활성화하면 정지되고, `vi.getTimerCount()`가 0이며, 오래된 observer 콜백은 효과가 없다. 그다음 한 번 재개하면 진행이 2를 거쳐 4가 된다.
  - 단계별 panel `data-state` 전이(active는 정확히 하나)를 추가한다.
  - 클러스터 완료 시 resource와 reuse가 시나리오별 객체를 보여주는지 확인한다. 노드 수와 결과 이름 등, 문구가 아닌 구조 기준으로 본다.
- **`LandingJourney.test.ts`(신규)**
  - 버튼을 누르면 `aria-pressed`, caption, `article[data-active]`, root `data-stage`가 바뀐다.
  - roomy이면서 reduced가 아니면 scroll geometry로 단계가 바뀌고, 사용자가 선택한 단계는 wheel이 오기 전까지 유지된다.
  - compact·reduced에서는 scroll로 바뀌지 않는다.
- **`LandingPage.test.ts`** 행동 복원(문구 비의존)
  - 건너뛰기 링크가 `#landing-content`로 포커스를 옮긴다.
  - 모든 콘솔 이동(nav, hero, product-console, contact)의 href가 `consoleHref`와 같다(`/login`, `/dashboard`).
  - hero 보조 버튼 → `#capabilities`, scroll cue → `#overview`.
  - brand는 `/`로 가고 runtime `logoPath`·`siteName`을 쓴다(footer brand 포함).
  - footer mailto와 GitHub 링크가 있다. raster `<img>`가 없다.
  - 기능 카드 link가 해당 workflow 필터를 선택한다.
  - 제품 view 전환 시 화면 `data-view`·route·설명이 바뀐다.
- **`typographyRoles.test.ts`**: landing AA 음성 가드를 복원한다.
  - 네 파일(`LandingPage`, `LandingOpsBoard`, `LandingJourney`, `LandingConsolePreview`) 모두: `color: var(--color-ink-3);`와 raw `color: var(--color-state-success);`를 금지한다.
  - 새로 만드는 세 컴포넌트: raw `color: var(--color-warm);`와 `color: var(--color-accent);` 텍스트 색도 금지한다.
  - `LandingPage`의 기존 accent 라벨은 이 변경 범위가 아니므로 pin하지 않는다.
  - 문구 고정이나 사라진 xl 레이아웃 pin은 넣지 않는다.
- `designSystemRules.test.ts`의 `method matrix` 문구 assertion 한 줄만 새 DESIGN.md 문구에 맞춘다(다른 세션 변경 보존).

## Risks / Trade-offs

- **세 컴포넌트가 같은 규칙을 각자 scoped CSS로 구현**: 값이 어긋날 수 있다. 공통 primitive를 새로 만들면 공개 페이지 전용 추상화가 늘어나므로, D1 값을 계약으로 두고 통합 시 시각 비교로 확인한다.
- **scrub 제거**: 스크롤 거리와 장면 진행이 1:1로 대응하지 않는다. 대신 각 단계의 장면이 항상 완결된 상태로 보이고(중간 상태 없음), GSAP Standard license 의존성이 사라진다.
- **UsageBar width transition은 primitive가 정한 160ms다**: 쿼터 막대가 빠르게 찬다. 순차 check와 working status로 단계 시간을 채운다.
- **모바일에서 미리보기가 길어진다**(panel 4개가 세로로 쌓임): 정책·자원·결과를 모든 tier에서 유지하는 계약을 우선한다.
