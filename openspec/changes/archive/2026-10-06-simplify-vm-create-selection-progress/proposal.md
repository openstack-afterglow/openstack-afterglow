## Why

VM 생성 마법사는 동일 이름의 이미지 태그를 별도 카드로 노출하고, 사용에 필요하지 않은 active/raw/해시 정보를 과다 표시한다. 선택한 flavor의 쿼터 추가량과 기존 사용량의 대비가 부족하다. GitHub 최근 사용자 재선택은 검증 상태를 잃고, 배포 경과 시간은 SSE 갱신 시점에만 변한다. 생성 완료 목적지와 인스턴스 SSH 기본 정보도 실제 접속 방식과 맞지 않는다.

## What Changes

- VM 이미지 선택은 기존 canonical repository/tag와 current-upload 규칙을 재사용한다. repository 이름별 카드 한 개, 카드 선택 후 태그 선택, repository 및 태그는 created_at 최신순(미확인 날짜 마지막)으로 표시한다. OS 필터는 유지하며 inactive current tag를 이전 active UUID로 대체하지 않는다.
- VM 이미지 카드 및 태그 선택에서 SHA, raw, 현재/active 부가 표시는 제거한다. 이미지의 OS, 이름, 태그, 크기/업로드 일자 및 명시적 비활성 선택 사유만 필요한 위치에 유지한다. 이미 선택한 과거 UUID는 자동 변경하지 않는다.
- flavor 쿼터는 기존 할당량/이번 VM 추가량/잔여 영역을 기존 디자인 token과 공용 meter 패턴으로 구분한다.
- 동일한 최근 GitHub ID의 재선택은 현재 검증 프로필을 유지하고, 다른 ID 선택에는 검증을 다시 적용한다.
- 배포 시계를 SSE 수신과 독립적으로 1초 단위로 갱신한다. 총 경과 시간과 실제 관측된 단계별 소요 시간을 표시하고 완료/실패/종료 시 정지·정리한다.
- 사용자 VM 생성 성공은 /dashboard/compute/instances, 관리자 성공은 /admin/instances로 이동한다. SSE/mock/squashfs 경로에 동일하게 적용한다.
- GitHub SSH 방식 및 canonical GitHub login을 VM 생성 시 Nova metadata에 기록한다. 일반/관리자/비동기/squashfs 생성과 공용 인스턴스 기본 정보에 반영한다. 기존 keypair 방식은 유지하며 GitHub 값이 없는 과거 VM을 추측하지 않는다.

## Capabilities

### New Capabilities

- `vm-create-experience`: 이미지 이름/태그 선택·최신 업로드·쿼터 preview·GitHub 검증 유지·관측 배포 시간·완료 navigation·명시적 SSH metadata의 사용자 계약.

### Modified Capabilities

- 기존 main capability 변경 없음. VM cloud-init bootstrap·인증·allocation 계약은 유지한다.

## Impact

Svelte VM wizard, 기존 image catalog/reference utility, 공용 usage meter, instance detail 및 FastAPI/Nova server 생성·projection 경로가 대상이다. DB schema, 인증 방식, OpenStack allocation 및 provider 정책은 변경하지 않는다. 기존 공유 worktree/병합 상태와 무관한 변경은 보존한다. 수정 경로는 focused regression와 격리 API smoke, 실제 Chromium의 synthetic API fixture로 검증한다. 로컬 UI fixture 성공을 실제 OpenStack VM 생성이나 운영 배포 증거로 보고하지 않는다.
