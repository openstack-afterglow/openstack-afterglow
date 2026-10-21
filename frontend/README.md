# Union Frontend

SvelteKit + TypeScript + Tailwind v4 기반의 Union 플랫폼 프론트엔드.

## 기술 스택

- **SvelteKit** (SPA + SSR)
- **TypeScript**
- **Tailwind CSS v4**
- **Bun** (패키지 매니저 / 빌드)

## 개발

```bash
npm install       # 의존성 설치 (bun install도 가능)
npm run dev       # 개발 서버 :3000
npm run build     # 프로덕션 빌드
npm run check     # svelte-check 타입 검사
npm test          # vitest 1회 실행
npm run test:watch  # vitest watch 모드
```

## 의존성 보안 floor

`package.json`의 dependency/override 선언과 두 lockfile(`package-lock.json`, `bun.lock`)을 함께 유지한다. npm lock의 root와 `packages[""]` version은 manifest와 같아야 한다. Bun lock에는 root version 필드가 없고 두 package manager의 중첩 graph는 다를 수 있지만, 대상 package의 모든 사본은 patched floor를 충족해야 한다.

Frontend runtime 이미지는 builder의 `package.json`과 기존 `package-lock.json`을 함께 복사하고 `npm ci --omit=dev --ignore-scripts`로 설치한다. Lock 없는 runtime 재해석을 하지 않으며 Bun build는 기존 frozen `bun.lock`을 그대로 사용한다.

| Package | Floor | 경로 |
| --- | --- | --- |
| `dompurify` | `^3.4.16` | 직접 의존성 + `overrides` (Mermaid의 중첩 사본까지 같은 patched 버전으로 고정) |
| `smol-toml` | `^1.7.1` | 직접 의존성 (`src/lib/server/config.ts` SSR TOML 설정) |
| `devalue` | `^5.9.3` | `overrides` (SvelteKit/Svelte transitive, 직접 의존성 추가 금지) |
| `vitest`, `@vitest/coverage-v8` | `^4.1.11` | devDependencies; `@vitest/*` family는 같은 정확한 버전으로 함께 갱신 |

기존 `cookie`/`esbuild`/`postcss`/`vite` override는 유지한다. 먼저 `package.json`의 대상 dependency/override floor를 함께 수정한 뒤 lifecycle script 없이 두 lockfile을 재생성하고, diff에서 대상 package와 필수 transitive 변경만 남았는지 확인한다. Overridden 직접 package에 `npm install <pkg>@<floor>`를 사용하면 `EOVERRIDE`가 날 수 있다. 광역 `update`·`--latest`로 Svelte/Kit/Vite나 무관한 graph를 갱신하지 않는다.

```bash
npm install --package-lock-only --ignore-scripts --no-audit --no-fund
bun install --lockfile-only --ignore-scripts
bun install --frozen-lockfile --lockfile-only --ignore-scripts   # Bun lock 동기화 확인
npm ls --package-lock-only dompurify smol-toml devalue vitest @vitest/coverage-v8
bun install --frozen-lockfile --ignore-scripts                  # Bun 설치 graph 확인
bun pm ls --all                                                # 중첩 사본의 floor 확인
```

## 디렉토리 구조

```
src/
├── routes/
│   ├── +layout.svelte           # 인증 체크, 사이드바
│   ├── dashboard/               # 대시보드 (인스턴스, 볼륨, 네트워크, 파일스토리지, k3s, 컨테이너)
│   ├── admin/                   # 관리자 페이지
│   ├── create/                  # VM 생성 마법사
│   └── auth/gitlab/callback/    # GitLab OIDC 콜백
└── lib/
    ├── api/client.ts            # API 클라이언트 (base URL, 헤더, 30초 타임아웃)
    ├── stores/auth.ts           # 인증 상태 (token, projectId, isSystemAdmin)
    ├── types/resources.ts       # 공통 TypeScript 타입
    ├── config/site.ts           # 사이트 설정 (서비스 활성화 플래그)
    └── components/              # 슬라이드 패널, 위저드, 차트 등 UI 컴포넌트
```

## Administrator service project scope

The workspace selector uses the server-authorized `/api/v1/auth/domains` and `/api/v1/auth/workspaces` directories, then `/api/v1/auth/token/workspace` for an atomic logical selection. A projectless system administrator must not be required to have a target membership or rescope native credentials into the target. The backend preserves the native authentication source; the browser sends the selected logical project as `X-Project-Id`.

