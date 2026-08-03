#!/bin/bash
set -euo pipefail

# Whonix Gateway Integration for Kali OSINT Agent
# This configures the Kali VM to route traffic through a Whonix Gateway VM
# on the same Proxmox host for maximum anonymity.
#
# Prerequisites:
#   - Whonix Gateway VM running on same Proxmox host
#   - Kali VM connected to Whonix internal network (vmbr1 or similar)
#   - Whonix Gateway IP: 10.152.152.10 (default)
#
# Architecture:
#   Kali VM ──► Whonix Internal Net ──► Whonix Gateway ──► Tor ──► Internet
#
# This provides better isolation than running Tor directly on Kali because:
#   - Tor process is isolated in its own VM
#   - Even if Kali is compromised, Tor circuits can't be manipulated
#   - DNS leaks are prevented at the network layer
#   - Stream isolation is handled by the gateway

WHONIX_GW_IP="${WHONIX_GW_IP:-10.152.152.10}"
KALI_INTERNAL_IP="${KALI_INTERNAL_IP:-10.152.152.11}"
INTERNAL_IFACE="${INTERNAL_IFACE:-eth1}"

echo "[*] Configuring Kali to use Whonix Gateway at ${WHONIX_GW_IP}..."

# Configure the internal network interface
cat > /etc/network/interfaces.d/whonix << EOF
auto ${INTERNAL_IFACE}
iface ${INTERNAL_IFACE} inet static
    address ${KALI_INTERNAL_IP}
    netmask 255.255.192.0
    gateway ${WHONIX_GW_IP}
EOF

# Configure DNS through Whonix (prevents DNS leaks)
cat > /etc/resolv.conf.whonix << EOF
nameserver ${WHONIX_GW_IP}
EOF

# Create a script to toggle Whonix routing
cat > /usr/local/bin/whonix-toggle << 'TOGGLE'
#!/bin/bash
WHONIX_GW="${WHONIX_GW_IP}"
INTERNAL_IFACE="${INTERNAL_IFACE}"

case "$1" in
    on)
        echo "[*] Enabling Whonix routing..."
        # Backup current resolv.conf
        cp /etc/resolv.conf /etc/resolv.conf.backup 2>/dev/null || true
        cp /etc/resolv.conf.whonix /etc/resolv.conf

        # Route all traffic through Whonix gateway
        ip route add default via ${WHONIX_GW} dev ${INTERNAL_IFACE} metric 50

        # Block direct internet access (force through Whonix)
        iptables -I OUTPUT -o eth0 -j DROP 2>/dev/null || true
        iptables -I OUTPUT -o ${INTERNAL_IFACE} -j ACCEPT

        echo "[+] All traffic now routed through Whonix Gateway"
        ;;
    off)
        echo "[*] Disabling Whonix routing..."
        # Restore DNS
        cp /etc/resolv.conf.backup /etc/resolv.conf 2>/dev/null || true

        # Remove Whonix route
        ip route del default via ${WHONIX_GW} dev ${INTERNAL_IFACE} 2>/dev/null || true

        # Restore direct access
        iptables -D OUTPUT -o eth0 -j DROP 2>/dev/null || true

        echo "[+] Direct internet access restored"
        ;;
    status)
        if ip route | grep -q "${WHONIX_GW}"; then
            echo "[+] Whonix routing: ACTIVE"
            echo "    Gateway: ${WHONIX_GW}"
            curl -s --socks5 ${WHONIX_GW}:9050 https://api.ipify.org 2>/dev/null && echo " (exit IP)" || echo "    Cannot reach Tor network"
        else
            echo "[-] Whonix routing: INACTIVE"
        fi
        ;;
    *)
        echo "Usage: $0 {on|off|status}"
        exit 1
        ;;
esac
TOGGLE
chmod +x /usr/local/bin/whonix-toggle

# Configure proxychains to use Whonix gateway's Tor port
cat > /etc/proxychains4.conf.whonix << EOF
strict_chain
proxy_dns
tcp_read_time_out 15000
tcp_connect_time_out 8000
[ProxyList]
socks5 ${WHONIX_GW_IP} 9050
EOF

echo "[*] Bringing up internal interface..."
ifup ${INTERNAL_IFACE} 2>/dev/null || ip addr add ${KALI_INTERNAL_IP}/18 dev ${INTERNAL_IFACE} 2>/dev/null || true
ip link set ${INTERNAL_IFACE} up 2>/dev/null || true

echo ""
echo "============================================"
echo " Whonix Gateway Integration Complete"
echo "============================================"
echo ""
echo " Usage:"
echo "   whonix-toggle on      # Route all traffic through Whonix"
echo "   whonix-toggle off     # Restore direct access"
echo "   whonix-toggle status  # Check current state"
echo ""
echo " The OSINT agent will auto-detect Whonix when proxy_mode=whonix"
echo ""
