## Why

The Cloud Shell implementation is complete and passed focused, image, browser, and repository gates, but its real Zun/Cinder lifecycle remains unverified because the current environment has the feature disabled. The existing opt-in live test is also too destructive: if run with an ordinary user that already has a workspace, its finalizer can delete that persistent home.

## What Changes

- Require an explicit destructive-test confirmation and expected disposable test identity before the live Cloud Shell scenario can mutate resources.
- Refuse to start when the selected identity already has an active session or persistent workspace; only resources created after that clean baseline may be removed by the test.
- Probe the reachable OpenStack environment without mutation and report missing service-project, network, security-group, image, credential, or feature-enable prerequisites precisely.
- Run the full live lifecycle only when every safe prerequisite is available; otherwise retain an explicit evidence-backed verification gap.
- Make terminal readiness reactive after the async xterm import, and preserve the same xterm instance while the dock is minimized so input and scrollback remain live.
- Update deployment/testing documentation and architecture review evidence to reflect the strengthened smoke contract and observed environment state.

## Capabilities

### New Capabilities

- Destructively safe, explicitly confirmed Cloud Shell live smoke execution for a disposable integration identity.

### Modified Capabilities

- Cloud Shell verification now distinguishes implementation success from real-environment readiness and cannot adopt or delete a pre-existing user workspace.

## Impact

- Affects `backend/tests/integration/test_cloud_shell.py`, its focused regression coverage, the Cloud Shell terminal/dock lifecycle, live deployment documentation, and architecture verification text.
- Production backend contracts remain unchanged; the frontend now keeps its terminal mounted during minimization and enables stdin when provisioning reaches `ready`.
- Live execution may remain blocked until operators provide an enabled Cloud Shell deployment, published immutable image, dedicated service-project resources, Redis, and disposable user credentials.
