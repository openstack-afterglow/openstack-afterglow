-- User-scoped history of GitHub identities verified for cloud-init SSH import.
-- Public email/name/profile URL and SSH key material are intentionally not persisted.

CREATE TABLE IF NOT EXISTS vm_github_ssh_users (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL,
    github_user_id BIGINT NOT NULL,
    github_login VARCHAR(39) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    verified_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_vm_github_ssh_user_identity (user_id, github_user_id),
    KEY idx_vm_github_ssh_users_user_verified (user_id, verified_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
