param([ValidateSet('run','setup','migrate','init','create-admin')][string]$Mode = 'run')
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

function Invoke-Checked {
    param([string]$Executable, [string[]]$Arguments)
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Command failed. Read the error above before continuing." }
}

$NoirPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $NoirPython)) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        Invoke-Checked 'py' @('-3','-m','venv','.venv')
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        Invoke-Checked 'python' @('-m','venv','.venv')
    } else { throw 'Install Python 3.11 or newer, then reopen the VS Code terminal.' }
    Invoke-Checked $NoirPython @('-m','pip','install','-r','requirements.txt')
} elseif ($Mode -eq 'setup') {
    Invoke-Checked $NoirPython @('-m','pip','install','-r','requirements.txt')
}

if (-not (Test-Path -LiteralPath '.env')) {
    Invoke-Checked $NoirPython @('scripts/configure.py')
    Write-Host 'Open .env beside app.py. Set the MySQL host, database, user and password.'
    Write-Host 'If upgrading, copy your original .env here instead. Do not copy an old .venv.'
    Write-Host 'After saving .env, run .\Start-Noir.ps1 -Mode migrate (existing database) or -Mode init (new database).'
    exit 0
}
switch ($Mode) {
    'setup' { Write-Host 'Dependencies ready. Check .env, then use migrate or init. See START-HERE.md.' }
    'migrate' { Invoke-Checked $NoirPython @('-m','flask','--app','app','migrate-db') }
    'init' { Invoke-Checked $NoirPython @('-m','flask','--app','app','init-db') }
    'create-admin' { Invoke-Checked $NoirPython @('-m','flask','--app','app','create-admin') }
    'run' { Invoke-Checked $NoirPython @('app.py') }
}
