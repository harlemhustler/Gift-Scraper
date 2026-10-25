$ErrorActionPreference = 'Stop'

$projectRoot = $PSScriptRoot
$registryPath = Join-Path $projectRoot 'data\gifts.json'
$monitorTaskName = 'EcoPlug-Gift-Inventory-Monitor'
$pythonCommand = Get-Command python3.14.exe -ErrorAction SilentlyContinue
if (-not $pythonCommand) {
    $pythonCommand = Get-Command python.exe -ErrorAction Stop
}
$python = $pythonCommand.Source
if ($python -like '*\WindowsApps\*') {
    throw 'The selected Python is a Microsoft Store alias. Install Python and retry.'
}

if (-not (Test-Path $registryPath -PathType Leaf)) {
    throw "Gift registry not found: $registryPath"
}
$registry = Get-Content $registryPath -Raw | ConvertFrom-Json
$activeGifts = @($registry.gifts | Where-Object { $_.status -eq 'active' })
if ($activeGifts.Count -lt 6) {
    throw "Refusing to schedule an incomplete pool: add and verify at least six real AliExpress free-with-purchase offers first."
}
foreach ($gift in $activeGifts) {
    if (-not $gift.title -or -not $gift.purchase_condition -or $gift.offer_url -notmatch '^https://([a-z0-9-]+\.)*aliexpress\.(com|us)/') {
        throw "Gift '$($gift.id)' is missing a verified title, offer condition, or valid AliExpress URL."
    }
}

$tokenFile = [Environment]::GetEnvironmentVariable('GORGON_INVENTORY_TOKEN_FILE', 'User')
if (-not $tokenFile -or -not (Test-Path $tokenFile -PathType Leaf)) {
    throw 'Set the user-level GORGON_INVENTORY_TOKEN_FILE to the private Gorgon API token file before scheduling.'
}
$token = (Get-Content $tokenFile -Raw).Trim()
if ($token.Length -lt 32) {
    throw 'The Gorgon inventory token must contain at least 32 characters.'
}

$inventoryUrl = [Environment]::GetEnvironmentVariable('GORGON_INVENTORY_URL', 'User')
if (-not $inventoryUrl) {
    $inventoryUrl = 'https://api.g0rg0nit3.com/api/inventory/update'
}
$inventoryUri = [Uri]$inventoryUrl
$healthUrl = "$($inventoryUri.Scheme)://$($inventoryUri.Authority)/health"
try {
    $healthResponse = Invoke-WebRequest -Uri $healthUrl -TimeoutSec 15
    if ($healthResponse.StatusCode -ne 200) {
        throw "Gorgon health check returned HTTP $($healthResponse.StatusCode)."
    }
} catch {
    throw "Gorgon must be online before scheduling the monitor. Health check failed: $($_.Exception.Message)"
}

$action = New-ScheduledTaskAction -Execute $python -Argument '-m src.gift_scraper.inventory_monitor' -WorkingDirectory $projectRoot
$trigger = New-ScheduledTaskTrigger -Daily -At (Get-Date).AddMinutes(2) `
    -RepetitionInterval (New-TimeSpan -Hours 1) -RepetitionDuration (New-TimeSpan -Days 1)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId "${env:USERDOMAIN}\${env:USERNAME}" -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $monitorTaskName -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal -Description 'Hourly check of approved EcoPlug AliExpress free-with-purchase gifts.' -Force | Out-Null

Write-Host "Registered $monitorTaskName. It runs hourly while this Windows account is signed in."
