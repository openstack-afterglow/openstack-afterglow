## Why
Switch–instance spacing remains too tall after prior fanout changes, and left-going parallel cables can cross due to universal reversed lane order. Obstacle routing can also choose unnecessary turns.

## What Changes
Compact automatic gutters to a single shared six-pixel fanout band. Order lanes according to cable horizontal travel while preserving per-network VM ingress and global switch endpoints. Prefer monotone direct routes when unobstructed and reject self-retracing detours. Preserve actual HUD clearance, NIC anchors, manual positions and traffic behavior.

## Impact
Frontend topology geometry and regression tests only; no API/schema/config/service deployment changes.
