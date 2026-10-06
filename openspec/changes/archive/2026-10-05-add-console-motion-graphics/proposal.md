## Why

콘솔의 생성·대기·전송 상태는 대부분 정적인 문구, 개별 spinner 또는 즉시 바뀌는 막대로만 표시된다. VM 배포처럼 여러 단계가 이어지는 작업, Lumen 응답 대기와 스트리밍, 토폴로지의 네트워크 연결, Object Storage 업로드·다운로드에서 지금 무엇이 진행되고 있는지 시각적으로 따라가기 어렵다. 지역 keyframe이 컴포넌트마다 중복되고 일부 막대는 layout 폭을 직접 애니메이션해 motion 계약과도 어긋난다.

## What Changes

- `layout.css`·`tokens.ts`·`DESIGN.md`에 공유 motion vocabulary를 추가한다: 회전·shimmer·stagger duration, emphasized·overshoot easing, 진입·draw·flow·sweep keyframe과 utility class. Reduced-motion 계약을 새 token까지 확장한다.
- 재사용 primitive를 추가한다: 결정/비결정 `ProgressTrack`, 작업 단계 목록 `StepProgress`, 아이콘 단계 그래픽 `ProvisionPipeline`, 대기·스트리밍·전송 표시 `ActivityIndicator`, count-up `AnimatedNumber`. 모든 primitive는 실제 상태 값에만 반응하고 상태를 문구·속성과 함께 전달한다.
- 우선 표면에 motion graphic을 적용한다:
  - VM 생성 wizard 단계 전환과 배포 진행, 같은 형식의 Drover 클러스터 생성/삭제·클러스터·이미지 내보내기·레이어 빌드 진행.
  - Lumen 응답 대기·추론·도구 실행·스트리밍 caret·새 메시지 진입, 이미지·오디오 생성 대기.
  - 토폴로지 lane/canvas의 연결 draw-in, 노드 진입, 카메라 이동, 네트워크 상세·대시보드 미니 토폴로지.
  - Object Storage와 이미지 업로드 dock, drop overlay, 다운로드 준비 상태.
- 모든 콘솔 페이지에 공통 motion을 적용한다: route 진입 fade, skeleton shimmer, table·empty state·alert 진입, modal pop, toast 진입/정렬, tab 선택 indicator, 사용량·통계 막대와 수치.

## Capabilities

### New Capabilities

- 공유 motion primitive와 utility class.

### Modified Capabilities

- 진행·대기·전송·토폴로지 표면과 공통 UI primitive의 시각 피드백. API·상태 모델·권한·데이터 흐름은 변경하지 않는다.

## Impact

Frontend `layout.css`, `tokens.ts`, `utils/motion.ts`, `components/ui/*`와 위 기능 컴포넌트를 수정한다. 애니메이션 런타임 의존성은 추가하지 않는다. Reduced-motion에서는 모든 반복·진입 motion이 정지 상태로 수렴하고, 상태는 문구와 ARIA 속성으로 계속 전달된다. Backend·배포·설정 변경은 없다.
