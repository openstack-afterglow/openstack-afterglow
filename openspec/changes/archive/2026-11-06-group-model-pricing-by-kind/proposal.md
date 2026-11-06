## Why
모델 등록 검토에서 텍스트 캐시 단가가 오디오 단가 뒤에 붙어 오디오 가격으로 오해할 수 있고, 종류와 무관한 이미지·오디오 항목이 항상 노출된다. 별도 models.dev 가격 조회·적용은 관리자 수기 입력 흐름과 중복된다.

## What Changes
- 등록 검토·직접 등록·가격 수정의 텍스트 입력/출력과 캐시 읽기/5분 쓰기/1시간 쓰기를 같은 텍스트 토큰 단가 그룹에 배치한다.
- 종류에 따라 기본 토큰 가격 그룹을 선택한다. 텍스트는 텍스트만, 이미지는 이미지만, 음성 종류는 오디오만 우선 표시한다. 텍스트 등 다른 모달리티는 명시적으로 선택해 추가한다. 이미 저장한 모달리티 단가는 수정 화면에서 자동으로 보인다.
- 표시 선택과 가격 저장을 분리하여 단가·0/null·미설정·unknown JSON 및 기존 수정 diff 규칙을 보존한다.
- models.dev 프로바이더 선택·가격 조회·매핑·import·modal과 관련 호출/전용 회귀/안내를 제거한다. 모델 조회는 모델 추가 안의 기존 provider discovery를 유지한다.
- 기존 저장 가격·출처 metadata를 자동 변경하지 않는다. API/schema/native billing/권한/배포는 변경하지 않는다.
- 추가 사용자 보고: 관리자에 지정한 이미지·TTS 모델이 Studio에서 사용 불가인 원인을 목록·활성·가격·실행 경로 경계에서 조사한다. 운영 모델 자동 활성화·가격/권한 우회·유료 추론은 하지 않는다.

## Capabilities
### New Capabilities
없음.
### Modified Capabilities
관리자 모델 가격 편집의 그룹 표시와 수기 입력 전용 진입.

## Impact
ChatConfiguration, ModelMediaPricingEditor, 관리자 UI 회귀와 9 locale 안내, DESIGN/ARCHITECTURE 및 검증 문서. 실제 source UI smoke와 scoped/named regression으로 검증하며 운영 배포는 하지 않는다.
