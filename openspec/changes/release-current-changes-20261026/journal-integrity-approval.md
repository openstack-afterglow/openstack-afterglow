# Approved journal integrity repair

The user selected **프레임 인덱스로 증분 검증** after actual native amd64 verification of Palimpsest `73667c8f4065215416e775f12cb0a6f578853044` found that unchanged tmpfs metadata could conceal same-length journal modifications before a non-tail output frame was returned.

Approved contract: retain compact trusted per-frame commitments, authenticate each requested frame before returning it, preserve reads proportional to requested/new frames, accept memory proportional to record count, and state explicitly that cursor-only access does not audit unrequested historical payloads. Startup performs complete streaming verification. No timestamp delay, retry, integrity bypass or silent full-prefix reread.

Prepare and qualify a new immutable Palimpsest patch release; preserve published `v0.3.8`. Formal `v0.3.8` Release run `40330305289` attempt 2 succeeded, but does not override the additional native correctness failure. Required KVM proof remains policy-skipped, not performed.

This OCI supervisor journal repair is separate from the pre-existing dedicated build worker's anonymous `claim_pending` disposition. The latter still requires all-writer fencing, protected paired backup/restore and fresh server/jobs/leases/scratch reconciliation before original-journal archive and explicit block release, without resubmission.

Production services, schema, active configuration and operator packages remain unchanged at this approval.
