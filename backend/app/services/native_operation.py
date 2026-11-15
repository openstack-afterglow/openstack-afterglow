"""Explicit, short-lived native client and read ownership for one auth operation.

No state is shared between requests. Callers must invalidate before entering a
fresh mutation guard and after native writes; service credentials may be reused,
but authority observations must not cross those boundaries.
"""

from __future__ import annotations

import asyncio

from fastapi import HTTPException


class NativeReads(dict):
    """Keep identity-keyed memo owners alive until this read phase ends."""

    def __init__(self):
        super().__init__()
        self._owners = {}

    def retain(self, owner):
        self._owners[id(owner)] = owner
        return owner

    def clear(self):
        super().clear()
        self._owners.clear()


def memo_identity(reads, owner):
    """Return an identity key only while its memo keeps the owner alive."""
    if reads is not None:
        if isinstance(reads, NativeReads):
            reads.retain(owner)
        else:
            reads.setdefault(("native_operation", "identity_owners"), {})[id(owner)] = owner
    return id(owner)


class NativeOperation:
    def __init__(self):
        self._ks = None
        self.reads = NativeReads()
        self.subjects = {}
        self._sessions = []
        self.generation = 0

    @property
    def ks(self):
        if self._ks is None:
            from app.services import keystone

            self._ks = keystone._get_admin_ks_client()
            session = getattr(self._ks, "session", None)
            if session is not None:
                self.own_session(session)
        return self._ks

    def own_session(self, session):
        if not any(existing is session for existing in self._sessions):
            self._sessions.append(session)
        return session

    def read(self, key, fn, *args, **kwargs):
        if key not in self.reads:
            self.reads[key] = fn(*args, **kwargs)
        return self.reads[key]

    def get(self, kind, object_id):
        from app.services.identity_roles import _field

        manager = getattr(self.ks, kind)
        key = (memo_identity(self.reads, manager), object_id)
        if key not in self.reads:
            row = manager.get(object_id)
            if _field(row, "id") != object_id:
                raise HTTPException(503, "Native resource identity is unavailable")
            self.reads[key] = row
        return self.reads[key]

    def catalog(self):
        from app.services import identity_roles

        def load():
            return identity_roles._catalog(
                list(self.ks.roles.list()), list(self.ks.inference_rules.list_inference_roles())
            )

        return self.reads.retain(self.read(("catalog",), load))

    def invalidate(self):
        self.generation += 1
        self.reads.clear()
        self.subjects.clear()

    async def run(self, fn, *args, **kwargs):
        """Drain a cancelled SDK call before releasing its reads or sessions."""
        from app.services.identity_roles import _to_completion

        return await _to_completion(asyncio.to_thread(fn, *args, **kwargs))

    def close(self):
        failure = None
        try:
            for session in reversed(self._sessions):
                try:
                    session.session.close()
                except Exception as exc:
                    if failure is None:
                        failure = exc
        finally:
            self._sessions.clear()
            self._ks = None
            self.invalidate()
        if failure is not None:
            raise failure

    def __enter__(self):
        return self

    def __exit__(self, exc_type, *_):
        try:
            self.close()
        except Exception:
            if exc_type is None:
                raise

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, *_):
        try:
            await self.run(self.close)
        except Exception:
            if exc_type is None:
                raise
