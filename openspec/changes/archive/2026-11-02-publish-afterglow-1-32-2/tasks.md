## Implementation Tasks

- [x] 현재 dev·원격 ancestry·tag 부재와 검증된 source를 확인하고 다른 세션 WIP를 보존한다.
- [x] 버전 상향은 release 발행까지 포함한다는 사용자 규칙을 기록한다.
- [x] 검증된 source와 문서만 dev에 정상 push하고 정확한 SHA의 CI 성공을 확인한다.
- [x] 불변 numeric 1.32.2 tag를 게시하고 tag image·Helm workflow 성공을 확인한다.
- [x] GitHub Release 및 release/latest image digest·revision, Helm metadata를 검증한다.
- [x] 결과와 운영 미배포 경계를 기록하고 checklist를 archive한다.

## Qualification

- Final source4b493144891cc6a6495560ba7a4339c09a0593a1, source fingerprint afcfe6686bef0f5431f580634c14d2680350ff9b1e61cb9a37580a40fdfdbc92/3942files. Local isolated gate exit0: backend12428/106skip, frontend6446/502files, contracts183, disposable realDB167/37deselected, Ruff820; artifact586. Linux Python3.12.3 actual setup11passed.
- Exact-SHA sourceCI41472014102 success, including3amd64 build and3manifest jobs. Immutable numeric1.32.2 tag pushed on that SHA only after success. Tag-triggered publication was verified separately in the receipt below.
- Prior CI failures41467016850/41467160186/41469295043 were preserved, not rerun-until-green. Diagnostic/probe traced prompt-vs-read timing; fixture synchronizes actual terminal read and preserves cancellation/no-write/secret checks. No production CLI fix is claimed.

## Publication Receipt

- GitHub latest stable release: https://github.com/openstack-afterglow/openstack-afterglow/releases/tag/1.32.2 . Remote annotated tag와 release target metadata 모두4b493144891cc6a6495560ba7a4339c09a0593a1이다. Main branch/PR/merge나 기존1.32.1 tag를 변경하지 않았다.
- Numeric tag imageCI41473493948·Helm41473493855 success. API/frontend/worker의1.32.2/latest digest·OCI revision 일치, linux/amd643images network-none/read-only/non-root runtime1.32.2 확인. Canonical workflow는 현재amd64만 발행한다.
- API sha256:360b051bc718c705bac619cdf7d6e6e2e1e0a9069ff3c5ebf213d3f6f238388e; frontend sha256:811c02601dab43cb64f1ffe3d4918e6cd9d934f6237412d84c784a77f6b46f0a; worker sha256:c733b99c6c3caee4789d04770180f69be7261260d1f347076847c9a1ed8c55b4.
- Published OCI Helm version/appVersion1.32.2 확인. Chart 기본 image alias는latest이므로 운영 immutable pin은 별도 선택이다. 운영 Kolla/native/schema/shared datastore 변경은 실행하지 않았다.
- Evidence: `~/.local/share/afterglow-proofs/release-1.32.2-20261102/`. Own isolated qualification clone·throwaway probes는 정리했고 동시 Pi/chat/SSO source·문서·private 설정은 보존·제외했다.
