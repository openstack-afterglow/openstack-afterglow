/* SPDX-License-Identifier: GPL-2.0
 * Passive socket filter: return zero ALWAYS. No packet is copied to userspace.
 * Only fixed Ethernet/VLAN/IPv4/IPv6 headers are read; never L4 or payload.
 * LOCAL_NODE is the bounded node index compiled by the protected loader.
 */
#include <uapi/linux/bpf.h>
#include <uapi/linux/if_ether.h>
#include <uapi/linux/if_packet.h>

#if __BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__
#define FROM_BE16(value) __builtin_bswap16(value)
#define FROM_BE32(value) __builtin_bswap32(value)
#elif __BYTE_ORDER__ == __ORDER_BIG_ENDIAN__
#define FROM_BE16(value) (value)
#define FROM_BE32(value) (value)
#else
#error Unsupported byte order
#endif

struct address6 { unsigned char bytes[16]; };
struct flow_key { u32 source; u32 target; u32 ifindex; u32 direction; };
struct totals { u64 packets; u64 bytes; };
struct ethernet_header { unsigned char destination[6]; unsigned char source[6]; __be16 protocol; } __attribute__((packed));
struct vlan_header { __be16 tci; __be16 protocol; } __attribute__((packed));
struct ipv4_header { u8 version_ihl; u8 tos; __be16 length; __be16 id; __be16 fragment; u8 ttl; u8 protocol; __be16 checksum; __be32 source; __be32 target; } __attribute__((packed));
struct ipv6_header { __be32 version_flow; __be16 length; u8 next; u8 hop; struct address6 source; struct address6 target; } __attribute__((packed));

BPF_HASH(addresses4, u32, u32, 1024);
BPF_HASH(addresses6, struct address6, u32, 1024);
BPF_HASH(interfaces, u32, u32, 8);
/* Non-LRU: never silently evict a cumulative counter. Per-CPU values avoid
 * cross-CPU lost updates and allow pre-increment uint64 overflow detection. */
BPF_PERCPU_HASH(counters, struct flow_key, struct totals, 1024);
BPF_PERCPU_ARRAY(dropped, u32, 1);

static __always_inline void mark_drop(void) {
    u32 zero = 0;
    u32 *flag = dropped.lookup(&zero);
    if (flag) *flag = 1;
}

int count_headers(struct __sk_buff *skb) {
    u32 ifindex = skb->ifindex;
    if (!interfaces.lookup(&ifindex)) return 0;
    u32 direction;
    if (skb->pkt_type == PACKET_OUTGOING) direction = 1;
    else if (skb->pkt_type == PACKET_HOST || skb->pkt_type == PACKET_BROADCAST || skb->pkt_type == PACKET_MULTICAST) direction = 0;
    else return 0; /* No promiscuous OTHERHOST or loopback duplicates. */

    struct ethernet_header ethernet = {};
    if (bpf_skb_load_bytes_relative(skb, 0, &ethernet, sizeof(ethernet), BPF_HDR_START_MAC) < 0) { mark_drop(); return 0; }
    u16 protocol = FROM_BE16(ethernet.protocol);
    u32 offset = sizeof(ethernet);
#pragma unroll
    for (int tag = 0; tag < 2; tag++) {
        if (protocol == ETH_P_8021Q || protocol == ETH_P_8021AD) {
            struct vlan_header vlan = {};
            if (bpf_skb_load_bytes_relative(skb, offset, &vlan, sizeof(vlan), BPF_HDR_START_MAC) < 0) { mark_drop(); return 0; }
            protocol = FROM_BE16(vlan.protocol);
            offset += sizeof(vlan);
        }
    }
    if (protocol == ETH_P_8021Q || protocol == ETH_P_8021AD) { mark_drop(); return 0; }
    u32 source = 0, target = 0;
    if (protocol == ETH_P_IP) {
        u8 version_ihl = 0;
        if (bpf_skb_load_bytes_relative(skb, offset, &version_ihl, 1, BPF_HDR_START_MAC) < 0) { mark_drop(); return 0; }
        if ((version_ihl >> 4) != 4 || (version_ihl & 15) < 5) { mark_drop(); return 0; }
        struct ipv4_header ip = {};
        if (bpf_skb_load_bytes_relative(skb, offset, &ip, sizeof(ip), BPF_HDR_START_MAC) < 0) { mark_drop(); return 0; }
        u32 ihl = (ip.version_ihl & 15) * 4;
        if ((ip.version_ihl >> 4) != 4 || ihl < 20 || FROM_BE16(ip.length) < ihl) { mark_drop(); return 0; }
        /* skb->len may exclude the pulled Ethernet header on ingress. Bound
         * the declared IP header in the same MAC-relative coordinate system. */
        u8 header_end = 0;
        if (bpf_skb_load_bytes_relative(skb, offset + ihl - 1, &header_end, 1, BPF_HDR_START_MAC) < 0) { mark_drop(); return 0; }
        u32 *src = addresses4.lookup(&ip.source);
        u32 *dst = addresses4.lookup(&ip.target);
        if (!src || !dst) return 0;
        source = *src; target = *dst;
    } else if (protocol == ETH_P_IPV6) {
        u8 version = 0;
        if (bpf_skb_load_bytes_relative(skb, offset, &version, 1, BPF_HDR_START_MAC) < 0) { mark_drop(); return 0; }
        if ((version >> 4) != 6) { mark_drop(); return 0; }
        struct ipv6_header ip = {};
        if (bpf_skb_load_bytes_relative(skb, offset, &ip, sizeof(ip), BPF_HDR_START_MAC) < 0) { mark_drop(); return 0; }
        if ((FROM_BE32(ip.version_flow) >> 28) != 6) { mark_drop(); return 0; }
        u32 *src = addresses6.lookup(&ip.source);
        u32 *dst = addresses6.lookup(&ip.target);
        if (!src || !dst) return 0;
        source = *src; target = *dst;
    } else return 0;
    if (source == target) return 0;
    if (direction == 1 ? source != LOCAL_NODE : target != LOCAL_NODE) return 0;
    struct flow_key key = {source, target, ifindex, direction};
    struct totals initial = {};
    struct totals *value = counters.lookup_or_try_init(&key, &initial);
    if (!value) { mark_drop(); return 0; }
    if (value->packets == ~0ULL || value->bytes > ~0ULL - (u64)skb->len) { mark_drop(); return 0; }
    value->packets += 1;
    value->bytes += skb->len;
    return 0;
}
