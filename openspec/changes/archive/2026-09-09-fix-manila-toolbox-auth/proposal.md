# Manila toolbox authentication during Kolla deployment

The Manila preconditions invoke `openstack --os-cloud=kolla` without provisioning that cloud inside kolla_toolbox. Authentication errors are treated as absent shares, so deployment attempts creation and fails.

Install the pinned Manila CLI plugin and prepare a restricted cloud profile from Kolla's existing authentication variables before Manila prechecks. Fail explicitly when authenticated listing fails, and determine share existence from a successful listing rather than swallowing lookup failures. Stop promptly on terminal share errors. Use a bare CephX user ID accepted by Manila, and elevate the configuration project lookup to access Docker. Preserve existing shares and validate via the live deployment. Keep credentials out of task logs.

Scope: deployment role only; no application API changes. Work on dev. Completion requires Keystone health, authenticated Manila queries, and successful relevant deployment. Preserve pre-existing shares. The failed, unallocated share created by this task was cleaned up after recovering RabbitMQ with explicit user approval for cluster join; the recovery evidence is recorded in tasks.md.
