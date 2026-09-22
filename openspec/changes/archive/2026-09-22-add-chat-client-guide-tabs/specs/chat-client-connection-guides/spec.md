## ADDED Requirements

### Requirement: Selectable client connection guides
The chat API-key settings surface SHALL present separate selectors for Codex, Claude Code, OpenAI, and Claude and SHALL display Codex as the initial selection.

#### Scenario: Initial guide selection
- **WHEN** valid Lumen connection discovery data is available
- **THEN** the Codex selector is selected and only the Codex connection document is displayed

#### Scenario: Switch client guide
- **WHEN** the user selects Claude Code, OpenAI, or Claude
- **THEN** the previous document is replaced by the selected client's document without reloading connection discovery

### Requirement: Client-specific setup documents
Each client document MUST include its relevant setup explanation, validated discovered endpoint, complete configuration or code template, and a copy action whose payload matches the visible template.

#### Scenario: Codex document
- **WHEN** Codex is selected
- **THEN** the document explains `~/.codex/config.toml`, uses the discovered Codex Responses base URL, and offers the complete configuration for copying

#### Scenario: Claude Code document
- **WHEN** Claude Code is selected
- **THEN** the document explains the required Anthropic environment variables, uses the discovered Anthropic base URL, and offers the complete launch command for copying

#### Scenario: OpenAI document
- **WHEN** OpenAI is selected
- **THEN** the document identifies the Python package and displays a complete OpenAI SDK request using the discovered OpenAI SDK base URL

#### Scenario: Claude document
- **WHEN** Claude is selected
- **THEN** the document identifies the Anthropic Python package and displays a complete Anthropic SDK request using the discovered Anthropic SDK base URL

### Requirement: Accessible and responsive guide navigation
The client selectors MUST use tab semantics with linked tab panels, MUST remain keyboard operable, and MUST keep every selector and copy action reachable without a tab-row scrollbar or page-level horizontal overflow at supported mobile, tablet, and desktop widths.

#### Scenario: Keyboard navigation
- **WHEN** focus is in the client selector and the user navigates with Arrow, Home, or End keys and activates a tab
- **THEN** focus follows the shared tab navigation contract and the linked selected panel is displayed

#### Scenario: Narrow viewport
- **WHEN** the settings surface is rendered below 768px wide
- **THEN** all four selectors remain visible without scrolling the selector row, arranged in two columns when needed, and the selected document contains its own long code within the code region rather than overflowing the page

#### Scenario: Tabs fit on a wide viewport
- **WHEN** all four client selectors fit on one row
- **THEN** the row displays no horizontal or vertical scrollbar

### Requirement: Safe discovery failure handling
The settings surface MUST NOT display any client template until all required public SDK URLs pass existing validation, and MUST retain the explicit retry action without exposing malformed or credential-bearing URL values.

#### Scenario: Invalid discovery URL
- **WHEN** discovery returns a malformed or credential-bearing SDK URL
- **THEN** no client code template is rendered and the connection error with retry action is displayed

#### Scenario: Retry succeeds
- **WHEN** the user retries after a discovery failure and valid discovery data is returned
- **THEN** the Codex selector and its connection document become available while API-key management remains usable throughout
