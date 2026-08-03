#!/bin/bash
set -euo pipefail

# Kali OSINT Agent - Proxmox VM Setup Script
# Run this on a fresh Kali Linux VM after initial install

echo "[*] Updating system..."
apt-get update && apt-get upgrade -y

echo "[*] Installing core dependencies..."
apt-get install -y \
    python3 python3-pip python3-venv python3-dev \
    git curl wget jq \
    tor torsocks proxychains4 \
    nmap theharvester recon-ng \
    whois dnsutils netcat-openbsd \
    build-essential libffi-dev libssl-dev \
    chromium

echo "[*] Installing Docker..."
apt-get install -y docker.io docker-compose-plugin
systemctl enable docker
systemctl start docker

echo "[*] Configuring Tor..."
cat > /etc/tor/torrc << 'TORRC'
SocksPort 9050
ControlPort 9051
HashedControlPassword $(tor --hash-password "osint-agent-tor" | tail -1)
CookieAuthentication 0
ExitPolicy reject *:*
TORRC
systemctl enable tor
systemctl restart tor

echo "[*] Configuring proxychains..."
cat > /etc/proxychains4.conf << 'PROXYCHAINS'
strict_chain
proxy_dns
tcp_read_time_out 15000
tcp_connect_time_out 8000
[ProxyList]
socks5 127.0.0.1 9050
PROXYCHAINS

echo "[*] Setting up Python virtual environment..."
cd /opt
git clone https://github.com/suzpekted1/ai-dev-gallery.git || true
cd ai-dev-gallery/kali-osint-agent

python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev]"

echo "[*] Setting up environment..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo "[!] Created .env from template - EDIT WITH YOUR API KEYS"
fi

echo "[*] Starting Docker services..."
docker compose up -d

echo "[*] Waiting for services to be healthy..."
sleep 10

echo "[*] Verifying services..."
docker compose ps

echo ""
echo "============================================"
echo " Kali OSINT Agent - Setup Complete"
echo "============================================"
echo ""
echo " Next steps:"
echo " 1. Edit /opt/ai-dev-gallery/kali-osint-agent/.env with your API keys"
echo " 2. Activate venv: source /opt/ai-dev-gallery/kali-osint-agent/.venv/bin/activate"
echo " 3. Start the agent: make run"
echo " 4. Access dashboard: http://localhost:8000/docs"
echo ""
echo " Services:"
echo "   PostgreSQL:  localhost:5432"
echo "   Neo4j:       http://localhost:7474"
echo "   Redis:       localhost:6379"
echo "   Tor SOCKS:   localhost:9050"
echo ""
