<#
.SYNOPSIS
  Publishes Address Explorer and its documentation into docs/.
.DESCRIPTION
  - Documentation sections are built from the Address knowledge-vault notes.
  - docs/design.md is copied from the Address POC design note.
  - The POC design section is inserted from src/design-tab.html.
  - docs/index.html is the primary app; docs/documentation.html contains the guide.
  - docs/documentation.css styles the guide to match POC Asset.
.EXAMPLE
  powershell -File scripts/publish.ps1
#>

param(
  [string]$VaultProjectPath
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if ([string]::IsNullOrWhiteSpace($VaultProjectPath)) {
  $VaultProjectPath = Join-Path $repoRoot '..\..\Obsidian\Projects\POC-Documentation\POC-Documentation-Vault\projects\Address'
}
$wiki   = (Resolve-Path -LiteralPath $VaultProjectPath).Path
$out    = Join-Path $repoRoot 'docs'
$tmpl   = Get-Content (Join-Path $repoRoot 'src\template.html') -Raw -Encoding UTF8

function Convert-WikiPage {
  param([string]$Path)

  $lines = Get-Content $Path -Encoding UTF8
  $html  = New-Object System.Collections.Generic.List[string]
  $i = 0
  while ($i -lt $lines.Count) {
    $line = $lines[$i]

    # Skip YAML-ish front matter noise, H1 title, Source: line, Related: line
    if ($line -match '^#\s' -or $line -match '^Source:' -or $line -match '^Related:') { $i++; continue }

    # Fenced code block
    if ($line -match '^```') {
      $buf = New-Object System.Collections.Generic.List[string]
      $i++
      while ($i -lt $lines.Count -and $lines[$i] -notmatch '^```') { $buf.Add($lines[$i]); $i++ }
      $i++
      $code = ($buf -join "`n") -replace '&','&amp;' -replace '<','&lt;' -replace '>','&gt;'
      $html.Add('    <pre><code>' + $code + '</code></pre>')
      continue
    }

    # Table block
    if ($line -match '^\|') {
      $rows = New-Object System.Collections.Generic.List[string]
      while ($i -lt $lines.Count -and $lines[$i] -match '^\|') { $rows.Add($lines[$i]); $i++ }
      $html.Add('    <table>')
      $first = $true
      foreach ($r in $rows) {
        if ($r -match '^\|[\s\-|]+\|$') { continue }  # separator row
        $cells = $r.Trim('|').Split('|') | ForEach-Object { $_.Trim() }
        $tag = if ($first) { 'th' } else { 'td' }
        $html.Add('      <tr>' + (($cells | ForEach-Object { "<$tag>$((Format-Inline $_))</$tag>" }) -join '') + '</tr>')
        $first = $false
      }
      $html.Add('    </table>')
      continue
    }

    # Headings
    if ($line -match '^####\s+(.*)') { $html.Add("    <h4>$(Format-Inline $matches[1])</h4>"); $i++; continue }
    if ($line -match '^###\s+(.*)')  { $html.Add("    <h4>$(Format-Inline $matches[1])</h4>"); $i++; continue }
    if ($line -match '^##\s+(.*)')   { $html.Add("    <h3>$(Format-Inline $matches[1])</h3>"); $i++; continue }

    # Unordered list
    if ($line -match '^[-*]\s+') {
      $html.Add('    <ul class="docs-list">')
      while ($i -lt $lines.Count -and $lines[$i] -match '^[-*]\s+(.*)') {
        $html.Add("      <li>$(Format-Inline $matches[1])</li>"); $i++
      }
      $html.Add('    </ul>')
      continue
    }

    # Ordered list
    if ($line -match '^\d+\.\s+') {
      $html.Add('    <ol class="docs-list">')
      while ($i -lt $lines.Count -and $lines[$i] -match '^\d+\.\s+(.*)') {
        $html.Add("      <li>$(Format-Inline $matches[1])</li>"); $i++
      }
      $html.Add('    </ol>')
      continue
    }

    # Blank line
    if ([string]::IsNullOrWhiteSpace($line)) { $i++; continue }

    # Paragraph
    $html.Add("    <p>$(Format-Inline $line)</p>")
    $i++
  }
  return ($html -join "`n")
}

function Format-Inline {
  param([string]$Text)
  $t = $Text
  $t = $t -replace '\[\[([^\]]+)\]\]', '$1'          # [[wiki-link]] -> text
  $t = $t -replace '\*\*([^*]+)\*\*', '<strong>$1</strong>'
  $t = $t -replace '`([^`]+)`', '<code>$1</code>'
  return $t
}

function Docs-Section {
  param([string]$Id, [string]$Kicker, [string]$Title, [string]$Inner)
  $tpl = '<section class="docs-section panel" id="' + $Id + '">' + "`n" +
         '  <div class="section-kicker">' + $Kicker + '</div>' + "`n" +
         '  <h2>' + $Title + '</h2>' + "`n" +
         $Inner + "`n" +
         '</section>' + "`n`n"
  return $tpl
}

$overview = Docs-Section 'overview' 'OVERVIEW' 'International Addressing Standards' (Convert-WikiPage (Join-Path $wiki 'Overview.md'))
$upu      = Docs-Section 'upu-s42' 'UPU S42' 'UPU S42 Addressing Standard' (Convert-WikiPage (Join-Path $wiki 'UPU-S42.md'))
$iso      = Docs-Section 'iso-20022' 'ISO 20022' 'ISO 20022 Address Schema' (Convert-WikiPage (Join-Path $wiki 'ISO-20022.md'))
$uk       = Docs-Section 'uk-format' 'UK FORMAT' 'UK Address Format' (Convert-WikiPage (Join-Path $wiki 'UK-Address-Format.md'))
$api      = Docs-Section 'loqate-api' 'LOQATE API' 'LOQATE API Integration' (Convert-WikiPage (Join-Path $wiki 'Loqate-api.md'))
$design   = Get-Content (Join-Path $repoRoot 'src\design-tab.html') -Raw -Encoding UTF8

$page = $tmpl
$page = $page.Replace('{{OVERVIEW}}', $overview)
$page = $page.Replace('{{UPU}}',      $upu)
$page = $page.Replace('{{ISO}}',      $iso)
$page = $page.Replace('{{UK}}',       $uk)
$page = $page.Replace('{{API}}',      $api)
$page = $page.Replace('{{DESIGN}}',   $design)

New-Item -ItemType Directory -Force $out | Out-Null
Set-Content (Join-Path $out 'documentation.html') $page -NoNewline -Encoding UTF8
Copy-Item -LiteralPath (Join-Path $repoRoot 'src\documentation.css') -Destination (Join-Path $out 'documentation.css')
Write-Host "Wrote $(Join-Path $out 'documentation.html')"

# Publish the production design note from its knowledge-vault source.
Copy-Item -LiteralPath (Join-Path $wiki 'Poc-Design.md') -Destination (Join-Path $out 'design.md')
Write-Host "Copied production design from $wiki"

$appSource = Join-Path $repoRoot 'src'
$appHtml = Get-Content (Join-Path $appSource 'poc-address-app.html') -Raw -Encoding UTF8

$rootApp = $appHtml.Replace('../docs/documentation.html', './documentation.html')
Set-Content (Join-Path $out 'index.html') $rootApp -NoNewline -Encoding UTF8
Copy-Item (Join-Path $appSource 'loqate-client.js') (Join-Path $out 'loqate-client.js')

# Stage for GitHub Pages (served from /docs on the repo root)
New-Item -ItemType File -Force (Join-Path $out '.nojekyll') | Out-Null
Write-Host "Published Address Explorer as the home page and the standards guide separately."
