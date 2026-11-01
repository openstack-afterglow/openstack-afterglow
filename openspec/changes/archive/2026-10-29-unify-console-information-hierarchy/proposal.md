# 정돈된 클라우드·AI 운영 콘솔

## Why
사용자가 제공한 2026-10-29 사용자·관리자 UI 평가의 13개 절 전체를 현재 소스와 대조하고 조치한다. 제품의 기존 차콜/노을 정체성, 설치별 브랜드, API/권한/데이터 경계를 보존하면서 정보 우선순위와 화면 간 규칙을 통일한다. 기존 공유 dev 작업과 index는 보존한다.

## Scope / completion
1. 보고서의 13개 확인 화면 및 주요 상태를 현재 구현과 대조한다.
2. 사용자/관리자 인스턴스·네트워크·볼륨: 범위→제목/주 행동→한 줄 요약→검색/필터/새로고침→표/카드→하단 페이지 컨트롤. 추이는 기본 접힘, 관리자 볼륨 집계는 용량 분석에 분리. 1440×900 첫 화면 여러 행.
3. 기존 토큰을 재사용해 따뜻한 주요 행동, 중립 선택/아이콘, 의미 있는 상태색을 통일한다. 제안 hex는 강제 교체값이 아니며 기존 디자인 권위를 유지한다.
4. 읽을 수 있는 본문/보조 글자, 36px 데스크톱/44px 터치 조작, 44px 기본 행, tabular 숫자/우측 수량, identifier만 mono.
5. 기능 우선 한국어 서비스 이름, 브랜드 병기, 같은 목적지의 공통 navigation/search, 명시적 범위와 전체 서비스 복귀, 즐겨찾기/최근.
6. 사용자 dashboard empty 시작 행동 및 telemetry unknown/error/empty 구분. 관리자 조치→용량→운영 이벤트→전체폭 도메인 분포→작은 관리 통계.
7. 실제 CPU/가상 할당/물리 대비와 프로비저닝/실측 storage를 구분. 막대만 clamp하고 텍스트 실제 비율; 정책 초과와 정상 overcommit을 혼동하지 않는다.
8. 공통 상태 텍스트/기술 코드, 짧은 UUID+전체/복사, domain/project 소유자, 일관 이름 링크, network 행 메뉴, 위험 확인 및 선택 시에만 bulk bar. 기존 공통 상세 페이지를 재사용하고 부족한 표면만 보완.
9. VM wizard의 기존 4단계를 유지하며 loading/failure/catalog-empty/filter-empty/quota/capacity를 분리하고 재조회 경로 제공. 프로젝트 이름/도메인/짧은 ID. 기존 선택/권한/ABA fence 보존.
10. 토폴로지 domain/project grouping, 펼침, 선택 직접연결 강조, inspector, 저배율 요약, 약한 격자, animation 기본 off/명시 설명, 일정 toolbar/help.
11. Drover 오류 요약/전체 상세; Palimpsest 레이어/빌드/프로필/인스턴스 및 명시 기반 선택; Lumen 실제 권한/범위/복구 안내; 설정 branding/infra/enrollment/quota/requests 분리 및 설명 지역화; Cloud Shell 단일 header.
12. 로고/선형 아이콘/사이드바 유지, 반복/장식 감축, 설치 이름과 Afterglow 제품 관계 설명.
13. 모든 묶음 구현 후 실제 Chromium, responsive 390/767/768/1023/1024/1440, 두 테마, 지원 9개 locale 및 키보드/오류/빈/미수집 상태 검증. 관련 selector→전체 frontend/gate 및 문서/architecture 갱신.

## Non-goals / safety
운영 배포, native 리소스 CRUD, IAM 변경, credential 수집, schema/config/dependency 변경을 승인받은 것으로 간주하지 않는다. Synthetic browser evidence는 native/provider/live acceptance가 아니다. 조회 실패를 빈 성공이나 0으로 숨기거나 권한을 완화하지 않는다. 동일 현상은 사용자 관측을 ground truth로 취급하고 이를 재확인하는 목적의 운영 요청을 반복하지 않는다.

## 추가 사용자 요구: 라이트·다크 공동 개선
사용자가 추가 제공한 라이트 평가8개 절 전체를 기존 범위와 함께 구현한다. 기존 DESIGN의 기존 색상값 보존 규칙보다 이번 명시적 요구가 우선한다. 제안 hex를 일괄 치환하지 않고 실제 토큰/조합을 측정한다.
- 흰 카드·표·편집 가능한 input, 옅은 중립 page, 회색 readonly/disabled를 구별하고 selected underline/명확한 surface·focus outline을 제공한다.
- 네트워크/인스턴스 상태 text부터 actual wash 대비4.5:1 이상과12–13px·점/아이콘/이름을 검증한다. Fill/line/text 역할별 token은 분리한다.
- 프로젝트 선택은 기본 얇은 구분선·hover·선택된 행만 강조한다. 관리자 domain 표는 fullwidth,service 요약은 content height로 둔다.
- 라이트 chart fill/legend/line/dash, topology white board·약한 grid/zone·선택 직접연결과 저배율 group summary를 함께 검증한다.
- 모든 테마 순환 control을 light/dark/system+check 선택 메뉴로 교체하고 system 현재 적용 결과를 표시한다. 실제 OS media 변경 추종도 검증한다.
- 같은 instance 기준 화면을 두 테마로 실제 렌더링하고 responsiveness/keyboard/200% 확대를 포함한다.
