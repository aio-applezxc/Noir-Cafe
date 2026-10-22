param([string]$OutputDirectory = (Join-Path $PSScriptRoot '..\evidence-local'))
# Read-only checks. Does not change device configuration or read .env/passwords.
$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$Checks = [ordered]@{
    CapturedAt = { (Get-Date).ToString('o') }
    OS = { Get-CimInstance Win32_OperatingSystem | Select-Object Caption,Version,BuildNumber }
    CPU = { Get-CimInstance Win32_Processor | Select-Object Name,NumberOfCores,NumberOfLogicalProcessors }
    Memory = { Get-CimInstance Win32_ComputerSystem | Select-Object TotalPhysicalMemory }
    Motherboard = { Get-CimInstance Win32_BaseBoard | Select-Object Manufacturer,Product }
    Disks = { Get-CimInstance Win32_DiskDrive | Select-Object Model,Size,InterfaceType }
    Network = { Get-NetIPConfiguration | Select-Object InterfaceAlias,IPv4Address,IPv4DefaultGateway,DNSServer }
    Adapters = { Get-NetAdapter | Select-Object Name,InterfaceDescription,MacAddress,Status,LinkSpeed }
    Firewall = { Get-NetFirewallProfile | Select-Object Name,Enabled,DefaultInboundAction,DefaultOutboundAction }
    Antivirus = { Get-MpComputerStatus | Select-Object AntivirusEnabled,RealTimeProtectionEnabled,AntivirusSignatureLastUpdated }
    TPM = { Get-Tpm | Select-Object TpmPresent,TpmReady }
    SecureBoot = { Confirm-SecureBootUEFI }
}
$Evidence = [ordered]@{}
foreach ($Key in $Checks.Keys) {
    try { $Evidence[$Key] = & $Checks[$Key] }
    catch { $Evidence[$Key] = "Check unavailable: $($_.Exception.Message)" }
}
$OutputFile = Join-Path $OutputDirectory ('platform-evidence-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.json')
$Evidence | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $OutputFile -Encoding UTF8
Write-Host "Saved: $OutputFile"
Write-Host 'Review network identifiers before submission. Capture screenshots separately. Unavailable checks are not passes.'
