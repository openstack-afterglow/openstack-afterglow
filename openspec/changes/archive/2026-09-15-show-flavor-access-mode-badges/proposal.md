## Why

The administrator Flavor list shows whether each Flavor is Public or Private, but a Private GPU Flavor's access policy is only visible after opening its management panel. The project GPU quota table also renders only aliases already present in that project's effective quota or usage response, so projects such as DMSLAB cannot configure newer cluster GPU types even though those types exist in Flavors or Placement. Administrators need both policy and quota-type visibility before changing access.

## What Changes

- Show a compact access-policy badge beside the existing Public/Private indicator for Private GPU Flavors.
- Label `afterglow:access_mode=gpu_quota` as `Quota 연동` and the absent/`manual` fallback as `수동`.
- Reuse the shared `Pill` primitive and existing semantic tones; do not introduce a new API, color, or policy state.
- Keep the indicator hidden for Public Flavors and non-GPU Flavors because quota-managed access is not applicable there.
- Merge the cluster-wide GPU alias catalog into every selected project's quota rows, using the effective default or `0` for aliases with no project status row.
- Clarify that the displayed Flavor Access operations are a dry-run preview; Nova access changes occur only when the unified Compute policy applies reconciliation.

## Capabilities

### New Capabilities

- Administrators can identify Private GPU Flavor access policy directly from the Flavor list.
- Administrators can configure any cluster-discovered GPU type for any project, even before that project has a stored quota or current usage.

### Modified Capabilities

- The existing administrator Flavor table presents access-policy metadata already returned in each Flavor's `extra_specs`.
- The administrator quota table combines cluster aliases, global defaults, and project effective status instead of treating the project status response as the complete catalog.

## Impact

Frontend presentation and controller changes in the administrator Flavor and quota surfaces, with focused component/controller coverage. Backend serialization, quota storage, and access-mode mutation behavior remain unchanged. The tables preserve their existing responsive behavior.
