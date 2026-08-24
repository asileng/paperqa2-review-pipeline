# pass4-v1 批量发射器：detached 启动 batch.py，写 PID，返回
$base = "D:\task\科研\HCI+\litereature review\paperqa2\integration-tests\pass4-v1"
$py = "D:\anaconda\miniconda3\envs\paperqa\python.exe"
$conc = if ($args.Count -ge 1) { $args[0] } else { "4" }
$maxh = if ($args.Count -ge 2) { $args[1] } else { "9.5" }
$extra = @()
if ($args.Count -ge 3 -and $args[2]) { $extra += @("--include") + ($args[2] -split ",") }
$p = Start-Process -FilePath $py -ArgumentList (@("batch.py", "--concurrency", $conc, "--max-hours", $maxh) + $extra) `
    -WorkingDirectory $base `
    -RedirectStandardOutput "$base\logs\batch.log" `
    -RedirectStandardError "$base\logs\batch.err.log" `
    -WindowStyle Hidden -PassThru
Set-Content -Path "$base\logs\batch.pid" -Value $p.Id
Write-Output "BATCH LAUNCHED PID $($p.Id) concurrency=$conc max_hours=$maxh"
