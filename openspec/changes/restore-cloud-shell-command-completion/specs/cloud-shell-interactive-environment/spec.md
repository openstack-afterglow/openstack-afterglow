## ADDED Requirements

### Requirement: Interactive Bash provides installed command completion independently of the home skeleton

The Cloud Shell workload SHALL initialize normal Bash programmable completion and the installed OpenStack command, subcommand and option completion in interactive login and nested interactive non-login Bash. Initialization SHALL work with an empty persistent home and SHALL NOT overwrite user dotfiles or custom aliases. Completion initialization SHALL NOT make cloud-resource requests. Noninteractive shells SHALL remain silent.

#### Scenario: Empty persistent home
- **WHEN** a user opens a shell on an empty mounted persistent home
- **THEN** TAB completes installed OpenStack commands, subcommands and options and normal Bash file paths
- **AND** a nested interactive Bash provides the same completion without requiring a copied .bashrc

#### Scenario: Existing customized home
- **WHEN** a user reconnects with existing shell dotfiles or a custom ll alias
- **THEN** image initialization preserves those files and customizations
- **AND** the image does not emit startup banners into noninteractive commands

### Requirement: Shell help is discoverable offline without increasing authority

The workload SHALL provide an offline cloud-shell-help entry point explaining completion and how to obtain command descriptions and option usage from installed CLI help. Shell convenience features SHALL preserve the scoped-token, private tmpfs and non-root bootstrap boundaries and SHALL NOT grant additional native permissions.

#### Scenario: Discovering CLI usage
- **WHEN** a user invokes cloud-shell-help or installed OpenStack command help
- **THEN** the shell provides usage guidance without contacting a cloud
- **AND** protected native commands still require the user's actual current-project authority
