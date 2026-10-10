---
layout: default
title: 사용자 서비스 가이드
lang: ko
---

# 사용자 서비스 가이드

Afterglow의 사용자 문서 경로는 **배포된 콘솔 origin의 `/docs`**다. 개발자 API 참고 자료·설치 문서와 분리하여 현재 콘솔에서 자원을 준비하고 사용하는 방법을 설명한다. 메인 페이지의 **Docs / 사용 가이드**와 사용자 콘솔 헤더·전체 메뉴의 **Docs · 사용 가이드**, 커맨드 팔레트에서 이동한다.

문서를 읽는 데 로그인이나 프로젝트 선택은 필요하지 않다. 실제 콘솔 작업에는 인증, 현재 프로젝트의 권한·쿼터와 해당 서비스 활성화가 필요하다. 문서가 있다는 사실은 특정 배포의 서비스 설치·가용성 또는 자원 생성 성공을 뜻하지 않는다.

## 지원 언어

전체 14개 가이드는 한국어, 영어, 일본어, 중국어 간체로 읽을 수 있다. 문서 헤더의 언어 메뉴에서 선택하며 본문·탐색·검색·목차·명령 복사·오류 안내가 함께 바뀐다.

| 언어 | 문서 홈 | 예시 가이드 |
|---|---|---|
| 한국어 (기본) | `/docs` | `/docs/manila#mount` |
| English | `/docs?lang=en` | `/docs/manila?lang=en#mount` |
| 日本語 | `/docs?lang=ja` | `/docs/manila?lang=ja#mount` |
| 简体中文 | `/docs?lang=zh-CN` | `/docs/manila?lang=zh-CN#mount` |

언어 전환은 현재 문서·목차 fragment·기존 query를 보존한다. 문서 내부 링크는 선택 언어와 튜토리얼 context를 유지한다. 지원하지 않는 `lang` 값이나 값이 없는 URL은 한국어로 표시하며 브라우저 언어에 따른 자동 redirect·계정 언어 저장은 하지 않는다. 공유할 때 `lang` query를 포함한 URL을 사용한다. 최초 SSR과 client navigation의 문서 언어를 모두 설정하지만 미번역 콘솔·로그인 화면은 기존 한국어를 유지한다.

검색은 선택 언어의 전체 본문과 키워드를 대상으로 한다. 명령의 API·상태·환경변수·필드·경로와 최종 code bytes는 네 언어가 공유하며 실행 예시 placeholder와 필수 변수 진단은 중립적인 영어를 쓴다. 실제 한국어 콘솔 버튼을 찾기 위해 일부 번역 문장에서 원래 UI 이름을 번역 뒤 괄호에 함께 표시한다.

## 문서 경로

| 경로 | 사용 목적 |
|---|---|
| `/docs` | 서비스 및 본문 검색, 전체 가이드 목록 |
| `/docs/getting-started` | 로그인·프로젝트·권한·쿼터와 첫 VM 준비 |
| `/docs/nova` | 인스턴스 생성·접속·상태·수명주기 |
| `/docs/neutron` | 네트워크·서브넷·라우터·Floating IP·보안 그룹 |
| `/docs/octavia` | VIP·리스너·풀·멤버와 헬스 확인 |
| `/docs/cinder` | 볼륨 연결·게스트 사용·스냅샷·백업 |
| `/docs/manila` | 공유 파일시스템·접근 규칙·export·스냅샷 |
| `/docs/glance` | 부팅 이미지 선택·업로드·이미지 관리 |
| `/docs/object-storage` | 버킷·폴더·객체 업로드·다운로드·휴지통과 외부 S3 접근 조건 |
| `/docs/trove` | 데이터베이스 인스턴스·접속·백업·복원 |
| `/docs/barbican` | 비밀 값 생성·조회·삭제와 자격 보호 |
| `/docs/drover` | Kubernetes 클러스터·노드·kubeconfig·워크로드 |
| `/docs/waygate` | WireGuard 게이트웨이·클라이언트·설정·연결 |
| `/docs/lumen` | AI 채팅·Studio·모델·한도·API/CLI 연결 |
| `/docs/palimpsest` | 프로젝트 패키지·접근 키·불변 레이어 재사용 |

