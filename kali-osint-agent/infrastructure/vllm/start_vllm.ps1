# vLLM Startup Script for Windows (PowerShell)
# Run from an elevated PowerShell terminal with CUDA installed

param(
    [string]$Model = "nvidia/Nemotron-Mini-4B-Instruct",
    [int]$Port = 8000,
    [string]$Host = "0.0.0.0",
    [float]$GpuMemUtil = 0.85,
    [int]$MaxModelLen = 8192
)

$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host " vLLM Server - Kali OSINT Agent" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Model:    $Model"
Write-Host "Endpoint: http://${Host}:${Port}/v1"
Write-Host "GPU Mem:  $($GpuMemUtil * 100)%"
Write-Host ""

# Check if vllm is installed
try {
    python -c "import vllm" 2>$null
} catch {
    Write-Host "[!] vLLM not found. Installing..." -ForegroundColor Yellow
    pip install vllm
}

# Open firewall port
$rule = Get-NetFirewallRule -DisplayName "vLLM OSINT Agent" -ErrorAction SilentlyContinue
if (-not $rule) {
    Write-Host "[*] Adding firewall rule for port $Port..." -ForegroundColor Yellow
    New-NetFirewallRule -DisplayName "vLLM OSINT Agent" `
        -Direction Inbound -LocalPort $Port -Protocol TCP -Action Allow | Out-Null
}

Write-Host "[*] Starting vLLM server..." -ForegroundColor Green
Write-Host ""

python -m vllm.entrypoints.openai.api_server `
    --model $Model `
    --host $Host `
    --port $Port `
    --tensor-parallel-size 1 `
    --max-model-len $MaxModelLen `
    --gpu-memory-utilization $GpuMemUtil `
    --dtype auto
