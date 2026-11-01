"""CPU adoption must make progress even when the SDK thread pool has one worker."""

import subprocess
import sys
import textwrap


def test_cpu_adoption_fence_does_not_deadlock_a_saturated_executor():
    script = textwrap.dedent(
        """
        import asyncio
        from concurrent.futures import ThreadPoolExecutor
        from types import SimpleNamespace
        from app.services import managed_flavors as service

        async def run():
            asyncio.get_running_loop().set_default_executor(ThreadPoolExecutor(max_workers=1))
            directory = {"p": {"domain_id": "d"}}
            snapshot = {"id": "manual"}
            native_specs = {}
            claim = {"snapshot": snapshot, "token": "a" * 48, "extra_specs": {}, "access": [], "pending": None}
            state = {"revision": 1}

            async def fence(*args):
                return None

            async def policy():
                return {"revision": 2}

            async def projects():
                # Model the real blocking Keystone directory reader.
                return await asyncio.to_thread(lambda: directory)

            async def save(*args):
                return None

            def native(*args):
                return snapshot, dict(native_specs), set()

            def create_specs(fid, specs):
                native_specs.update(specs)

            service._fence = fence
            service.flavor_automation_policy.load_policy = policy
            service._pool_projects = projects
            service._pool_projects_sync = lambda: directory
            service._save = save
            service._manual_native = native
            service.checkpoint_sync = lambda: None
            lease = SimpleNamespace(assert_owned=fence)
            compute = SimpleNamespace(create_flavor_extra_specs=create_specs)
            await service._manual_write(compute, lease, state, 2, directory, "manual", claim, {"kind": "marker"})
            assert native_specs[service.CPU_TOKEN] == service._cpu_marker(claim)
            assert claim["pending"] is None
            print("completed")

        asyncio.run(run())
        """
    )
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=8, check=False)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "completed"
