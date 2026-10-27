# Approved Lumen Valkey Sentinel correction

The user selected **Sentinel 지원 후 정식 patch 배포** after actual native observations proved all six Lumen API/workers directly connected to `172.30.0.11:6379`, logical DB8, a Valkey replica whose current master is `172.30.0.13:6379`. The user explicitly clarified: **redis 대신에 valkey 로 대체했는데 거기에 맞게 확인 및 진행**.

Use the existing Valkey and Valkey Sentinel installation. Do not install a Redis server, replace/upgrade Valkey, create a master-only HAProxy route, or perform live failover to qualify this change. Add optional canonical Sentinel support to Lumen, preserve data authentication, separate Sentinel authentication, URI/TLS/socket options and close ownership, and qualify actual controlled Valkey failover before a new immutable patch release. `redis-py` remains a wire-compatible client, not evidence of a Redis server.

All rendered HAProxy configurations/effective mappings and node listeners were inspected; no existing stable master-only Redis/Valkey endpoint was found. Pinning only the current master was explicitly not selected.

Palimpsest's real Sentinel factory already resolves the master, but the old backup helper omitted its Sentinel fields and authentication/TLS options. Correct backup/fence routing from separately protected actual settings evidence without rewriting the original escrow. Do not describe the original incomplete settings extraction as complete routing proof.

Native Valkey state/configuration, production writers, SQL028 and the operator active environment remain unchanged at approval. Prior release and hot restoration evidence remain historical/exact-source-specific; cold recovery and rollout are still pending.
