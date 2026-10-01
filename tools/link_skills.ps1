# Relie .claude/skills à .agents/skills pour que Claude Code voie les skills du projet.
# Jonction locale (non versionnée) : à relancer après un clonage.
#   powershell -ExecutionPolicy Bypass -File tools/link_skills.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$target = Join-Path $root ".agents\skills"
$claudeDir = Join-Path $root ".claude"
$link = Join-Path $claudeDir "skills"

if (-not (Test-Path $target)) { throw "Dossier introuvable : $target" }
New-Item -ItemType Directory -Force $claudeDir | Out-Null

if (Test-Path $link) {
    $item = Get-Item $link -Force
    if ($item.LinkType) {
        Write-Host "Déjà en place : $link -> $($item.Target)"
        exit 0
    }
    throw "$link existe et n'est pas une jonction : le déplacer ou le supprimer avant de relancer."
}

New-Item -ItemType Junction -Path $link -Target $target | Out-Null
Write-Host "Jonction créée : $link -> $target"
