# project-instance-list-controls Specification

## Purpose
TBD - created by archiving change finish-instance-list-controls. Update Purpose after archive.
## Requirements
### Requirement: Adequately wide desktop instance tables fit their shell
The project instance table SHALL fit a content shell at least64rem wide without horizontal overflow, while retaining every row action. Long IPv6 addresses and library names SHALL wrap within their assigned columns.

#### Scenario: Desktop list with long values
- **WHEN** the desktop content shell is at least64rem wide and rows have long addresses or library names
- **THEN** the table and its actions fit the shell and full values remain readable or available through existing details

### Requirement: Column sorting is available in both responsive forms
The list SHALL default to newest creation first and SHALL sort the complete filtered snapshot by name, status, image/specification, IP, library or strategy before pagination. Repeated activation SHALL cycle ascending, descending and default. Sort changes SHALL reset the page and clear selection without mutating the source. Compact cards SHALL expose equivalent labeled keyboard controls with44px touch targets; desktop columns SHALL expose aria-sort.

#### Scenario: Cycle a column
- **WHEN** a user activates the same column three times
- **THEN** ascending, descending and default newest-first orders are presented with accurate accessible state

#### Scenario: Switch responsive mode
- **WHEN** the viewport switches between compact cards and desktop table
- **THEN** the same sort and selection state remain and only one set of controls is mounted

### Requirement: Related instance controls stay adjacent
The tutorial SHALL be next to VM creation in the page header, and page size SHALL be grouped with previous/next controls in the footer at all viewport sizes. All new labels SHALL exist in the nine supported locales.

#### Scenario: Narrow viewport
- **WHEN** the footer or header cannot fit on one line
- **THEN** related controls wrap within the page without hiding actions or overflowing the document

