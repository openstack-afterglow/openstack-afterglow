## ADDED Requirements

### Requirement: Landing service sections explain themselves visually

Each landing service section SHALL show a simple flow diagram of icons with localized text labels that reads from inputs to the resulting research resource, rather than decorative character art. The diagram SHALL keep a localized accessible name, play its motion once when visible, and present a complete static frame under reduced motion.

#### Scenario: Visitor scrolls to a service section
- **WHEN** a service section scrolls into view
- **THEN** its labeled stages appear in order, connected by arrows, and the motion settles to a complete static diagram
