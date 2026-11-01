## Why

관리자는 현재 감지된 장치의 Nova PCI alias와 resource class를 찾아 JSON 세 필드에 반복 입력해야 하며 GPU와 동반 오디오를 한 이름으로 선택하거나 미매핑·사용 중 상태를 함께 확인하기 어렵다. 도메인 pool과 flavor 표시도 서로 다른 별칭을 사용한다.

## What Changes

- Nova API의 effective `[pci] alias` 설정에서 정확한 name/vendor/product 및 scheduling 관련 공개 필드만 추출한 읽기 전용 snapshot과 Placement 관측을 구분하여 관리자에게 보여준다. 누락·불일치·실패는 unknown/partial로 표시한다. Nova의 비밀·전체 설정을 Afterglow에 노출하거나 Nova를 수정하지 않는다.
- 관리자가 정확한 계산 alias와 오디오/동반 alias를 선택하여 명시 승인된 GPU 그룹으로 저장한다. 이름과 catalog는 분류 힌트이고 미확인 장치는 unknown으로 보존한다. 하나의 그룹은 하나의 주 GPU resource class를 갖고 각 구성요소는 별도 Nova attachment alias를 가진다.
- 그룹 이름과 개수에 따라 `gpu.{name}x{count}_{cpu}c_{ram}g`를 생성하며 기존 immutable Nova flavors와 명칭 충돌을 보존한다. 도메인 pool·GPU quota는 동일 그룹 이름을 보여주되 resource class 기준의 기존 accounting과 project/native quota 경계를 유지한다.
- 모든 관측된 PCI 자원과 configured alias를 매핑 여부·Placement 사용량/미확인 상태와 함께 조회한다. Placement는 등록되지 않은 물리 장치의 완전한 목록이나 동일 카드의 GPU/audio 동반 할당을 보장하지 않음을 명시한다.

## Capabilities

### New Capabilities

관리자용 정확한 PCI alias/Placement 관측과 선택 기반 GPU 그룹 작성.

### Modified Capabilities

관리형 GPU flavor 명칭, GPU pool과 quota의 그룹명 projection.

## Impact

Backend administrator API, Kolla의 안전한 Nova alias snapshot, 기존 flavor automation 및 quota, 관리자/UI/i18n, 회귀 및 관련 문서. 기존 native flavor, VM, 볼륨, quota 정책과 Nova 설정은 자동 삭제·변경하지 않는다. 신규 배포·운영 mutation은 별도 승인 범위다.
