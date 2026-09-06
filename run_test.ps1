$requests = @(
    @{ label = "1) Initialize handshake";        json = '{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "manual-test", "version": "1.0"}}}' }
    @{ label = "2) Confirm initialized (no reply expected)"; json = '{"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}' }
    @{ label = "3) List available tools";        json = '{"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}' }
    @{ label = "4) List available datasets";     json = '{"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "list_datasets", "arguments": {}}}' }
    @{ label = "5) List run history (should be empty first time)"; json = '{"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "list_run_history", "arguments": {}}}' }
    @{ label = "6) Run an eval (calls real model)"; json = '{"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "run_eval", "arguments": {"dataset": "sample_eval.json", "model": "gemini-flash-latest", "provider": "gemini"}}}' }
)

$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = "python"
$psi.Arguments = "server.py"
$psi.RedirectStandardInput = $true
$psi.RedirectStandardOutput = $true
$psi.UseShellExecute = $false

$proc = [System.Diagnostics.Process]::Start($psi)

foreach ($r in $requests) {
    Write-Host ""
    Write-Host "----- $($r.label) -----" -ForegroundColor Cyan
    $proc.StandardInput.WriteLine($r.json)
    if ($r.json -notmatch "notifications") {
        $line = $proc.StandardOutput.ReadLine()
        Write-Host $line
    }
}

$proc.StandardInput.Close()
$proc.WaitForExit()
