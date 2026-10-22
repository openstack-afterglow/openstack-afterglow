#!/usr/bin/env python3
"""Read native Zun in the exact dedicated project using toolbox's existing SDK.

No python-zunclient installation or stock toolbox image mutation is required.
Only a bounded container-list request is sent; resource bodies and credentials
are never printed.
"""
from __future__ import annotations

import json
import sys
from uuid import UUID


def check(project_id: str) -> None:
    UUID(project_id)
    import openstack.config
    from keystoneauth1.identity import v3
    from keystoneauth1.session import Session

    cloud = openstack.config.OpenStackConfig().get_one_cloud(cloud="kolla")
    auth = dict(cloud.config["auth"])
    for key in ("project_id", "project_name", "project_domain_id", "project_domain_name", "system_scope", "domain_id", "domain_name"):
        auth.pop(key, None)
    auth["project_id"] = project_id
    plugin = v3.Password(**auth, reauthenticate=False)
    session = Session(auth=plugin, verify=cloud.verify, cert=cloud.cert, timeout=10)
    try:
        if plugin.get_access(session).project_id != project_id:
            raise RuntimeError("Dedicated-project authentication returned a different scope")
        endpoint = session.get_endpoint(
            service_type="container", interface=cloud.get_interface(), region_name=cloud.get_region_name()
        )
        if not endpoint:
            raise RuntimeError("Native Zun endpoint is unavailable")
        response = session.get(
            endpoint.rstrip("/") + "/containers",
            params={"limit": 1},
            headers={"OpenStack-API-Version": "container 1.36"},
            redirect=False,
            raise_exc=False,
        )
        if response.status_code != 200:
            raise RuntimeError("Dedicated-project Zun list was rejected")
        body = response.json()
        if not isinstance(body, dict) or not isinstance(body.get("containers"), list):
            raise RuntimeError("Native Zun returned an invalid list")
    finally:
        session.session.close()


def main() -> int:
    try:
        if len(sys.argv) != 2:
            raise ValueError("Expected one dedicated project ID")
        check(sys.argv[1])
    except Exception:
        print("Dedicated Cloud Shell Zun authentication/list precheck failed", file=sys.stderr)
        return 1
    print(json.dumps({"project_id": sys.argv[1], "native_zun_list": "ready"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
