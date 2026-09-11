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
