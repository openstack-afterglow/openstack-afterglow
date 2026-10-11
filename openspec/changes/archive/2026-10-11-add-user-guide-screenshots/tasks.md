## Implementation Tasks

- [x] 15개 가이드의 상세 절차와 실제 UI를 대조하여 캡처 위치를 정한다.
- [x] 사용자 직접 인증 브라우저에서 제출 전 폼·목록·상세 화면을 캡처하고 민감정보를 제거한다.
- [x] 기존 문서 계약에 section/step screenshot, 접근 가능한 figure·원본 링크와 반응형 크기를 추가한다.
- [x] 모든 가이드의 세부 절차에 실제 asset과 번역된 alt·caption을 연결하고 검색·번역 계약을 유지한다.
- [x] 실제 로컬 `/docs` 렌더링에서 이미지 decode·원본 열기·네 언어·반응형·테마·민감정보를 검증한다.
- [x] 관련 기존 검증을 실행하고 상세 문서·디자인·아키텍처·변경 이력과 확인 범위를 기록한다.

완료 증거: 실제 콘솔 WebP 42장(15개 가이드), 네 언어 60개 경로의 168개 figure와 48개 반응형/테마 조건, 실제 원본 새 탭 클릭 및 최종 개인정보 제거 이미지의 문서 렌더링을 확인했다. 문서 테스트 36개·i18n check/scan·production build와 OpenSpec strict validation이 통과했다. 공개 자산 자체에서 실제 이름·식별자·주소·비밀을 제외했고 운영 자원/키/설정은 변경하지 않았다. 발견한 시각 문제 네 건은 `docs/user-guide-visual-review.md`, 상세 확인·전체 type-check/gate 한계는 `verification.md`에 기록한다. `public-service-docs` main spec에 screenshot requirement를 동기화했으며 운영 배포·전체 gate 통과 증거가 아니다.
