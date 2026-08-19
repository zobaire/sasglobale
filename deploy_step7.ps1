$ErrorActionPreference = "Stop"

$src = "C:\Users\book\Desktop\Lydia\imports\player.gd"
$dst = "C:\Users\book\Desktop\fate's-pair\scripts\player.gd"

# Backup + copy the new player.gd
Copy-Item $dst "$dst.bak" -Force
Copy-Item $src $dst -Force
Write-Host "player.gd deployed"

# Strip the old plain Camera3D from player.tscn (the script now creates
# its own camera inside a BoneAttachment3D on the head bone)
$tscn = "C:\Users\book\Desktop\fate's-pair\scenes\player.tscn"
Copy-Item $tscn "$tscn.bak" -Force

$lines = Get-Content $tscn
$out = New-Object System.Collections.Generic.List[string]
$skipNext = $false
foreach ($ln in $lines) {
    if ($ln.Contains('[node name="Camera3D"')) {
        $skipNext = $true   # drop this node header...
        continue
    }
    if ($skipNext) {
        $skipNext = $false  # ...and its transform line
        continue
    }
    $out.Add($ln)
}
[System.IO.File]::WriteAllLines($tscn, $out, (New-Object System.Text.UTF8Encoding($false)))
Write-Host "player.tscn cleaned (old Camera3D removed)"
