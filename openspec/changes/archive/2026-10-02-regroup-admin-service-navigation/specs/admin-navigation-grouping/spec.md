## ADDED Requirements

### Requirement: Administrator navigation follows feature domains
The administrator sidebar, responsive drawer, and command palette SHALL organize destinations by their feature domain without a separate 서비스 category, preserving existing route URLs, authorization, individual service gates, beta gates, and tenant navigation.

#### Scenario: Container services have independent visibility
- **WHEN** k3s is enabled and Zun is disabled
- **THEN** the 컨테이너 group exposes Drover at `/admin/drover` and 클러스터 템플릿 at `/admin/drover/templates`, without exposing 전체 컨테이너
- **AND** directly opening either Drover route or a slash-delimited descendant expands 컨테이너

#### Scenario: Zun remains available without Drover
- **WHEN** Zun is enabled and k3s is disabled
- **THEN** 컨테이너 exposes 전체 컨테이너 at `/admin/containers` and hides Drover and 클러스터 템플릿

#### Scenario: Lumen administration is grouped together
- **WHEN** chat is enabled
- **THEN** the Lumen group exposes Lumen, 채팅 통계, 사용자 쿼터, 모델 설정, and 도구 설정 at their existing `/admin/chat` routes
- **AND** direct navigation expands Lumen and selects the matching exact destination
- **WHEN** chat is disabled
- **THEN** the Lumen group and its destinations are hidden

#### Scenario: Palimpsest is a direct destination
- **WHEN** an administrator uses navigation at desktop or mobile width
- **THEN** Palimpsest is a standalone link to `/admin/libraries`, not a disclosure button
- **AND** `/admin/libraries` and slash-delimited descendants select that link

#### Scenario: Waygate belongs to Network without changing scope
- **WHEN** Waygate is enabled
- **THEN** administrator Waygate appears under 네트워크 at `/admin/waygate`
- **AND** tenant Waygate remains at `/dashboard/network/waygate` with its existing project scope
- **WHEN** Waygate is disabled
- **THEN** its administrator destination is hidden without hiding other Network destinations

#### Scenario: Search and responsive navigation use the same classification
- **WHEN** an administrator searches the command palette
- **THEN** Drover and 클러스터 템플릿 results are classified as 컨테이너, all five Lumen destinations as Lumen, Palimpsest as Palimpsest, and administrator Waygate as 네트워크
- **AND** existing service visibility gates still apply
- **WHEN** a destination is selected from the mobile drawer
- **THEN** the drawer closes and the matching destination becomes selected

#### Scenario: Similar route names do not activate groups
- **WHEN** the path is `/admin/droverish`, `/admin/chatty`, `/admin/libraries-old`, or `/admin/waygate-extra`
- **THEN** none of the corresponding feature sections is active
