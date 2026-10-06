## Why

이미지 모델은 텍스트 입력 단가만 있고 출력 단가는 없을 수 있다. 현재 관리자 UI 및 Lumen의 text-kind 저장 검증은 입력·출력을 한 쌍으로 강제하여 기존 text-kind 이미지 등록도 저장을 차단한다. 음성의 단방향 텍스트·오디오 가격에도 같은 문제가 생긴다.

## What Changes

- 모델 종류나 이름을 추측하지 않고 텍스트 입력·출력 수동 단가를 독립적으로 저장한다.
- 변경한 필드만 PATCH하고, 빈 값은 null 해제, 명시적 0은 무료 단가, 미변경 값은 보존한다.
- Lumen API·repository의 쌍 저장 제약을 제거한다. 수치 정밀도, 음수/유한값, 실행 admission 및 실제 과금의 필수 가격 검증은 유지한다.
- 이미지·TTS·STT·realtime과 기존 text-kind media 가격을 브라우저 및 실제 관리자 HTTP/저장 경로로 검증한다.

## Capabilities

### New Capabilities

없음.

### Modified Capabilities

관리자 모델 단가 등록·수정: 지원하지 않는 방향의 텍스트 단가를 강제로 만들지 않는다.

## Impact

Afterglow ChatConfiguration와 가격 회귀, Lumen 모델 API·provider repository, 양쪽 가격 계약 문서. DB schema·migration·provider protocol·실행 과금 정책은 변경하지 않는다. 기존 사용자 변경·공유 stack·운영 모델/설정은 보존한다.
