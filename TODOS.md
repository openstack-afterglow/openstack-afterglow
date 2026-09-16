# TODOS — Deferred from §12.3 Autoplan Review
Generated: 2026-05-15

## 즉시 처리 불가 (§12.5 답변 선행 필요)

- [ ] **monitoring_scrape_cidr 확정** — Prometheus pod가 어느 CIDR에서 VM에 접근하는지
  (control plane management network? provider network?)
  → 확정 후 `afterglow.conf.example` + `backend/app/config.py` 기본값 업데이트

- [ ] **Kolla Ansible Prometheus/Grafana 재사용 여부** — §12.5 Q1
  → 재사용 시: K8s Prometheus configmap에 scrape job만 추가 (새 Prometheus 불필요)
  → 독립 운영 시: 현재 계획대로

## 후속 PR (§12.3 완성 후)

- [ ] **GPU 알림 규칙** — GPU 사용률 95% 초과 시 알림 (Prometheus alerting rules)
  → `deploy/k8s-template/monitoring/prometheus/alerting-rules.yaml` 신규

- [ ] **Option B 평가** — Option A 완성 후 다중테넌시 격리 요구 강도 재검토
  → 강한 격리 필요 시 per-project Prometheus (Option B) 또는 Grafana per-org 전환

- [ ] **SD endpoint public API 문서화** — `GET /api/sd/prometheus/targets`를
  파워유저(연구자)가 자체 Prometheus에 연결할 수 있도록 문서화
  → API 레퍼런스 페이지 또는 README 추가

- [ ] **Grafana org 기반 다중테넌시** — 현재 single-org + var-project_id 방식의
  보안 강화가 필요한 경우, Grafana org per-project 마이그레이션
  → 단, 이 경우 GF_AUTH_ANONYMOUS 비활성화 + per-org token 발급 필요

## 기술 부채

- [ ] `generate_k8s.py:render_grafana_deployment` — `cfg` 파라미터 미사용
  hardcoded `"admin"` password → `cfg.get("grafana_admin_password", "admin")` 로 수정
  또는 render_secret()으로 K8s Secret에 주입

## Kolla role wheel 후속

- [ ] **`*-kolla` wheel PyPI trusted publishing 전환** — 초기 GitHub Release direct URL
  배포가 Drover 파일럿과 Afterglow 4-wheel composition gate에서 안정화된 뒤,
  `afterglow-kolla`, `drover-kolla`, `lumen-kolla`, `palimpsest-kolla` 이름을 확보하고
  각 서비스 tag workflow에 PyPI trusted publishing과 provenance 검증을 추가한다.
  → 장점: `/etc/kolla/pyproject.toml`을 정적 PEP 508 URL 대신 일반 version constraint로 단순화
  → 비용/위험: 4개 레포의 package-name ownership, OIDC publisher, release rollback 정책을 함께 운영
  → 선행조건: Drover wheel clean-venv gate, container/wheel lockstep release, 4-wheel install/upgrade/uninstall isolation 통과
