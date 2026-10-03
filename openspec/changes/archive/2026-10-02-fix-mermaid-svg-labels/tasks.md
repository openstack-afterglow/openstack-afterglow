## Implementation and verification

- [x] Reproduce blank flowchart labels in real compiled Chromium using both the baseline 1.30.0 image and the dependency-patched image. Trace HTML-label foreignObject removal to the existing SVG-only sanitizer.
- [x] Select native SVG text labels without relaxing sanitizer or strict Mermaid security.
- [x] Canonical linux/arm64 and linux/amd64 frontend images built and ran. Chromium retained exact Markdown/Sanitized output SVG text labels, Markdown table, KaTeX and code while script/event/javascript URL content was rejected. Both architectures retained labels and overflow0 at390/767/768/1023/1024/1440px; settled390px labels measured visible at12px. Provider/identity APIs were synthetic, not operational acceptance.
- [x] Existing focused tests passed10 plus the sanitizer consumer1. Removed obsolete copied initialize-options/render-call assertions rather than re-pinning them. Final full gate: backend3523/frontend1896/contract141/DB functional28, Ruff/format530; frontend check2130files/0errors/0warnings and production build passed. Architecture/chat/security/changelog recorded the unchanged trust boundary. Accepted for archive before dev commit.
