## Why

Windows 등 패스워드 인증이 기본인 게스트 OS나 QEMU Guest Agent가 설치된 리눅스 인스턴스에서 기본 유저의 패스워드를 런타임에 설정/변경할 수 있는 Nova `changePassword` 기능이 필요하다.
기존 백엔드 API 및 UI는 관리자 전용(`require_admin`)으로 제한되어 있어 일반 사용자가 자신이 생성한 인스턴스의 패스워드를 재설정할 수 없었다.
보안 원칙에 따라 인스턴스 패스워드 변경은 인스턴스 생성자 본인 또는 시스템 관리자 권한이 있는 경우에만 허용해야 하며, 관리자 페이지는 모든 인스턴스 상세에서, 일반 사용자 페이지는 본인 소유(생성자) 인스턴스에서만 가능해야 한다.

## What Changes

- 백엔드 `precheck_admin_password` 및 `set_admin_password` 엔드포인트는 프로젝트 쓰기 권한을 먼저 검증하고 검증된 시스템 관리자 또는 실제 Nova 생성자(`user_id`)이면서 정확한 현재 프로젝트(`project_id`)인 경우만 허용한다. 수정 가능한 metadata·프로젝트 admin 역할·같은 프로젝트 소속만으로는 생성자를 인정하지 않는다.
- 다른 사용자가 생성한 인스턴스에 대한 비관리자의 패스워드 사전 점검 및 변경 시도는 403 Forbidden으로 거부한다.
- 프론트엔드 `instanceDetailController`는 프로젝트 쓰기 권한 및 검증된 시스템 관리자 또는 정확한 생성자·프로젝트 조건이 맞을 때만 precheck를 호출한다. 관리자 화면 진입만으로 관리자 권한을 부여하지 않는다.
- `InstanceHeader`의 관리자 상세는 검증된 시스템 관리자에게, 일반 사용자 상세는 본인 생성 인스턴스에만 비밀번호 변경 버튼을 제공한다. 권한이 없는 경우 사전점검/변경 요청도 보내지 않는다.
- 프론트엔드 `Instance` 인터페이스에 `user_id?: string | null` 필드를 추가하여 타입 안정성을 확보한다.
- 패스워드 변경 모달 및 API 호출 시 `effectiveProjectId`를 정확히 전달하고, 상태가 ACTIVE가 아니거나 QGA 미지원 시 비활성화 및 안내 툴팁을 제공한다.
- Windows 등의 볼륨 부팅은 Nova 루트 장치와 Cinder 이미지 메타데이터를 대조하고, 루트 장치가 숨겨져 있으면 유일한 bootable 볼륨만 허용한다. 모호하면 fail closed하며 `/dev/vda` 데이터 디스크로 계정/QGA를 추측하지 않는다.
- Nova 요청 접수와 게스트 적용/로그인 성공을 구분한다. 제출 중 입력·취소·close/Escape를 막고, 창 종료·인증 범위 변경 시 비밀 입력을 제거하며 오류·감사 기록에 비밀번호/upstream 원문을 노출하지 않는다.

## Capabilities

### New Capabilities
- 인스턴스 생성자(일반 사용자)가 자신의 인스턴스 상세 페이지에서 QEMU Guest Agent 기반 패스워드 변경 가능 여부를 확인하고 새 패스워드를 설정할 수 있는 기능.

### Modified Capabilities
- `GET /api/v1/instances/{server_id}/admin-password/precheck` 인가: 시스템 관리자 또는 생성자 본인 허용.
- `POST /api/v1/instances/{server_id}/admin-password` 인가: 시스템 관리자 또는 생성자 본인 허용.
- 관리자 인스턴스 상세 및 사용자 인스턴스 상세 화면의 비밀번호 변경 버튼 노출 조건.

## Impact

- 검증된 시스템 관리자의 인스턴스 비밀번호 변경 경로를 유지하고 Nova 정책·QGA/ACTIVE 요구 조건을 우회하지 않는다.
- 인스턴스 생성자가 아닌 다른 프로젝트 멤버가 타인의 인스턴스 패스워드를 가로채거나 변경하는 것을 원천 차단한다.
- 새 DB 스키마, 의존성, 인프라 변경 없이 순수 API 인가 및 UI 조건 확장으로 구현된다.
