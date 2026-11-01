# VM 자원 숫자·슬라이더 입력

## 목표와 범위
CPU·RAM·GPU 개수의 긴 select를 동기화한 숫자 직접 입력과 native range로 대체한다. GPU 모델 select, 기존 same-host conditional options·native quota·저장/복원·인가/unknown fence는 유지한다. Backend/API/DB/배포 변경은 없다.

## 완료 기준
- 각 숫자 자원에 현재 범위의 양 끝과 단위를 표시한다.
- 숫자는 정수 범위 내 직접 편집하고 RAM은 GiB↔MiB로 정확히 변환한다. 빈/소수/범위 밖 입력으로 과거 사양을 저장하지 않는다.
- Slider는 서버가 반환한 이산 값만 이동하며 현재 부족해진 값은 숫자 입력에 보존하고 저장을 차단한다. 드래그 미리보기는 숫자와 동기화하고 release에서 한 번 재검증한다.
- 기존 scope별 restore, 명시 저장 및 GPU 소진 메시지를 보존하고 mobile/tablet/desktop·light/dark에서 확인한다.
