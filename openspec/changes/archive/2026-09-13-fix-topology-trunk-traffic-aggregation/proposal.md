# 토폴로지 트렁크 트래픽 귀속 수정

## Why

provider 스위치에 여러 라우터가 연결된 경우 provider 네트워크 전체 NIC 합산값이 각 라우터 트렁크에 반복 표시되는 오류를 제거한다.

## What Changes

- 라우터의 external gateway 트렁크는 그 라우터가 직접 연결한 하위 네트워크들의 트래픽 합을 표시한다.
- 라우터와 하위 네트워크 스위치 사이 트렁크는 해당 하위 네트워크 트래픽만 표시한다.
- 라우터 exporter가 없는 한계와 방향별 NIC 합산이라는 기존 데이터 계약은 유지한다.

## 완료 기준

- 같은 provider 네트워크에 연결된 라우터들이 각자 다른 하위 네트워크 합산값을 표시한다.
- provider 네트워크 자체 합산값은 라우터별 external gateway 트렁크에 복제되지 않는다.
- 기존 cable, LB, isolated network 트래픽 표시가 회귀하지 않는다.