Lumen, Drover, Waygate and Palimpsest controls consume the exact leaves from `/api/v1/projects/current/permissions`; cached administrator flags and role names never synthesize service grants. Loading, verification failures and project transitions disable actions. Native service policies remain authoritative. Administrative management does not impersonate a resource owner: Waygate profiles and Palimpsest package keys retain requester ownership checks and one-time-secret disclosure fences.

The administrator Drover list captures the resource's `project_id` with the selected cluster and supplies it to the existing detail controller and its auxiliary controls (health, workloads, nodegroups, networks, certificates, Stampede and shell tickets). Missing owner project metadata never falls back to the caller project. Routine kubeconfig downloads explicitly request the current `user` or `editor` grade on the project endpoint, including from administrator details. The stored `admin` certificate remains a separate explicitly confirmed action.

Source changes and regression definitions are not browser/native acceptance evidence. Run the focused permission, workspace-selector, Drover controller and auxiliary-control regressions, then verify the compiled controls against the integrated backend with a freshly verified zero-role administrator and a selected project without membership.

## Design system

Frontend visual changes must start from root `DESIGN.md`; reusable assets live in `src/lib/components/ui`; semantic token metadata lives in `src/lib/design`.

See [`../DESIGN.md`](../DESIGN.md).

### Tablet and mobile resource cards

Wrap application-authored table and div-grid data views in `ResponsiveTable`. Its shared viewport MediaQuery mounts only `cards` below1024px and only the desktop `children` snippet at1024px and above; a narrow desktop modal is still a table. Keep selection, pending writes, drafts, sort/filter/page state in the owning component/controller, outside the responsive branch. Breakpoint changes never fetch or mutate.

Author the compact branch with `CompactResourceCard`: name/status, two or three key facts, visible wrapping actions, secondary UUID/time/specification fields in `details` or the existing detail view. Use `.responsive-card-toolbar` for select-all/sort controls above the card grid. The default layout auto-fits18rem cards inside the available width with0.5rem gaps and0.75rem padding, without fixed heights. Preserve all action/permission/unknown-state boundaries and ensure inline editors do not lose drafts on viewport transitions. User/external Markdown and graph canvases are not data-table conversions.


### Dashboard charts: Bklit UI

