## Decision
Keep node/side stable physical slot ordering. For VM TOP endpoints, derive lane count/offset independently per edge.netId. Switch lane ordering continues to span all incident edges on its side. Endpoint offsets no longer inherit the dominant bend offset. Auto-layout retains the switch total but reads each VM peer's fanout within the cable network only.

## Verification
Regression fails before the fix: adding4 other-network NICs changes original cable route. After the fix226 canvas tests pass, including stable original routes, unchanged auto-gap and same-switch peer influence. Real compiled CanvasEdgeLayer browser toggle proves existing routes unchanged across another-network0→4 and switch participation maintained when a same-switch peer is removed. Synthetic fixture; no live cloud or deployment acceptance.
