## Context

The completed source enables initial SSO local-password creation as well as reset. The administrator warning still says it only replaces a password. Existing receipt evidence is correctly synthetic but uses a hand-written protocol peer.

## Goals / Non-Goals

**Goals:** Accurate nine-locale administrator warning and generated-mail advice; independent SMTP/IMAP interoperability with verified certificates and exact header confirmation.

**Non-Goals:** No authority/API/schema/worker redesign, no all-project admin scan expansion, no permanent literal-copy or forwarding tests, no production or real mailbox traffic.

## Decisions

- Warn every administrator action conditionally: initialize if absent, otherwise replace; SSO native passwords can bypass IdP MFA and remain usable when the IdP disables the account. Do not infer absence from UI metadata. Keep mailbox exposure/immediate change advice. The generated-password email carries the same conditional risk notice.
- Keep existing native-state/owner/audit/no-replay behavior. Existing behavioral regressions and actual rendered nine-locale confirmation/error mapping validate the path without repinning exact translation text.
- Use pinned GreenMail standalone2.1.15 in a throwaway isolated Docker network with dummy users and a purpose-generated trusted TLS certificate. Exercise actual application connection/test/receipt endpoints over TCP with persisted settings/outbox, implicit TLS, wrong auth, not-found, substring collision rejection, header-only exact confirmation and unchanged seen state. GreenMail2.1.15 advertises no SMTP/IMAP STARTTLS (upstream issue135); validate safe rejection rather than falsely claim positive STARTTLS interoperability or weaken product TLS checks. Existing STARTTLS source/unit boundaries remain separate.

## Risks / Trade-offs

- GreenMail is independent protocol implementation but remains a sandboxed test mail server, not the operator's actual mailbox or provider acceptance.
- Preserve fail-closed TLS certificate validation; trust only the disposable certificate, never turn off verification.
- Existing opt-in bounded per-project scanner is intentionally unchanged; a system-wide inventory/token redesign is unrelated and has broader authority implications.
