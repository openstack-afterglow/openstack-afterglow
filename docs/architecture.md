# Afterglow 아키텍처 상세

이 페이지의 정본은 저장소 루트 [`ARCHITECTURE.md`](https://github.com/openstack-afterglow/openstack-afterglow/blob/main/ARCHITECTURE.md)입니다. 루트 문서는 현재 `dev` checkout을 기준으로 Afterglow 대시보드·FastAPI gateway/BFF·OpenStack 경계, 인증과 세션, VM SSE/rollback, 형제 서비스 ownership, 배포와 보안 한계를 설명합니다.

이 문서는 문서 사이트에서 접근할 수 있는 상세 도메인 안내 페이지입니다. 현행 책임과 route mount가 여기의 과거 설명과 다르면 루트 문서와 source를 우선합니다.

## 상세 문서

- [API 레퍼런스](api-reference.md): `/api/v1` route와 legacy VM callback 계약
- [보안 모델](security.md): 인증·인가, owner check, 암호화와 알려진 제한
- [k3s/Drover 동작 명세](drover-workflow.md): 계획과 현재 SSE/callback 단계의 차이
- [Palimpsest](palimpsest.md) 및 [squashfs layer pipeline](squashfs-layer-pipeline.md): retained layer 도메인
- [배포](deployment.md): Compose, Kubernetes, ArgoCD, kolla-ansible 실행 전제조건

코드·설정·schema·dependency·배포·테스트를 변경할 때는 루트 architecture 본문과 이 상세 문서를 함께 검토합니다. 변경 후 source를 검토하고 저장소 root에서 다음 명령으로 stamp한 뒤 stage 범위를 확인합니다.

```bash
python3 scripts/check_architecture.py --stamp --summary "검토한 변경 경로와 구조 영향"
python3 scripts/check_architecture.py --staged
```

이 페이지는 루트 문서의 복사본이나 별도 snapshot이 아닙니다. historical Union 계획은 [Palimpsest 현행 경계](palimpsest.md)와 구분해 읽습니다.

## 채팅 컨텍스트 검사와 로컬 실행 경계

`ChatContextPanel`은 Lumen의 optional `ContextState.breakdown`을 표시하며 Afterglow가 토큰이나 모델 한도를 재추정하지 않는다. `preview`는 다음 요청의 준비 상태이고 `request`는 worker의 실제 요청 상태다. 각 component는 안전한 이름/ID, 개수, 토큰 수, 측정 방식과 포함 여부를 전달한다. 메시지·시스템/프로젝트 지침·메모리·스킬·에이전트·요약·도구·MCP·첨부·framing을 구분하되 본문/비밀은 표시하지 않는다.

- 포함된 항목의 전체 모델 한도 대비 비중과 응답 예약·안전 버퍼·남은 입력을 구분한다.
- `uncounted` 항목은 아직 계수되지 않은 요청 재료이며 실제 지연 로딩 항목과 다르다. 미계수 재료를 0으로 가정하거나 정확한 여유 공간으로 표시하지 않는다.
- 한도가 없는 모델도 안전한 구성 metadata는 볼 수 있다. 과거 journal에 breakdown이 없으면 임의 분해하지 않는다.
- 컨텍스트는 요청 크기이며 사용량 청구, 월/주간 credit quota와 별개다. 모델 한도는 Lumen의 정확한 catalog 항목 또는 양수 관리자 override가 소유한다.

설정 화면은 tablet/desktop에서 parent 높이를 나눠 쓰고 내용 영역만 스크롤한다. Mobile은 자연스러운 main scroll을 유지한다. 검사 패널은 기존 `SlidePanel`의 mobile modal, tablet/desktop bounded panel, Escape/focus 복원 계약을 사용한다.

Compose 배포는 세 독립 manifest로 나눈다. `docker-compose.yml`은 published frontend/backend만 실행하고 외부 DB/cache를 사용한다. `docker-compose.dev.yml`은 전체 current-source local stack이며 `services:config/up/smoke/down`은 [로컬 서비스 스택](deployment.md)의 `afterglow-local-services` project·기본 loopback 3080/8000·sibling API ports와 private 입력/volume을 보존한다. `docker-compose.prod.yml`은 source build 없이 GHCR 이미지를 pull하며 HAProxy TLS·DNS round-robin을 제공한다. 운영 앱 port는 private이고 sibling은 기본적으로 catalog로 연결하며, 별도 profiles로만 sibling API/worker/migration을 실행한다. 이 worker들은 Afterglow backend process에 내장되지 않는다. Smoke는 Lumen 관리자 billing 계약과 dashboard summary/quotas까지 검사하므로 상류 Nova 503을 container health 성공으로 숨기지 않는다. 모델 metadata/context-preview 성공과 실제 유료 provider completion은 서로 다른 증거다.

독립 서비스 endpoint는 `SERVICE_*_INTERNAL_URL`/`[services] *_internal_url`로 선택한다. BFF와 공유 OpenStack connection의 Drover/Waygate SDK에 함께 적용하고 core OpenStack routing·token/project scope는 유지한다. 기본·운영 Compose는 unset 변수를 주입하지 않아 TOML 또는 catalog를 유지하며 운영 명시 URL은 HTTPS를 요구한다. Dev runner는 shell/`.env`(빈 값은 catalog) → nonempty private snapshot → local DNS 순서로 선택하고 결과를 private `compose.env`에 보존한다. DB/cache isolation 및 실패 URL에서 catalog로 자동 fallback하지 않는 경계는 바뀌지 않는다.

Frontend `/health`는 session이 없는 probe에도 JSON liveness를 반환하고 Compose는 로그인 redirect를 정상으로 인정하지 않는다. Drover는 별도로 DB/Redis/migration과 명시적인 dedicated service project의 Keystone authorization readiness를 요구한다. 로컬 snapshot의 service project UUID는 기존 프로젝트를 지정하며 admin으로 fallback하지 않는다.

Dashboard Drover SDK 통계는 caller token의 원래 project를 보존해야 한다. 형제 API의 token introspection이 default-project 재인증을 대체하며 명시적 rescope와 admin/owner 검증은 유지된다. Local smoke는 통계의 HTTP 200뿐 아니라 `available: true`와 count 범위까지 확인한다.

Waygate와 Drover의 BFF discovery root는 canonical upstream `/v1/`로 전달한다. 내부 hostname의 307 redirect를 브라우저에 노출하지 않고 version JSON을 반환하며, 사용자 token/project 전달과 나머지 resource path는 그대로 유지한다.

Lumen의 async 인증 dependency는 동기 Keystone 검증을 Starlette의 제한된 threadpool에서 기다린다. 느린 인증 한 건이 API event loop 전체를 막지 않으며 token rescope, target project, admin 판정과 실패 응답은 바꾸지 않는다. 이는 인증 결과 cache나 장애 시 허용 경로가 아니다.
