## ADDED Requirements

### Requirement: Contextual actual-console screenshots
The public guides SHALL include actual console captures beside the sections or steps they explain using typed static screenshot metadata and local public image assets. Each image SHALL have meaningful alternative text, a caption, intrinsic dimensions and an accessible original-image link. The implementation SHALL preserve existing public reading, service gates, executable commands and operational authorization without adding a documentation API or runtime. Screen capture work SHALL record observed visual problems and their conditions separately from unrelated product fixes.

#### Scenario: Read a supported service procedure
- **WHEN** a reader follows a guide with a screenshot attached to a section or step
- **THEN** its real console image appears next to the relevant instructions rather than in a detached gallery
- **AND** the caption distinguishes pre-submit forms, current empty/denied/beta-gated states and existing-resource configurations from successful provisioning or data-plane execution

#### Scenario: Read the same screenshot in another language
- **WHEN** a reader selects Korean, English, Japanese or Simplified Chinese documentation
- **THEN** screenshot alternative text, captions, original-image actions and the Korean-console/redaction notice use the selected documentation language
- **AND** source paths and intrinsic dimensions are preserved across translations
- **AND** screenshot alternative text and captions are discoverable by the existing selected-language search

#### Scenario: Inspect a screenshot on a narrow screen
- **WHEN** the article is read on mobile, tablet or desktop in either theme
- **THEN** the entire image scales within its reading column without cropping or page-level horizontal overflow
- **AND** the original-image action provides a visible keyboard focus and a minimum 44px target
- **AND** activating it opens the same sanitized image in a separate tab without exposing the opener

#### Scenario: Publish an authenticated console capture
- **WHEN** a capture from the authenticated console is added as a public static asset
- **THEN** actual credentials, personal names, unnecessary resource identifiers, internal addresses and private conversation content are absent from the published image pixels
- **AND** redaction does not depend on reader-side CSS or an authenticated image endpoint
- **AND** capture preparation does not issue/revoke keys, reveal secret payloads, create/delete cloud resources or make paid provider calls merely for illustration

#### Scenario: Encounter a visual problem during capture
- **WHEN** an actual console surface has a visual or usability problem during documentation capture
- **THEN** a durable review records the affected route, observed conditions, impact, safe evidence and unresolved status
- **AND** intended permission gates and real empty states are distinguished from visual defects without claiming unobserved root causes or fixing unrelated service behavior
