# Extended auth page studies

## Why

The existing responsive auth gallery needs matching signup, email verification, recovery and MCP connection examples before application adoption.

## What Changes

Add six standalone page studies with22 explicit states, shared character scene/palette and local-only interactions. Split longer tasks into steps so small portrait/landscape viewports retain controls without clipping. Extend gallery, screenshots and the ZIP. No application authentication, email, token or permission operations are connected.

## Verification

All440 state/viewport combinations passed with no document overflow or out-of-viewport controls/content. All22 states also passed at568×320 in light mode. Primary step transitions, heading focus and MCP approval/denial examples passed. Independent source review approved. README documents native-device/zoom/locale gaps; application gates are outside the standalone scope.
