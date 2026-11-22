# Kolla 이미지 선택 누락 오류 안내 개선

## Why

Kolla의 Afterglow 이미지 참조 선택은 첫 targeted controller에서만 실행됩니다. 그 첫 호스트가 앞선 play의 실패로 active host 목록에서 빠지면, 남은 controller에서는 selection task가 모두 skipping되고 마지막 readiness assert가 2차 실패로 끝납니다. 현재 fail message만으로는 최초 실패를 찾으라는 점이 드러나지 않습니다.

## What Changes

- `resolve_image_refs.yml`의 selection readiness assertion에 첫 targeted controller 이름을 표시합니다.
- 첫 호스트가 현재 active play host 목록에서 빠진 경우, 이 assertion은 2차 실패일 수 있으므로 앞선 `fatal`을 확인하라는 안내를 추가합니다.
- Kolla 배포 문서, changelog, architecture review summary를 갱신합니다.

## 범위 밖

- 이미지 resolver 동작, host selection, Kolla lifecycle, 운영 설정은 변경하지 않습니다.
- 운영 재실행이나 배포는 수행하지 않습니다.
