# Explicit retained build-worker journal disposition

The user selected `검증 후 원장 보관·차단 해제` after the actual old0.3.7 dedicated build worker was found repeatedly restarting with an immutable 26-byte `claim_pending` journal containing no job identity. Read-only preflight found5 complete builds,1 error build and0live leases. This is not proof of safe disposition at cutover time.

Only after all writers are fenced, protected SQL/CAS/scratch/key backups are restored and independently validated, and fresh native server job/lease plus exact worker scratch observations prove no incomplete or uncertain effect may Main archive the original journal with its hash and explicitly release the safety block. Preserve the original receipt and all unaccounted scratch. Never resend the unknown old claim, mark work terminal, clear/reset native leases, or delete resources to make readiness green. If any unresolved work appears, retain the barrier and report the exact blocker.
