# 클라우드 사이트 조사와 Afterglow 적용

## 조사 경계

지정된 9개 URL을 실제 Chrome에서 열고 1440×900 CSS px·DPR 1을 확인했다. 각 첫 화면과 아래 구간을 캡처하고 scroll·Google carousel·AWS hover를 실행했다. 회사의 인증·성능·고객 수·비용 주장은 회사가 게시한 문구이지 독립 검증 결과가 아니다. 로딩 시점·쿠키·개인화에 따라 hero 문구가 바뀔 수 있다. 선언된 CSS 시간과 실제 재생·전환 관측을 구분한다. 라이브러리는 DOM/배포 파일로 확인할 수 있는 범위만 기록하며 외형만으로 GSAP/Lottie를 추정하지 않는다.

## 사이트별 결과

| 사이트와 primary source | 소개·어필 구조 | 관측한 시각 효과와 구현 | Afterglow 적용 판단 |
|---|---|---|---|
| [NHN Cloud](https://www.nhncloud.com/kr) | 캠페인 hero, 기술/산업별 주요 솔루션, 바로 이용할 주요 서비스, 고객 사례. 시작하기/Console와 도입 문의를 분리한다. AI 인프라와 Private Cloud가 별도 진입점이다. | Nuxt asset, Swiper DOM·wrapper, card/image 중심의 넓은 구성. 대상 DOM의 inline style은 opacity+translateY(5px), 0.7s ease-out; nav 색상 feedback은 0.15s. 초기 getAnimations 빈 결과는 애니메이션 부재의 증거가 아니며 후속 hydration에서 실제 transition/Swiper markup을 확인했다. | 기술 제품과 기관별 도입 목적을 구분한다. 회사가 주장한 GPU 수·인증·순위는 복제하지 않는다. |
| [Google Cloud](https://cloud.google.com/?hl=ko) | “The new way to cloud”를 AI 활용·앱 배포·데이터 분석이라는 실제 과제로 풀고 무료 시작/영업 문의를 나눈다. 역할·제품 분류와 작업 영상으로 이어진다. | 실제 CSS animation은 fadeInFromBottom 500ms, scaleDown/slideInFromRight 1250ms, fadeIn 450ms와 stagger delay. 다음 버튼과 scroll을 실행했다. MultiPath WebM은 이번 관측에서 paused/currentTime 0으로 재생되지 않았다. | 짧은 첫 메시지 바로 아래 구체적인 서버·학습·채팅·Kubernetes를 명시한다. 스스로 이용하기와 구축 상담을 구분한다. |
| [AWS](https://aws.amazon.com/ko/) | 실제 렌더 hero는 “고유한 보안 요구 사항을 충족”. Raw HTML의 breadth-first hero와 다르므로 브라우저 결과를 현재 화면으로 기록한다. 뉴스→업종별 고객 결과→제품·인프라로 이어진다. | 뉴스 카드 AnimatedCTA `.rgic_02e87eb9` hover를 실제 실행했다. CSS grid column이 `0px 16px`→중간 `46.9688px 54.6875px`→`156.172px 16px`로 변했다. 진입 400ms, 복귀 250ms. 고객 carousel은 translate/scale wrapper 구조다. | 사용자의 업무 목적과 제품 카탈로그를 분리한다. 작동하는 서비스 가이드 링크와 명확한 CTA를 둔다. 인증·대형 고객 사례를 만들어내지 않는다. |
| [KakaoCloud](https://kakaocloud.com/) | 브랜드 hero→새 소식→서비스 분류→산업별 솔루션→고객 사례→교육·시작 가이드. VM·Transit Gateway·Kubeflow를 실제 제품명으로 안내한다. | Next asset와 실제 muted autoplay loop MP4를 확인했다. `video_home_top_bg_lg.mp4`는 readyState 4, paused false, currentTime이 관측 사이 증가했다. 브랜드 영상은 서비스 실행 증거가 아니다. | 이름만 나열하지 않고 사용자가 수행할 분석·학습·대화·배포로 설명한다. 반복 배경 영상은 추가하지 않는다. |
| [KakaoCloud 공공](https://kakaocloud-kr-gov.com/) | 데이터 보호/안정성으로 타깃을 먼저 선언하고 공공 도입 상담을 primary CTA로 둔다. 전용 인프라→AI stack→보안 인증→공공 사례를 구분한다. | 실제 muted autoplay loop `video_home_top_bg_gov_lg.mp4`, readyState 4와 진행하는 currentTime을 확인했다. 일반 사이트와 비슷한 영상 언어를 쓰지만 문구와 상담 목적이 공공에 맞춰 달라진다. | 연구자·교수·기관 운영자가 누구인지 먼저 명시한다. 기관 내부 소유 경계를 보여주되 CSAP/SLA/24시간 지원 등 확인되지 않은 약속은 넣지 않는다. |
| [LG CNS Cloud](https://www.lgcns.com/kr/service/modern-it-infra-on-cloud/cloud) | 직접 VM을 파는 storefront보다 컨설팅→전환·구축→현대화→AI/Data→운영 서비스 범위를 설명하고 도입 문의로 연결한다. | 사진/장문 설명/구간 navigation이 중심이다. 대상 viewport에서 active content animation은 관측하지 않았고 header에 `top 0.5s` transition을 확인했다. 무거운 canvas/hero video는 해당 URL에서 관측하지 않았다. | “클라우드를 사용”하는 것과 “기관의 클라우드를 구축”하는 일을 별도 선택으로 설명한다. 실제 제공 범위 밖의 migration·24/7 MSP 계약은 주장하지 않는다. |
| [KT Cloud](https://cloud.kt.com/) | 상품 선택과 컨설팅/영업·견적 문의가 병렬이다. Compute·GPU·Container·Hybrid/Private Cloud 및 구성 reference를 분리한다. 실제 hero는 자사 데이터센터와 cloud 연결을 설명한다. | Vue app/chunk-vendors 배포 파일, Swiper wrapper의 translate3d, 이전·다음·정지 controls를 확인했다. nav/product panel은 0.2–0.5s CSS transition. 초기 reader의 metadata-only 응답과 달리 브라우저에서는 본문이 렌더됐다. | 자원을 묶는 구성 그림과 프로젝트별 제공 방식을 사용한다. 자동 하이브리드 연결이나 외부 CSP 통합을 지원한다고 확대하지 않는다. |
| [Cloudflare](https://www.cloudflare.com/) | 하나의 플랫폼에서 앱·agent·workforce를 운영한다는 약속→Region: Earth 설명→고객/비교·가격·제품으로 이어진다. HTML hero와 회사의 `.md` alternate 표현도 구분했다. | 실제 canvas 1개, SVG/opacity entrances, waveform-scroll 20s, marquee 8s, ticker 80s 등을 관측했다. Hero MP4는 autoplay/loop/muted markup이지만 이번 sample은 readyState 0·currentTime 0으로 재생 확인이 없다. Source의 video loader는 reduced motion·Save-Data·network 조건 및 IntersectionObserver로 gated된다. | 복잡한 플랫폼을 연결 관계로 설명하는 아이디어와 reduced-motion/static safeguards만 채택한다. WebGL·반복 ticker·배경 영상은 필요하지 않다. |
| [DigitalOcean](https://www.digitalocean.com/) | 현재 “AI-Native Cloud” hero와 제품/solution menu, five-layer platform, 개발자 문서·직접 signup이 중심이다. GPU·Kubernetes·Core Cloud를 AI 서비스와 같은 stack 안에서 설명한다. | Next assets, 실제 30s CSS marquee와 1000ms slide-up을 getAnimations에서 확인했다. 도시/stack WebP 이미지가 실체이며 이 URL에서 canvas/video는 관측하지 않았다. Five layers는 아키텍처 분류이지 실험 기록을 저장하는 레이어 기능이 아니다. | 네 개의 지원 서비스를 한 플랫폼의 명확한 목록으로 소개한다. 타사의 구조 그림을 Palimpsest 재사용 기능처럼 광고하지 않는다. |

## 적용한 설계

- 첫 메시지: **연구에 필요한 클라우드. 기관에 맞는 구축까지.**
- 네 서비스: 연구용 클라우드 서버, GPU 기반 AI 학습, Lumen AI 채팅, Kubernetes 플랫폼.
- 두 경로: 제공 클라우드 이용은 기존 콘솔로, 온프레미스 구축은 기존 문의 email로 연결한다.
- 구성도: 서버·GPU / 스토리지 / 네트워크를 연구 클라우드로 묶고 프로젝트·역할·쿼터를 통해 연구실·수업·기관에 제공한다. 실제 배포 화면이 아닌 설명용 예시다.
- 미지원 홍보 제거: Palimpsest 레이어 기록·저장·포크·재사용 본문, hero 결과 단계, library 카드, 관련 meta/네 locale/전용 story·artwork. 스냅샷 스케줄 저장도 임의의 기능 약속이 되지 않게 체험에서 제거했다.
- 구현: 기존 Svelte 5, CSS Grid, `Button`/`ToggleGroup`/`UsageBar`, 공유 motion token과 `.motion-enter`, IntersectionObserver reveal. 새로운 animation dependency·WebGL·영상·scroll hijack는 없다. 모션은 선택/단계 전이를 설명하고 reduced motion에서는 즉시 읽을 수 있다.

## 증거

- 실제 9사이트 첫 화면: [contact sheet](evidence/cloud-reference-contact-sheet.png). 개별 hero/section/interaction PNG는 `~/.local/share/afterglow-proofs/research-cloud-landing-20261012-qxi2e2rq/`에 보존한다. NHN 초기 campaign modal 캡처와 dismiss 이후의 unobstructed 화면은 구분한다.
- Raw runtime: [9 URL 중 8곳의 첫 화면·scroll 기록](evidence/cloud-reference-live.json), [추가 hover/transition 기록](evidence/cloud-reference-interactions.json). Google은 별도 browser 결과와 hero/carousel/section PNG로 확인했다.
- 변경 전후 녹화는 같은 proof 디렉터리의 `afterglow-cloud-landing-before.mp4`와 `afterglow-cloud-landing-after.mp4`다. 둘 다 실제 1440×900·DPR 1·light·no-preference. FFprobe는 전 9.60s/288frames, 후 9.333s/280frames이며 `mpdecimate` changed frames는 95/74다. 실제 hero 단계 전이를 보여주는 영상이며 nominal 30fps나 서로 다른 디자인·단계 수를 성능 비교로 주장하지 않는다. 새 구축 선택은 아래 별도 녹화로 증명한다.
- Compiled preview의 4 locale × 2 theme × 8 width, 총 64조건: 320/390/767/768/1023/1024/1440/2560px. Cloud/on-premises 모두 horizontal overflow 0, 네 서비스·44px 선택과 정확한 목적지를 확인했다. [Compiled matrix](evidence/compiled-browser.json).
- Reduced motion 3시나리오 즉시 3/3 완료, keyboard Enter·focus 유지·Tab 문의 이동·skip link, 720×450·DPR 2 및 공개 가이드 3개 HTTP 200. [Keyboard/reduced proof](evidence/keyboard-reduced-browser.json), [전체 서비스·필터·제품 화면](evidence/surface-browser.json), [최종 adapter-node 자체 실행·obsolete artwork 404](evidence/adapter-node-browser.json).

추가 구축 선택 녹화는 proof 디렉터리의 `afterglow-cloud-landing-deployment-motion.mp4`다. FFprobe 4.733s/142frames와 `mpdecimate` changed frames 10으로 선택 전후 실제 변화는 확인했지만 frame-rate 성능을 주장하지 않는다. [실행한 검사와 한계](evidence/verification.json), [scoped architecture receipt](evidence/architecture.json)는 전체 gate·운영 acceptance와 분리한다.

로컬 preview의 public site-config는 `localhost:8000` 응답이 HTTP200이지만 이 preview origin의 Access-Control-Allow-Origin이 없어 브라우저에서 거부됐다. 화면은 기존 기본 config로 검증했고 CORS나 운영 설정을 변경하지 않았다. 운영의 custom config integration, 실제 GPU/VM provisioning·Lumen 유료 inference·Kubernetes 설치·기관 구축·운영 배포 완료의 증거가 아니다. 번역은 카탈로그·렌더 경계를 검증한 초안이며 원어민 검수 인증이 아니다.
