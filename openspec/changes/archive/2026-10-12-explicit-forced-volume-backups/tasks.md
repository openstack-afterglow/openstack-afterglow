## Implementation Tasks

- [x] Add explicit force to the manual backup API and native Cinder adapter; reject owned in-use volumes without force and retain ownership, cache and existing activity metadata.
- [x] Add localized warning and initially unchecked force acknowledgement to both manual creation dialogs; gate submit and reset consent on source changes/reopen while keeping available-volume creation unforced.
- [x] Add focused consent/state/ownership regression coverage without mock forwarding or wording-only tests; retain the automatic backup force policy.
- [x] Exercise the current route and real SDK over isolated HTTP and both real browser dialogs across locales, themes and responsive cutovers; distinguish synthetic providers from production acceptance.
- [x] Update API, public user/design/architecture guidance and changelog with actual verification, limits and consistency risk; archive the completed change.
- [x] Clarify all four warnings and API guidance that force itself does not guarantee crash-consistency or recovery; exercise the final wording in the 112-condition UI matrix, both native submissions and the short viewport.
