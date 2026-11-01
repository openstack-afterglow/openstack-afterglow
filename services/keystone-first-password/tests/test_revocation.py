from keystone import exception


def test_native_manager_revokes_existing_tokens_after_creation(native, subject, post):
    providers = native["providers"]
    # Issue a real native unscoped token for a synthetic no-password subject.
    # This is test setup via the actual token provider, not endpoint authority.
    token = providers.token_provider_api.issue_token(subject["id"], ["password"])
    providers.token_provider_api.validate_token(token.id)
    assert post(subject).status_code == 204
    try:
        providers.token_provider_api.validate_token(token.id)
    except exception.TokenNotFound:
        pass
    else:
        raise AssertionError("Native user-wide revocation was not preserved")
