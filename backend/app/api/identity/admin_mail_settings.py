"""Fresh administrator-only transport settings and saved-configuration diagnostics."""

import asyncio
import imaplib
import re
import socket
import ssl
import threading
import time
from email.parser import BytesHeaderParser
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from app.api.deps import get_token_info, require_admin
from app.services import email_service, identity_roles, mail_settings


class PrivateRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()

        async def handle(request):
            try:
                response = await original(request)
            except HTTPException as exc:
                response = JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers)
            _private(response)
            return response

        return handle


router = APIRouter(dependencies=[Depends(require_admin)], route_class=PrivateRoute)


def _private(response):
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Pragma"] = "no-cache"


async def _body(request):
    try:
        # Transport forms contain only bounded strings; do not let validation echo secrets.
        raw = await request.body()
        if len(raw) > 32768:
            raise ValueError
        body = await request.json()
        if not isinstance(body, dict):
            raise ValueError
        return body
    except Exception:
        raise HTTPException(422, "mail_settings_invalid") from None


@router.get("/email/settings")
async def get_settings(response: Response):
    _private(response)
    return mail_settings.public_settings(await mail_settings.effective_settings())


@router.put("/email/settings")
async def put_settings(request: Request, response: Response, token_info: dict = Depends(get_token_info)):
    _private(response)
    return await mail_settings.save_settings(await _body(request), user_id=str(token_info.get("user_id") or ""))


@router.delete("/email/settings")
async def reset_settings(request: Request, response: Response, token_info: dict = Depends(get_token_info)):
    _private(response)
    revision = request.query_params.get("revision", "")
    if not re.fullmatch(r"[0-9]{1,16}", revision):
        raise HTTPException(422, "mail_settings_invalid")
    return await mail_settings.save_settings(
        revision=int(revision), reset=True, user_id=str(token_info.get("user_id") or "")
    )


class _IMAPControl:
    """Own an in-flight socket across the API task and its drained worker."""

    def __init__(self, timeout):
        self.deadline = time.monotonic() + timeout
        self.cancelled = threading.Event()
        self.lock = threading.Lock()
        self.sock = None

    def remaining(self):
        remaining = self.deadline - time.monotonic()
        if self.cancelled.is_set() or remaining <= 0:
            raise TimeoutError
        return remaining

    def bind(self, sock):
        with self.lock:
            self.sock = sock
            cancelled = self.cancelled.is_set()
        if cancelled:
            self.close()
            raise TimeoutError

    def close(self):
        self.cancelled.set()
        with self.lock:
            sock = self.sock
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass


class _IMAPBounds:
    """Bound literal allocation, aggregate response bytes and every socket read."""

    def _budget(self):
        self.sock.settimeout(self._mail_control.remaining())

    def _received(self, data):
        self._mail_control.remaining()
        self._mail_bytes += len(data)
        if self._mail_bytes > 262144:
            raise ValueError("imap_response_bounds")
        return data

    def read(self, size):
        if not 0 <= size <= 16384:
            raise ValueError("imap_header_bounds")
        chunks = []
        while size:
            self._budget()
            chunk = self._received(self.file.read1(min(size, 4096)))
            if not chunk:
                break
            chunks.append(chunk)
            size -= len(chunk)
        return b"".join(chunks)

    def readline(self):
        line = bytearray()
        while len(line) <= 65536:
            self._budget()
            chunk = self._received(self.file.read(1))
            line.extend(chunk)
            if not chunk or chunk == b"\n":
                return bytes(line)
        raise ValueError("imap_response_bounds")

    def send(self, data):
        self._budget()
        return super().send(data)


