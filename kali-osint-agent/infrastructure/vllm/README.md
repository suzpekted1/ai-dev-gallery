# vLLM Setup for OSINT Agent - Windows PC (RTX 5090)
#
# This runs Nemotron Mini locally on your Windows PC via vLLM,
# serving an OpenAI-compatible API that the Kali agent connects to.
# All sensitive/private queries route here instead of external APIs.
#
# Prerequisites:
#   - Windows PC with NVIDIA RTX 5090
#   - CUDA 12.x installed
#   - Python 3.11+ with pip
#   - WSL2 recommended (vLLM runs better on Linux)
#
# Architecture:
#   Kali VM (LAN) ──► Windows PC vLLM (LAN:8000) ──► Nemotron Mini (GPU)
#
# The vLLM server exposes an OpenAI-compatible /v1/chat/completions endpoint.
# No data leaves your LAN for queries routed to this model.

## Option 1: WSL2 (Recommended)

### Install vLLM in WSL2:
```bash
# In WSL2 terminal:
pip install vllm

# Download and serve Nemotron Mini:
vllm serve nvidia/Nemotron-Mini-4B-Instruct \
    --host 0.0.0.0 \
    --port 8000 \
    --tensor-parallel-size 1 \
    --max-model-len 8192 \
    --gpu-memory-utilization 0.85 \
    --dtype auto
```

### For fine-tuned OSINT model (after fine-tuning):
```bash
vllm serve ./nemotron-osint-finetuned \
    --host 0.0.0.0 \
    --port 8000 \
    --tensor-parallel-size 1 \
    --max-model-len 8192 \
    --gpu-memory-utilization 0.85 \
    --dtype auto
```

## Option 2: Native Windows (PowerShell)

Use the provided `start_vllm.ps1` script.

## Verify it works:

```bash
# From Kali VM (replace IP):
curl http://192.168.1.100:8000/v1/models

curl http://192.168.1.100:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "nvidia/Nemotron-Mini-4B-Instruct",
    "messages": [{"role": "user", "content": "What is OSINT?"}],
    "max_tokens": 100
  }'
```

## Windows Firewall

Allow port 8000 through Windows Firewall for LAN access:
```powershell
New-NetFirewallRule -DisplayName "vLLM OSINT Agent" -Direction Inbound -LocalPort 8000 -Protocol TCP -Action Allow
```

## Fine-Tuning Nemotron for OSINT

See `configs/finetune_config.yaml` for the fine-tuning pipeline that
creates an OSINT-specialized version of Nemotron Mini. This model
understands security tooling output, OSINT terminology, and produces
better structured reports.