각 가이드는 준비 사항, 작업 순서, 결과 확인, 정리·데이터 손실 주의, 장애 대응, 관련 문서와 콘솔 링크를 제공한다. 일부 작업은 UI가 아닌 외부 CLI 예시임을 본문에서 구분한다. 명령은 복사할 수 있으며 실제 환경의 이미지·사용자·ID·IP·파일 경로로 바꾸어 실행한다. 문서를 열거나 명령을 복사하는 것만으로 실행되지는 않는다.

## 접근 및 표시 경계

- `/docs`와 `/docs/` 아래 경로만 공개 문서 범위다. `/docsevil`·`/docs-admin` 같은 유사 접두 경로의 인증 조건은 바꾸지 않는다.
- 미등록 서비스 문서는 404와 문서 홈 안내를 유지한다. 로그인 상태라는 이유로 문서 404를 SPA 홈 200으로 바꾸지 않는다.
- 공개 문서는 로그인 세션의 프로젝트 선택·인증 복구 화면을 요구하지 않고 인증 갱신·공지 polling을 시작하지 않는다. 이전 콘솔 요청이 세션 만료로 실패해도 현재 문서에서 로그인 화면으로 이동하지 않는다. 기존 보호 콘솔의 인증·프로젝트 검사는 유지한다.
- 문서 내용은 서비스 활성화와 관계없이 읽을 수 있다. 선택 서비스의 하단 콘솔 링크는 현재 공개 site-config의 서비스 gate를 반영한다. API 권한 검사는 여전히 백엔드가 소유한다.
- 튜토리얼에서도 문서 진입이 허용되며 문서 내용을 가상 자원 응답으로 대체하지 않는다. 콘솔 복귀는 기존 튜토리얼 범위를 유지한다.
- 모바일은 문서 메뉴·목차를 inline disclosure로 제공하고, tablet은 서비스 문서 탐색 열, desktop은 문서 내부 목차 열을 추가한다. 코드의 가로 스크롤은 해당 영역 안으로 제한한다.
- Key Manager에서 이미 표시한 비밀은 다른 값 조회가 진행 중이어도 즉시 숨길 수 있다. 새 값 조회는 직렬화하지만 숨기기는 로컬 동작이므로 네트워크 완료를 기다리지 않는다.

## 내용 수정 위치

사용자 문서 정본은 `frontend/src/lib/docs/`의 typed static data다. 같은 내용을 별도 Markdown·HTML 엔진에 복제하지 않는다.

- `types.ts`: guide·section·step·command·link 계약.
- `gettingStarted.ts`: 프로젝트 시작 절차.
- `coreGuides.ts`: Nova·Neutron·Octavia·Cinder·Manila.
- `additionalGuides.ts`: Glance·Object Storage·Trove·Barbican.
- `platformGuides.ts`: Drover·Waygate·Lumen·Palimpsest.
- `catalog.ts`: 전체 목록, 선택 언어 catalog의 lazy load/cache와 검색 인덱스.
- `paths.ts`: 정확한 공개 문서 경로 판정.
- `locales.ts`: 지원 언어·URL context·번역된 shell/index/article/copy/error 문구와 카테고리.
- `translate.ts`: reader-facing 필드 변환; 누락·빈 번역은 오류로 처리하고 한국어 본문으로 조용히 fallback하지 않는다.
- `translations/{en,ja,zh-CN}/`: 언어별 guide group dictionary. source literal key를 유지하고 한국어 정본 변경 시 세 언어의 해당 항목도 함께 갱신한다. slug·section ID·link URL·service gate·related slug·실행 code는 번역 대상이 아니다.
- `frontend/src/routes/docs/`: 공개 shell·목록·서비스 article·404 화면.

본문은 Svelte text node로 escape되며 raw HTML을 주입하지 않는다. 외부 URL·내부 콘솔 링크·명령을 추가할 때 현재 route/component/API를 확인하고 실 credential, 운영 내부 주소, 개인 데이터를 예시에 넣지 않는다. 서비스의 API 계약은 [API 참고 자료](api-reference.md), 시각 계약은 [디자인 시스템](https://github.com/openstack-afterglow/openstack-afterglow/blob/dev/DESIGN.md)을 따른다. 사용자 문서 변경만으로 API 실행·데이터 플레인·운영 배포 성공을 기록하지 않는다.
