# Afterglow 범용 문자 에셋 테마

이 테마는 Lumen 전용이 아니다. 모든 서비스의 장식 일러스트, 빈 화면, 검색 결과, 연결·전송 대기, 오류·완료 안내에 같은 문자 그래픽 언어를 적용한다. 사용처 목록은 [에셋 인벤토리](asset-theme-inventory.md), 실제 상태 경계는 [Lumen 조사](lumen-loading-audit.md)를 함께 참고한다.

## 정본과 배포 파일

- `frontend/src/lib/design/characterAssets.json`: 에셋 ID·분류·카탈로그 이름·문자 아트의 정본.
- `frontend/src/lib/components/ui/AssetGlyph.svelte`: 앱 내 공통 렌더러. 정본을 직접 읽으며 기존 사용처도 같은 에셋을 받는다.
- `frontend/static/theme/afterglow/`: 정본에서 생성한 독립 TXT, 문자만 포함한 투명 SVG, manifest와 카탈로그. 다른 앱·문서·슬라이드·서버 렌더러에서도 사용 가능하다.
- `scripts/generate-character-assets.py`: 생성기. `--check`는 정본과 생성물의 일치 여부를 검사한다.

파일을 따로 수정하지 않는다. 정본을 수정한 뒤 생성기로 공개 파일을 갱신한다. ID는 안정적인 계약이며 기존 ID를 임의로 삭제하거나 이름을 바꾸지 않는다. 카탈로그 이름은 설명용이고 앱에 표시하는 상태 문구는 기존 i18n을 사용한다.

## 선택 방법

|환경|에셋 계열|표시 원칙|
|---|---|---|
|컴퓨트·VM·컨테이너·클러스터|compute, container, kubernetes, cloud|서비스 소개·빈 화면·설정 안내의 장식|
|네트워크·연결|network, connecting, offline|연결 전·진행 중·끊김을 실제 상태 문구로 분리|
|볼륨·스토리지·백업·DB|storage, backup, database|무자료와 조회 실패를 구분|
|IAM·보안·권한|security, locked|권한 차단을 작업 중으로 표현하지 않음|
|AI·채팅·이미지·음성|ai, chat, image, audio|사용자 콘텐츠 자체를 대체하지 않고 주변 대기·오류를 표현|
|전송·처리|upload, download, processing, queued|동작 정체성을 정적 에셋으로, 실제 대기는 LoadingState로 표시|
|공통 상태|empty, search, error, success, canceled|항상 실제 설명·복구 동작과 함께 사용|
|정보·업무 도구|document, terminal, monitoring, table, progress|소개 장식이며 실제 데이터·명령·표·진행률을 흉내 내지 않음|

## 앱 사용 예

```svelte
<script lang="ts">
  import { AssetGlyph } from '$lib/components/ui';
</script>
<AssetGlyph variant="storage" />
```

에셋은 기본적으로 장식이며 `aria-hidden`이다. 옆에 번역된 제목·설명과 필요한 복구 동작을 둔다. 에셋 자체에 상태 권위를 부여하지 않는다. 독립 SVG를 img로 쓰면 장식은 `alt=""`, 유일한 의미 전달 이미지라면 번역된 대체 텍스트를 제공한다.

## 색상·크기·반응형

앱은 기존 `--afterglow-artwork-*` 별칭과 `--font-mono`, 타입 토큰을 사용한다. 기본은 선택한 Afterglow 웜 계열이고 light/dark의 배경·대비를 함께 따른다. 실제 위험·성공 상태는 Alert/StatusChip의 의미 색상을 유지한다. SVG 파일은 단독 사용을 위한 웜 기본색을 포함한다. 외부 img의 currentColor가 부모에서 전달된다고 가정하지 말고, 앱의 실시간 테마 전환은 AssetGlyph 또는 TXT/manifest 렌더링을 사용한다.

문자의 고정 폭·공백·줄바꿈을 보존한다. 좁은 공간에서는 문자를 잘라 쓰지 말고 영역용 에셋 대신 compact LoadingState나 텍스트 상태를 선택한다. 손가락으로 누르는 버튼·메뉴를 문자 장식으로 대체하지 않는다. 큰 일러스트는 PageShell·Card 내부에서 폭을 제한한다.