All Afterglow-owned numerical visualizations use the actual [Bklit UI](https://github.com/bklit/bklit-ui) React registry components. SvelteKit remains the application framework. `src/lib/components/charts/BklitChart.svelte` owns the client-only lazy import, one React root per mounted plot, reactive data/locale updates, reduced-motion subscription, and teardown. Do not import React/vendor components from Svelte routes or create a second SVG/CSS chart implementation.

| Surface | Shared composition / native Bklit renderer |
| --- | --- |
| Quotas, resource capacity, hypervisor/project usage, context inspector | `UsageBar`, `QuotaBar`, `CapacityBar`, `HypervisorUsageBar`, `ProjectQuotaPanel` → continuous linear `Gauge` |
| Composer context, dashboard/resource overview rings | `UsageRing`, `Donut`, `QuotaDonut` → `RingChart` + `Ring` |
| Dashboard/usage/report mini graphs and host telemetry | `Spark`, `StatTile` → native line/area or gauge |
| Resource/admin time history, library/layer history | `TimeSeriesChart`, `LibraryUsageChart` → native time series with stable series IDs |
| VM CPU/memory/network/disk/GPU charts | `MetricsPanel` → native line/area with independent sample timestamps |
| Admin native host/storage measurements | `MonitoringSummaryTab` → per-meter native time series, retaining reported units and real timestamps |
| Network lanes/detail, Waygate peer rates, infrastructure NIC history | `TrafficSparkline`, `TrafficArea`, `NetworkLane` → native time series |
| Activity/hourly login distributions, user/admin chat statistics | `LoginCharts`, activity route, `ChatUsagePanel`, admin stats route → native bars/stacks |
| Model/token shares, chat quota, storage-pool usage, file-storage capacity, flavor capacity preview | Native gauge or horizontal stacked bar; existing thresholds/units preserved |
| Admin traffic trends and country map | `TrafficTrend` → `Spark`; `TrafficCountryMap` → native `ChoroplethChart`/`ChoroplethFeature`/`ChoroplethTooltip` |

Editable network topology, role/dependency graphs, external Grafana embeds and their queries remain specialized. Their embedded numerical plots use Bklit. Task progress, status indicators, icons, QR codes, terminal output, public illustrations and user-authored Mermaid are not statistical charts. Country flow/site annotations remain a small domain overlay using Bklit's projection; they never replace the native geographic renderer or imply physical network routes.

**Adding a visualization**

1. Reuse a domain component above; otherwise pass a typed `ChartSpec` from `charts/types.ts` to `BklitChart`. The discriminants are `time-series`, `bar`, `ring`, `gauge`, and `choropleth`. Required `height` reserves layout before the client runtime loads; `width` is only for fixed-size compact plots.
2. Time-series X values are epoch **milliseconds**. Convert seconds at the consumer boundary. Keep null/nonfinite/unobserved values unavailable, measured zero as zero, source timestamps independent via `ChartSeries.data`, exact percentage domains explicit, and byte/unit/timezone semantics unchanged. `data` supplies the union of timestamps for axes, tooltips and the accessible table. Do not manufacture aligned samples or interpolate missing buckets.
3. Use existing chart/tone/surface CSS variables and current `intlLocale()` formatters. Full plots expose native tooltips plus a keyboard-accessible source-data disclosure. Compact/decorative plots require adjacent readable labels/values; meter wrappers own `role="meter"` and unlimited/over-limit semantics. Numeric labels fit the actual panel width; complete category text remains available in tooltip/table.
4. Keep fetch, authorization, project/request-generation fences, loading/error/empty states, refresh and filters in the existing Svelte controller. The chart receives data, never credentials or a fetch callback. `showData={false}` requires an equivalent existing table; decorative plots must not introduce duplicate accessible graphics.
5. Qualify actual compiled Chromium at mobile/tablet/desktop widths, all supported locales and both themes. Check refresh, null gaps, zero/unlimited/over-limit, independent sample spacing, 18px rings/5px meters, tooltips, data-table keyboard access, geographic selection, unmount/remount and live reduced-motion changes. jsdom's zero-layout ResizeObserver shim is not visual evidence.

For categorical timestamps, retain canonical bucket IDs in `data` and use `formatCategory(value, 'axis' | 'detail')` to abbreviate the axis only. Never use abbreviated dates as scale keys: distinct hours/days must remain separate bars. Qualification checks pairwise label collisions as well as plot/document overflow.

`/admin/monitoring` keeps Nova allocation and provisioned storage inventory independent of optional Gnocchi telemetry. The native section reports caller-policy coverage, provider availability and truncation, shows the latest observation with its reported unit, and lazily opens recorded Bklit history (including null gaps and true zeros). Display work is bounded to 12 resources and 12 meters per resource; the visible limit notice must not imply cloud-wide totals. Allocation bars are not measured host RAM or guest usage. Summary and instance inventory responses are fenced by auth/session/project generations; instance selection recreates `MetricsPanel` for its verified owning project, and unknown ownership does not issue a private metrics request.
**Upstream maintenance**

`src/lib/vendor/bklit-ui/provenance.json` pins commit `f7b3bd2999a5c993863f9cc5523c9cf60b9f3bc2`, official immutable registry URLs, original hashes, import rewrites and local extensions. Keep its MIT `LICENSE`. This is source-distributed Bklit, not an unofficial Svelte imitation or a runtime CDN. Fetch the required registry roots and transitive registry dependencies at a reviewed commit, reapply only the documented extensions (exact domains, null gaps, independent sampling, compact geometry, localized axes, reduced motion, stable geographic focus), and retain original hashes alongside the patch ledger. Do not run `shadcn init`, replace the app theme/reset, or copy a complete Next.js demo.

React/ReactDOM, Motion and exact Visx 4 dependencies are declared in `package.json`; keep npm and Bun locks synchronized using the existing dependency procedure. LayerChart POCs and the unused direct `layerchart`/`d3-scale` dependencies are removed. `svelte.config.js` includes `.tsx` in generated TypeScript checking, and `tsconfig.json` enables React JSX. Run `npm run check`, native/consumer regressions, the full frontend suite, i18n checks and `npm run build`; report pre-existing failures separately. Current qualification evidence is in [`../docs/testing.md`](../docs/testing.md).

## 환경 설정

백엔드 API는 `/api` 경로로 프록시됩니다.

- 개발: `vite.config.ts`의 프록시 설정으로 `http://localhost:8000` 연결
- 프로덕션: HAProxy / Nginx 리버스 프록시

모든 API 요청은 `X-Auth-Token`과 `X-Project-Id` 헤더를 포함합니다.
