## Why

공개 `/docs`의 15개 사용자 가이드는 텍스트와 명령만 제공해 실제 콘솔에서 버튼·선택 단계·결과 확인 위치를 찾기 어렵다. 사용자가 직접 인증한 실제 배포 화면을 캡처하여 해당 세부 절차에 배치한다.

## What Changes

- 기존 typed static content의 section/step에 선택적 screenshot 데이터를 추가하고 figure·대체 텍스트·설명·원본 열기를 렌더링한다.
- 로그인·프로젝트·VM·네트워크·스토리지·DB·비밀 관리·Drover·Waygate·Lumen·Palimpsest·MCP의 실제 화면을 필요한 세부 단계에 추가한다.
- 공개 static WebP 파일만 제공하며 실제 credential·개인정보·민감 자원 식별자는 캡처 전 가리거나 캡처에서 제외한다.
- 한국어 콘솔 캡처임을 명시하고 설명·대체 텍스트·접근성 문구를 기존 네 문서 언어로 제공한다.

## Capabilities

### New Capabilities

- 사용자 절차에 연결된 실제 콘솔 화면과 읽을 수 있는 원본 이미지.

### Modified Capabilities

- 사용자 문서의 typed content, 다국어 번역·검색과 responsive article 렌더링.

## Impact

인증·API·DB·서비스 gate·기존 명령·운영 배포는 바꾸지 않는다. 캡처는 조회와 제출 전 폼 탐색만 수행하며 자원 생성·삭제, 키 발급·payload 조회, QR/비밀 설정 다운로드, 유료 provider 호출을 하지 않는다. 기존 동시 작업은 유지한다. 실제 화면 캡처와 로컬 변경 문서 검증을 운영 배포 완료 증거와 구분한다.
