## Implementation Tasks

- [x] 현재 image 설정·Zun lifecycle·원본 baseline/CLI/runtime·GitHub org admin 권한을 확인하고 범위/보안 계약을 기록한다.
- [x] 원본의 Git 이력을 보존하고 Afterglow bootstrap/runtime 검증을 openstack-client로 이전한다.
- [x] GitHub Actions에 Debian/Alpine amd64/arm64 실제 build/smoke 후 GHCR 게시를 구성한다.
- [x] Afterglow 기본 image와 선택 가능한 pull policy / Zun registry ID를 backend·K8s·Helm·Kolla에 연결한다.
- [x] Afterglow 중복 Cloud Shell image/package/version-sync/CI 정본을 제거한다.
- [x] 설정 경계·Zun HTTP payload·image 미게시 실패/cleanup을 관련 회귀와 실제 runtime 경로로 검증한다.
- [x] 로컬 source/image/bootstrap 검증 후 GitHub private repo에 push하고 정확한 SHA Actions 및 게시 manifest/digest를 확인한다.
- [x] 실제 증거·blocked live 경계를 운영 문서/changelog/architecture에 반영하고 OpenSpec을 검증·정리한다.
