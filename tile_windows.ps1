Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Win32T {
    [DllImport("user32.dll")]
    public static extern bool MoveWindow(IntPtr h, int x, int y, int w, int ht, bool r);
    [DllImport("user32.dll")]
    public static extern bool SetForegroundWindow(IntPtr h);
}
"@

Add-Type -AssemblyName System.Windows.Forms
$bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$sysW = $bounds.Width
$sysH = $bounds.Height

$colW = [int]($sysW / 2)
$rowH = [int]($sysH / 2)

# Corner layout: top-left, top-right, bottom-left, bottom-right
$apps = @(
    @{ Name = 'cmd';               X = 0;         Y = 0;        W = $colW; H = $rowH },
    @{ Name = 'VisualStudioCode';  X = $colW;     Y = 0;        W = $colW; H = $rowH },
    @{ Name = 'brave';             X = 0;         Y = $rowH;    W = $colW; H = $rowH },
    @{ Name = 'Spotify';           X = $colW;     Y = $rowH;    W = $colW; H = $rowH }
)

foreach ($a in $apps) {
    # Get the process that has a main window handle
    $procs = Get-Process -Name $a.Name -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne [IntPtr]::Zero }
    if ($procs) {
        $p = $procs | Select-Object -First 1
        $h = $p.MainWindowHandle
        if ($h -ne [IntPtr]::Zero) {
            [Win32T]::MoveWindow($h, $a.X, $a.Y, $a.W, $a.H, $true) | Out-Null
            [Win32T]::SetForegroundWindow($h) | Out-Null
            Write-Output ("Positioned " + $a.Name + " at x=" + $a.X + " y=" + $a.Y + " w=" + $a.W + " h=" + $a.H)
        } else {
            Write-Output ($a.Name + " no handle")
        }
    } else {
        Write-Output ($a.Name + " not found")
    }
}