## 동작·상태

정적 파일은 움직이지 않는다. 로딩·스트리밍은 기존 LoadingState/characterTicker, 확정 진행은 ProgressTrack을 사용한다. 테마 파일을 고른 것만으로 임의 타이머나 진행률을 만들지 않는다. hidden/offscreen/reduced-motion/unmount 정리 계약을 지킨다. 완료·실패·취소·권한 차단의 로딩을 멈춘다.

모델 응답, 이미지 다운로드·디코딩, 음성 버퍼링, 실제 연결 단계의 관측은 각 기능 소유자의 책임이다. 에셋 제작과 해당 상태 로직의 구현·실환경 검증은 별개다.

## 적용 경계

새 장식 일러스트는 이 레지스트리를 먼저 사용한다. 새 변형이 필요하면 정본·생성 파일·공통 렌더·관련 테스트·이 가이드를 함께 갱신한다. 제품 로고·업로드 로고·사용자 이미지·문서 증거 캡처·데이터 차트·토폴로지·기능 아이콘은 시각 의미와 원본을 보존한다.

## 이번 제작 검증 — 2026-11-01

정본은34종이며 TXT34개·문자 전용 SVG34개와 manifest·카탈로그·가이드 총73개 공개 파일을 생성했다. 기존7개 ID와 아트는 보존했다. 생성기 `--check`, SVG 태그/공백/텍스트 일치, 링크 검사와 관련4파일17테스트가 통과했다. `svelte-check`는 오류0개·경고17개다. 독립 검토에서 SVG 제목ID 충돌을 수정하고 최종 승인을 받았다.

실제 Chromium 카탈로그에서34개 렌더링,5개 환경 필터,라이트/다크 전환과320/768/1440px 가로 넘침 없음을 확인했고 라이트·다크·모바일 캡처를 검토했다. 최종 콘솔 확인에서 새 오류는 없었다. 다른 브라우저·실제200% 확대·모든 인증화면/9언어 수용은 이번 라이브러리 제작의 검증 증거가 아니다. 전체화면의 상태 로직이 새로 구현됐다고 주장하지 않는다. 커밋·push·배포와 전체test:gate는 실행하지 않았다.

다운로드 묶음 `output/afterglow-theme.zip`은 독립 카탈로그/파일/manifest, 정본 JSON, 이 가이드와 DESIGN.md의 테마 절을 포함한다. 저장소 내 생성기는 원래 경로 구조를 기준으로 실행한다.

## Progress·status 변형 추가 — 2026-11-01

현재 정본은40종이고 생성 파일은89개다. 기존34종에 `progress-linear`, `progress-circular`, `status-dots`, `status-bars`, `status-brackets`, `status-spinner`를 추가했다. 개별 SVG/TXT는 정적 예시다. 실제 진행률에는 다음 API를 사용한다.

```svelte
<ProgressTrack shape="linear" value={42} label={t('actualTaskProgress')} />
<ProgressTrack shape="circular" value={null} active label={t('actualTaskWaiting')} />
<LoadingState variant="inline" indicator="dots" label={t('actualTaskWaiting')} />
```

위 t키는 사용 화면이 소유한 실제 번역키로 교체하는 예시다. 지원 상태 신호는dots/bars/brackets/spinner/wave이며 기존 기본값wave는 보존한다. 직접 포맷을 사용할 때는 characterFormats.js의 `linearProgress(value,step,active)`, `circularProgress(value,step,active)`, `statusSignal(type,step)`을 사용하고 시간·실제 작업·접근성은 소유자가 관리한다. 브라우저용 character-formats.js는 같은 정본 함수를 결정적으로 내보낸 파일이다. motion.html은 선택/일시정지/미확정 모드를 지원하는 독립 데모다.

관련5파일18테스트,0/100/unknown ARIA·백분율 부재,320/768/1440px 화면폭, 일시정지·재생 검증을 통과했다. 독립 소스 검토 승인과 생성물 일치 확인을 받았다. 타입 검사 결과는 기존과 동일한 오류0개·경고17개다. 실제 앱의 모든 호출부를 원형 또는 새 신호로 일괄 교체하지 않았으며, 선택 가능한 공통 변형과 파일을 제공한 변경이다.
