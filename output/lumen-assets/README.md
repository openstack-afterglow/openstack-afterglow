# Lumen character state asset kit

Open `index.html` directly. HTML/CSS/JavaScript only; no framework, request, provider call, microphone or media playback. This is a reviewable asset specification, not an application patch. All26 states are manually selectable; only pending states animate. Settled error/blocked/ready art stays still. Percentages and fabricated task timing are absent. The audio pattern is symbolic, not a measured waveform.

## Files and usage

- `index.html`: four interactive asset cards and compact action symbols.
- `assets.css`: isolated Afterglow warm colors, responsive layout, status colors and typography.
- `assets.js`: text artwork, state catalogue, shared160ms animation step and event cleanup.
- `preview.png`, `preview-states.png`, `preview-mobile.png`: inspected renders.

`window.lumenAssets.setState('image', 'failed')` switches an example. `window.lumenAssets.states` contains the full state catalogue. Call `window.lumenAssets.destroy()` before removing the page; all DOM nodes belong to this single standalone instance. A future Svelte implementation should use component props/lifecycle, semantic theme tokens and existing localization. The catalogue's Korean copy is reference copy, not a nine-locale application translation.

## State map

|Family|State keys|
|---|---|
|chat|waiting, thinking, sending, blocked, ready, failed|
|image|queued, generating, downloading, decoding, ready, failed, canceled|
|audio|uploading, synthesizing, transcribing, buffering, ready, failed|
|realtime|permission, session, socket, device, waiting, ready, failed|

## Application adapter requirements

- Chat: preserve actual streaming, stop and tool-approval behavior. A permission block is not a submitted approval request.
- Images: generation completion does not mean preview-ready. Track download and native image decode separately; a failed cell stops its loader and owns retry.
- Audio: distinguish upload, synthesis/transcription and native media buffering/ready/error. Retain actual media controls and content.
- Realtime: keep connection pending through session creation, socket handshake and AudioWorklet/device readiness. Complete only at actual readiness; do not fabricate those transitions with timers.
- Status text remains the accessible source of truth. Decorative text is aria-hidden; actual state changes use a polite status region. Error uses both text and a symbol, not color alone.

## Verification — 2026-11-01

JS syntax passed. All26 state keys were switched in isolated Chromium and checked against their labels/kinds. Width320/768/1440 had no page overflow. Image error exposes retry; blocked differs from pending; device setup remains a pending example. Pause/resume stability/change checked. Desktop, alternate settled states and mobile screenshots inspected. Browser console was cleared before the final page check: no new errors. Earlier browser-buffer errors were from a prior application preview and are not attributed to this file-only page. Independent source review approved; mobile selector sizing refined and checked.

Native OS reduced-motion changes, actual200%browser zoom, other browsers and live provider/media behavior are unverified. This kit changes no application behavior. It demonstrates the desired transitions; the actual bugs in docs/lumen-loading-audit.md still need an application patch.