def _imap_operation(config, *, message_id=None, control=None):
    """Only EXAMINE, SEARCH and PEEK header fetches; never bodies or seen flags."""
    control = control if control is not None else _IMAPControl(config.timeout_seconds)
    client = None

    def budget():
        remaining = control.remaining()
        if client is not None and client.sock is not None:
            client.sock.settimeout(remaining)
        return remaining

    try:
        context = ssl.create_default_context()
        transport = imaplib.IMAP4_SSL if config.security == "tls" else imaplib.IMAP4

        class Client(_IMAPBounds, transport):
            def __init__(self, *args, **kwargs):
                self._mail_control = control
                self._mail_bytes = 0
                super().__init__(*args, **kwargs)

            def _create_socket(self, timeout):
                raw = socket.create_connection((self.host, self.port), timeout=control.remaining())
                control.bind(raw)
                if config.security != "tls":
                    return raw
                secure = context.wrap_socket(raw, server_hostname=self.host, do_handshake_on_connect=False)
                control.bind(secure)
                secure.settimeout(control.remaining())
                secure.do_handshake()
                control.remaining()
                return secure

        if config.security == "tls":
            client = Client(config.host, config.port, ssl_context=context, timeout=budget())
        else:
            client = Client(config.host, config.port, timeout=budget())
            budget()

            class StartTLSContext:
                def wrap_socket(self, raw, **kwargs):
                    secure = context.wrap_socket(raw, do_handshake_on_connect=False, **kwargs)
                    control.bind(secure)
                    secure.settimeout(control.remaining())
                    secure.do_handshake()
                    control.remaining()
                    return secure

                @property
                def check_hostname(self):
                    return context.check_hostname

            client.starttls(ssl_context=StartTLSContext())
        if config.username:
            budget()
            client.login(config.username, config.password)
        budget()
        mailbox = '"' + config.mailbox.replace("\\", "\\\\").replace('"', '\\"') + '"'
        status, _ = client.select(mailbox, readonly=True)
        if status != "OK":
            return {"status": "failed", "code": "imap_mailbox_unavailable"}
        if message_id is None:
            return {"status": "ok"}
        budget()
        status, data = client.uid("SEARCH", None, "HEADER", "Message-ID", '"' + message_id + '"')
        if status != "OK" or not data or not isinstance(data[0], bytes) or len(data[0]) > 65536:
            return {"status": "failed", "code": "imap_search_failed"}
        ids = data[0].split()
        if len(ids) > 20 or any(not item.isdigit() for item in ids):
            return {"status": "failed", "code": "imap_search_bounds"}
        for uid in ids:
            budget()
            status, headers = client.uid("FETCH", uid, "(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID)])")
            if status != "OK":
                return {"status": "failed", "code": "imap_search_failed"}
            for part in headers or []:
                if isinstance(part, tuple) and isinstance(part[1], bytes):
                    if len(part[1]) > 16384:
                        return {"status": "failed", "code": "imap_header_bounds"}
                    values = BytesHeaderParser().parsebytes(part[1]).get_all("Message-ID", [])
                    if len(values) == 1 and str(values[0]).strip() == message_id:
                        return {"status": "confirmed"}
        return {"status": "not_found"}
    except Exception:
        return {"status": "failed", "code": "imap_connection_failed"}
    finally:
        control.close()
        if client is not None:
            # Do not CLOSE (can expunge). Shut down the read-only connection locally.
            try:
                client.shutdown()
            except Exception:
                pass


async def _imap_check(config, *, message_id=None):
    if not config.enabled:
        return {"status": "disabled"}
    if not config.host:
        return {"status": "failed", "code": "imap_connection_failed"}
    control = _IMAPControl(config.timeout_seconds)
    operation = asyncio.create_task(asyncio.to_thread(_imap_operation, config, message_id=message_id, control=control))
    try:
        async with asyncio.timeout(config.timeout_seconds):
            return await asyncio.shield(operation)
    except TimeoutError:
        control.close()
        await identity_roles._to_completion(operation)
        return {"status": "failed", "code": "imap_timeout"}
    except asyncio.CancelledError:
        control.close()
        await identity_roles._to_completion(operation)
        raise


async def _smtp_check(config):
    if not config.enabled:
        return {"status": "disabled"}
    if not config.host:
        return {"status": "failed", "code": "smtp_connection_failed"}
    client = None
    try:
        client = email_service.smtp_client(config)
        async with asyncio.timeout(config.timeout_seconds):
            await client.connect()
            await client.noop()
        return {"status": "ok"}
    except Exception:
        return {"status": "failed", "code": "smtp_connection_failed"}
    finally:
        if client is not None:
            client.close()


@router.post("/email/connection-check")
async def connection_check(request: Request, response: Response):
    _private(response)
    if await _body(request):
        raise HTTPException(422, "mail_settings_invalid")
    settings = await mail_settings.effective_settings()
    smtp, imap = await asyncio.gather(
        _smtp_check(settings.smtp),
        _imap_check(settings.imap),
    )
    return {"revision": settings.revision, "smtp": smtp, "imap": imap}


@router.post("/email/receipt-check")
async def receipt_check(request: Request, response: Response):
    _private(response)
    body = await _body(request)
    try:
        if set(body) != {"delivery_id"}:
            raise ValueError
        delivery_id = str(UUID(body["delivery_id"]))
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(422, "mail_settings_invalid") from None
    from app.services import mail_delivery

    target = await mail_delivery.get_receipt_target(delivery_id)
    if not target or target.get("kind") != "test":
        raise HTTPException(404, "mail_test_delivery_not_found")
    if target.get("status") in {"pending", "failed", "cancelled"}:
        return {"status": "not_sent"}
    if target.get("status") not in {"accepted", "unknown"}:
        return {"status": "failed", "code": "mail_delivery_in_progress"}
    message_id = target.get("message_id")
    if not isinstance(message_id, str) or not re.fullmatch(r"<[A-Za-z0-9_.@+-]{1,240}>", message_id):
        return {"status": "failed", "code": "mail_message_id_invalid"}
    settings = await mail_settings.effective_settings()
    if not settings.imap.enabled:
        return {"status": "disabled"}
    return await _imap_check(settings.imap, message_id=message_id)
