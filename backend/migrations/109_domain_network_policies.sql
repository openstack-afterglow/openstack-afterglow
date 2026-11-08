-- Per-domain network policy: CIDRs reserved for VPN tunnels.
-- Additive only: an absent row keeps the documented default ["10.8.0.0/24"]
-- (Waygate's default tunnel CIDR). Existing subnets are never rewritten; only new
-- subnet CIDRs and gateway changes are refused when they overlap a reserved range.
CREATE TABLE IF NOT EXISTS domain_network_policies (
    domain_id VARCHAR(64) NOT NULL,
    vpn_reserved_cidrs JSON NOT NULL,
    revision BIGINT NOT NULL DEFAULT 1,
    updated_by_user_id VARCHAR(64) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (domain_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
