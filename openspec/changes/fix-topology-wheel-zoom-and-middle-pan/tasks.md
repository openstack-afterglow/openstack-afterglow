# 작업

- [x] `canvasHelpers.ts` — `MOUSE_WHEEL_MIN_DELTA`(10) 추가, `isMouseWheel` 이 120 배수를
      확정 증거로만 쓰고 트랙패드 표식이 없으면 마우스로 보도록 변경
- [x] `TopologyCanvas.svelte` — `Gesture.panOnly` 추가, `onDown` 에서 `button === 1` 을
      이동 전용 경로로 보내고(노드·존·엣지·연결 핸들 해석 건너뜀) `onEnd` 에서 선택 판정 차단
- [x] `TopologyCanvas.svelte` — `mousedown`·`auxclick` 기본 동작 차단(자동 스크롤 위젯·가운데 클릭)
      과 정리(cleanup) 등록
- [x] 캔버스 하단 도움말 문구에 휠 버튼 이동 추가
- [x] `wheelIntent.test.ts` — 뒤집힌 계약 갱신(고해상도 휠·`wheelDeltaY` 없음은 이제 확대),
      한 자릿수 델타는 트랙패드, `MOUSE_WHEEL_MIN_DELTA` 경계 양쪽 단정
- [x] `TopologyCanvas.test.ts` — `firePointer` 에 `button` 추가, 휠 버튼 드래그가 노드를 잡지
      않고 이동만 하는지 + 움직이지 않고 떼면 선택이 안 바뀌는지 테스트 2건
- [x] `TopologyCanvas.test.ts` — 기존 누적 테스트가 `{deltaY:120}` 을 트랙패드로 가정하고
      있었으므로 가로 성분을 실어 장치 판정이 아닌 **누적**을 보게 고침
- [x] `ARCHITECTURE.md` — 휠 제스처 계약 갱신 + 휠 버튼 이동 규칙 추가
- [x] `CHANGELOG.md` — `[Unreleased] › Fixed` 항목 추가

## 검증

- [x] `npm run test:target -- frontend:src/lib/components/topology` — 12 파일 **207** 테스트 통과
- [x] `svelte-check` — 0 errors / 0 warnings
- [x] 실렌더 검증(휠 4개 프로파일) — 고해상도 휠(`deltaY -53`/`wheelDeltaY 64`) **확대됨**
      (k 0.607 → 0.657), `wheelDeltaY` 없는 120 델타 **축소됨**, 트랙패드(가로 성분) 배율 불변 +
      (-40, -120) 이동, 소수점 4.5 배율 불변
- [x] 실렌더 검증(휠 버튼) — 노드 카드 위에서 눌러도 뷰만 (70, 45) 이동, 배율 불변,
      노드 제자리, 수동 배치 핀 없음, 움직이지 않고 떼면 선택 불변
- [x] 앱 콘솔 오류 0건(백엔드 미기동 CORS 경고만 기존대로)
- [ ] `npm run test:gate` 통과 후 커밋

## 남은 가정

`MOUSE_WHEEL_MIN_DELTA` 10px 는 사용자의 실제 장치를 관찰하지 못한 상태의 추정이다. 여전히
휠로 확대가 안 되면 이 상수를 낮추고(예: 4), 반대로 트랙패드가 확대되면 올린다.
