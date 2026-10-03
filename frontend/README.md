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

## Design system

Frontend visual changes must start from root `DESIGN.md`; reusable assets live in `src/lib/components/ui`; semantic token metadata lives in `src/lib/design`.

See [`../DESIGN.md`](../DESIGN.md).

## 환경 설정

백엔드 API는 `/api` 경로로 프록시됩니다.

- 개발: `vite.config.ts`의 프록시 설정으로 `http://localhost:8000` 연결
- 프로덕션: HAProxy / Nginx 리버스 프록시

모든 API 요청은 `X-Auth-Token`과 `X-Project-Id` 헤더를 포함합니다.
