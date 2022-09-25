# Script has been deprecated; use system to manage restarting
$host.UI.RawUI.WindowTitle = "thegamebot"

function Raise-Number {
    param (
        [int]$X,
        [int]$Y
    )
    $result = 1
    FOR ($i = 0; $i -lt $Y; $i++) {
        $result *= $X
    }
    $result
}

# Blame ArgumentList for having to do this
$CleanArgs = $args
IF (!$args.Count) {
    $CleanArgs = @()
}

$BackoffExponent = 0

do {
    Remove-Item "SHUTDOWN" -ErrorAction SilentlyContinue

    # .venv\Scripts\pip.exe "install" "-U" "discord.py"
    $RunTime = Measure-Command {
        Start-Process `
            "main.bat" `
            -ArgumentList $CleanArgs `
            -Wait `
            -WindowStyle Normal
    }

    # Assume program ran correctly if it takes more than 10 seconds
    IF ($RunTime.TotalSeconds -gt 10) {
        $BackoffExponent = 0
    } ELSE {
        $BackoffExponent += 1
    }
    # Exponential Backoff
    $SleepTime = Raise-Number 2 $BackoffExponent
    Write-Host "Sleeping for $($SleepTime)s..."
    Start-Sleep $SleepTime

} while (-NOT (Test-Path "SHUTDOWN"))
