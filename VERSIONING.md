# 버전 관리 정책

이 프로젝트는 [유의적 버전 2.0.0](https://semver.org/lang/ko/)을 따릅니다.

---

## 버전 형식

```
MAJOR.MINOR.PATCH
```

배포된 버전의 내용은 절대 변경할 수 없습니다. 변경이 필요하면 반드시 새 버전을 릴리즈합니다.

---

## 버전 증가 기준

### MAJOR (주버전) — 하위 호환성 파괴

다음 중 하나라도 해당하면 MAJOR를 올립니다.

- 공개 REST API의 요청/응답 구조 변경 (필드 제거·이름 변경·타입 변경)
- 인증 방식 변경 (예: Bearer JWT 외 다른 방식으로 교체)
- `afterglow.conf` 필수 항목의 키 이름 변경 또는 제거
- union mount 레이어 시스템의 메타데이터 스키마 파괴적 변경
- DB 마이그레이션 중 데이터 손실이 발생하거나 롤백이 불가능한 경우
- 기존 클라이언트(프론트엔드 또는 외부 API 소비자)가 재설정 없이 동작하지 않는 경우

MAJOR 증가 시 MINOR와 PATCH를 0으로 초기화합니다.

### MINOR (부버전) — 하위 호환 기능 추가

다음 중 하나라도 해당하면 MINOR를 올립니다.

- 새 REST API 엔드포인트 추가
- 기존 응답에 선택적 필드 추가 (기존 클라이언트에 영향 없음)
- 새 라이브러리 레시피 또는 k3s 플러그인 지원 추가
- 기존 기능의 유의미한 개선 (성능, UX, 관리 기능 등)
- 기존 기능을 deprecated 표시 (아직 제거하지 않음)
- `afterglow.conf`에 선택적 항목 추가

MINOR 증가 시 PATCH를 0으로 초기화합니다.

### PATCH (수버전) — 하위 호환 버그 수정

다음 중 하나에 해당하면 PATCH를 올립니다.

- API 동작의 오류 수정
- 보안 취약점 패치 (API 서명 변경 없음)
- 문서, 번역, 주석 수정
- 의존성 패치 버전 업데이트

---

## 사전 릴리즈 표기

정식 배포 전 검증이 필요하면 다음 접미사를 사용합니다.

| 단계 | 형식 예시 | 의미 |
|------|-----------|------|
| 알파 | `1.16.0-alpha.1` | 내부 테스트 중, API 불안정 |
| 베타 | `1.16.0-beta.1` | 기능 완성, 버그 수정 중 |
| RC | `1.16.0-rc.1` | 릴리즈 후보, 최종 검증 |

사전 릴리즈 버전은 정식 버전보다 우선순위가 낮습니다.
(`1.16.0-rc.1` < `1.16.0`)

---

## 버전 태그 규칙

- Git 태그 형식: `v{MAJOR}.{MINOR}.{PATCH}` (예: `v1.15.0`)
- `v` 접두어는 Git 태그 전용입니다. `CHANGELOG.md`, API 응답, 문서에서는 `1.15.0` 형식을 사용합니다.
- 배포 요청의 tag는 [개발 가이드의 완료 계약](docs/agent-development-guide.md#사용자-요청-배포의-완료-계약)에 따라 정상 push한 정확한 `dev` commit의 CI 성공 뒤 생성한다.
- `dev → main` PR·merge는 pie_root가 수행하며 이 절차가 main 승격 승인을 대신하지 않는다.

```bash
# 정확한 dev SHA의 CI 성공 뒤, 승인된 배포 작업에서 수행
git tag -a v1.16.0 -m "release v1.16.0"
git push origin v1.16.0
```

---

## CHANGELOG 연동

모든 버전 릴리즈에는 반드시 `CHANGELOG.md` 항목이 있어야 합니다.

- 형식: [Keep a Changelog 1.1.0](https://keepachangelog.com/ko/1.1.0/)
- 섹션: `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, `Security`
- `[Unreleased]` 섹션에 변경을 누적하다가 릴리즈 시 버전 날짜로 전환합니다.

---

## 현재 버전 참고

| 항목 | 값 |
|------|----|
| 현재 최신 버전 | `v1.18.1` |
| 공개 API 안정화 | `v1.0.0` 이후 |
| 다음 기능 릴리즈 | `v1.19.0` (MINOR 증가) |
| 다음 버그 수정 | `v1.18.2` (PATCH 증가) |
---

## 참고 문서

- [유의적 버전 2.0.0 (한국어)](https://semver.org/lang/ko/)
- [Keep a Changelog 1.1.0 (한국어)](https://keepachangelog.com/ko/1.1.0/)
- [CHANGELOG.md](./CHANGELOG.md)
