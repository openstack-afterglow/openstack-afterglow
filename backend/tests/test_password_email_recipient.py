"""A credential destination must be exactly one canonical mailbox, not header syntax."""

import pytest

from tests.test_admin_password_reset import directory as directory
from tests.test_admin_password_reset import post

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize(
    "address",
    [
        "alice(comment)@example.test",
        "Alice <alice@example.test>",
        "alice@example.test,other@example.test",
        "alice@example.test (comment)",
    ],
)
async def test_ambiguous_smtp_mailbox_is_rejected_before_password_write(directory, address):
    directory.users["target"]["email"] = address
    response = await post(directory)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "admin_password_reset_email_unavailable"
    assert not directory.updates and not directory.mail
    assert directory.sessions == ["target-session"]
