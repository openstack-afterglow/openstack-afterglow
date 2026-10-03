## ADDED Requirements

### Requirement: Maintain readable Lumen composer controls in both themes
The Lumen composer MUST use existing semantic surface, ink, line, focus, and disabled tokens for the editor, placeholder, toolbar, attachment content, and send controls. Light mode MUST keep each interaction state legible without changing dark-mode behavior or adding a separate feature palette.

#### Scenario: Edit and focus a light-theme message
- **WHEN** a user enters the composer in light mode and focuses the editor
- **THEN** its text, placeholder, boundary, caret/focus treatment, and toolbar controls remain distinguishable from surrounding surfaces

#### Scenario: Attach content and disable sending
- **WHEN** attached content is visible while sending is disabled or in progress
- **THEN** attachment labels and controls remain readable and the disabled send action is visually distinct without being mistaken for available

#### Scenario: Switch appearance and viewport
- **WHEN** the user switches between light and dark themes at desktop or mobile width
- **THEN** composer content and primary actions remain reachable and dark-mode contrast is not degraded
