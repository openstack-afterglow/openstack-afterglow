## Why

전체 unit의 Kolla1실패/RBAC6error를 단순히 기존 실패로 분류할 수 없으므로 동일 환경의 독립 selector와 HEAD baseline을 비교했다. HEAD 8f5d2a6ea4f8018702a9290e07c5204cde3a9064에서도 RBAC6error가 재현됐으나 country-startup은 통과했다. 현재의 alias snapshot checksum layer를 직접 추출한 startup fixture가 누락한 회귀다.

## What Changes

- Country-startup 실제 Ansible smoke fixture에 정제 alias 파일과 필수 snapshot path 변수를 제공한다.
- 실 startup guard/checksum/Docker side-effect sandbox는 유지한다. Production task/defaults·UI·quota·auth는 변경하지 않는다.
- HEAD/현재 독립 실행의 RBAC 동일 오류와 Kolla 실패 전/통과 후를 기록한다. 공유 worktree/index/설정·운영 서비스는 보존한다.

## Capabilities

### Modified Capabilities
- 기존 Kolla country data pin과 restart identity의 국소 검증 입력 완전성.

## Impact

테스트 fixture 세 줄만 추가하며 runtime 구조/schema/설정 변경은 없다. HEAD baseline은 같은 설치된 Python/Ansible와 private config의 read-only symlink를 사용했고 실제 외부 접근은 network guard가 차단했다. 임시 baseline worktree는 검증 후 제거한다. Full gate stale marker와 baseline RBAC fixture 공백은 성공으로 바꾸지 않는다.
