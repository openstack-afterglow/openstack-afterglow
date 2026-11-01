## MODIFIED Requirements

### Requirement: Landing service sections explain themselves visually

Each landing service section SHALL show a large, product-like scene with icons, localized labels and illustrative values that reads from inputs to the resulting research resource, rather than decorative character art. The scene SHALL keep a localized accessible name, play its motion once when visible, end in a completed state, and present that complete static frame under reduced motion.

#### Scenario: Visitor scrolls to a service section
- **WHEN** a service section scrolls into view
- **THEN** its stages appear in order with their resources and states, and the motion settles on the completed scene
