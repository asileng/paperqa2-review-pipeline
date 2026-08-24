# pass4-v1 @ OpenCode Go 套餐发射器
# 用法: powershell -ExecutionPolicy Bypass -File launch_go.ps1 <runner参数透传，如 "6QFXQUNA" 或 "--batch">
# 说明: 从 ~/.local/share/opencode/auth.json 读取 opencode-go key，
#       注入 OPENAI_API_KEY / OPENAI_API_BASE / PILOT_LLM / PILOT_VLM 后 detached 启动。
param(
    [switch]$Batch,
    [string]$Keys = "",
    [int]$Concurrency = 4,
    [double]$MaxHours = 10
)
$ErrorActionPreference = "Stop"
$base = "D:\task\科研\HCI+\litereature review\paperqa2\integration-tests\pass4-v1"
$py = "D:\anaconda\miniconda3\envs\paperqa\python.exe"

$auth = Get-Content "$env:USERPROFILE\.local\share\opencode\auth.json" -Raw | ConvertFrom-Json
$key = $auth.'opencode-go'.key
if (-not $key) { throw "opencode-go key not found in auth.json" }

$env:OPENAI_API_KEY = $key
$env:OPENAI_API_BASE = "https://opencode.ai/zen/go/v1"
$env:PILOT_LLM = "openai/qwen3.7-plus"
$env:PILOT_VLM = "openai/deepseek-v4-flash-vision-exp"

if ($Batch) {
    $argList = @("batch.py", "--concurrency", "$Concurrency", "--max-hours", "$MaxHours")
    if ($Keys) { $argList += (@("--include") + ($Keys -split ",")) }
    $log = "$base\logs\batch_go.log"; $err = "$base\logs\batch_go.err.log"
} else {
    $argList = @("runner.py") + ($Keys -split "," | Where-Object { $_ })
    $log = "$base\logs\pilot_go.log"; $err = "$base\logs\pilot_go.err.log"
}

$p = Start-Process -FilePath $py -ArgumentList $argList -WorkingDirectory $base `
    -RedirectStandardOutput $log -RedirectStandardError $err -WindowStyle Hidden -PassThru
Set-Content -Path "$base\logs\current.pid" -Value $p.Id
Write-Output "GO-MODE LAUNCHED PID $($p.Id) | llm=$env:PILOT_LLM vlm=$env:PILOT_VLM"
