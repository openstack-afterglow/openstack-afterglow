# Proposal: Waygate VPN network, ownership and placement follow-ups

## Why
Live use of Waygate (Afterglow 1.32.11 / Waygate 0.3.7, project NLP) showed:
1. Server create and network attach report failure although the backend finished: provisioning writes take 25–33 s while the browser and the Afterglow→Waygate proxy gave up at 30 s.
2. The network attach dialog only offers tenant networks; provider/shared networks cannot be attached, and the attachment silently puts every subnet CIDR into client `AllowedIPs`, conflating the physical interface with routing.
3. A client owner must be typed as a raw Keystone user ID, which users do not know.
4. VPN gateway VMs live in the requester's project and can be deleted there outside Waygate; their size is fixed regardless of client count.
5. The WireGuard tunnel range (default `10.8.0.0/24`) can be reused by tenant/provider subnets, breaking routing.

## Decisions (user, 2026-11-08)
- Placement: option 2 first (keep VMs in the requester project, make them deletable only through Waygate); option 1 (central `waygate-service` project in the Default domain with cross-project network attach) is a later change.
- Provider networks may be attached by any member who can see the network (Neutron policy still decides).
- Attaching a network is only the physical interface; `AllowedIPs` routing is a separate per-attachment setting.
- Owner is optional at creation (empty by default), a user registers themself when needed, and the first config download by an eligible user registers them automatically.
- Tunnel/VPN ranges are reserved per domain; tenant and provider networks/subnets may not overlap them.
- Expected client count is requested at server create and selects the gateway flavor: up to 50 clients 1 vCPU/1 GiB, more 2 vCPU/2 GiB.

## Scope
- Afterglow: proxy write deadline (55 s) and client deadline (58 s) with reconcile-on-timeout UI (done); attach dialog lists provider networks, per-attachment AllowedIPs, optional owner with self-registration and claim-on-download, expected-client field; backend lock refusing deletion of Waygate gateway instances; per-domain reserved VPN ranges enforced for network/subnet create and update.
- Waygate (separate repo, new branch from 0.3.7, release 0.3.8): per-attachment `allowed_ips` with migration that preserves existing behavior, shared/external network attach, `expected_clients` → flavor tier.

## Non-goals
- Central `waygate-service` project placement (option 1), moving existing gateways, Nova lock enforcement against native-API deletion (documented limit), production deployment.
