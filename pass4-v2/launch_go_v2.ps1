# pass4-v2 @ 跨 provider 路由发射器
# 用法: powershell -ExecutionPolicy Bypass -File launch_go_v2.ps1 [-Keys "A,B"] [-Batch] [-Provider go|dashscope|auto] [-ZoteroIndex]
# 说明: 注入 OPENAI_API_KEY/BASE(Go 网关)；DASHSCOPE_API_KEY 取自用户环境。
#       模型选择由 model_router.py 决定（GLUE v2-dev §九），PILOT_* 已废弃。
param(
    [switch]$Batch,
    [string]$Keys = "",
    [int]$Concurrency = 4,
    [double]$MaxHours = 11,
    [ValidateSet("auto","go","dashscope")][string]$Provider = "auto",
    [switch]$WaitReset,
    [switch]$ZoteroIndex,
    [switch]$NoProbe
)
$ErrorActionPreference = "Stop"
$base = "D:\task\科研\HCI+\litereature review\paperqa2\integration-tests\pass4-v2"
$py = "D:\anaconda\miniconda3\envs\paperqa\python.exe"

$auth = Get-Content "$env:USERPROFILE\.local\share\opencode\auth.json" -Raw | ConvertFrom-Json
$key = $auth.'opencode-go'.key
if (-not $key) { throw "opencode-go key not found in auth.json" }

$env:OPENAI_API_KEY = $key
$env:OPENAI_API_BASE = "https://opencode.ai/zen/go/v1"
# DeepSeek 兜底：研究者将 API key 存于环境变量 'paperqa'，此处映射为 litellm 标准 var
$pk = $env:paperqa
if (-not $pk) { $pk = [Environment]::GetEnvironmentVariable("paperqa","User") }
if (-not $pk) { throw "neither DEEPSEEK_API_KEY nor 'paperqa' env var found for deepseek fallback" }
$env:DEEPSEEK_API_KEY = $pk

if ($Batch) {
    $argList = @("batch.py", "--concurrency", "$Concurrency", "--max-hours", "$MaxHours")
    if ($WaitReset) { $argList += "--wait-reset" }
    if ($NoProbe) { $argList += "--no-probe" }
    if ($Keys) { $argList += (@("--include") + ($Keys -split ",")) }
    $log = "$base\logs\batch_routed.log"; $err = "$base\logs\batch_routed.err.log"
} else {
    $argList = @("runner.py", "--provider", $Provider)
    if ($ZoteroIndex) { $argList += "--update-zotero-index" }
    $argList += ($Keys -split "," | Where-Object { $_ })
    $log = "$base\logs\runner_routed.log"; $err = "$base\logs\runner_routed.err.log"
}

$p = Start-Process -FilePath $py -ArgumentList $argList -WorkingDirectory $base `
    -RedirectStandardOutput $log -RedirectStandardError $err -WindowStyle Hidden -PassThru
Set-Content -Path "$base\logs\current.pid" -Value $p.Id
Write-Output "ROUTED-MODE LAUNCHED PID $($p.Id) | mode=$(if($Batch){'batch'}else{'single'}) provider=$Provider"
