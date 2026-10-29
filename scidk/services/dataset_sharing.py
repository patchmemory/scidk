"""Read-only, bounded dataset projection from current ledger support.

Legacy graph membership is never export authority. No ontology, grants, evidence,
settings, filesystem contents or graph data is created by this service.
"""
from contextlib import closing
from pathlib import Path, PurePosixPath
import io
import json
import re
import sqlite3
import zipfile

from ..agent_tools.facts import FactDisclosure
from ..agent_tools.registry import available_tool_definitions
from ..agent_tools.security import DisclosureDenied
from .human_policy import HumanIdentity, resolve_workspace

MAX_FILES = 256
FIELDS = {'Dataset': {'name', 'description', 'modality'},
          'File': {'relative_path', 'size_bytes', 'extension', 'sha256'}}


def dataset_snapshot(ctx, dataset_id):
    """One snapshot; refuse unknown, unaccepted, hidden or oversized membership."""
    human = type(ctx.identity) is HumanIdentity
    if (not ctx.identity or ctx.identity.token_id or ctx.identity.channel not in {'chat', 'human'}
            or not isinstance(dataset_id, str) or not 1 <= len(dataset_id) <= 256
            or (not human and 'explain_fact' not in {d['name'] for d in available_tool_definitions(ctx)})
            or (human and (not ctx.knowledge_enabled or not ctx.knowledge))):
        raise DisclosureDenied()
    facts = ctx.knowledge.assertions.facts
    if not isinstance(facts, FactDisclosure) or facts.store.path != Path(ctx.settings_db).resolve():
        raise DisclosureDenied()
    with resolve_workspace(ctx, 'research_browse') as policy, closing(sqlite3.connect(
            facts.ledger.path.as_uri() + '?mode=ro', uri=True)) as conn:
        conn.execute('PRAGMA query_only=ON')
        conn.execute('BEGIN')
        provenance = []
        used_bytes = 0
        def read(fid):
            nonlocal used_bytes
            value = facts._fact(conn, policy, fid, True, set())
            used_bytes += len(json.dumps(value).encode('utf-8'))
            if used_bytes > 2 * 1024 * 1024:
                raise DisclosureDenied()
            provenance.append(value)
            return value
        def node(ref, label):
            value = facts._reference(conn, policy, ref, set())
            if value.get('label') != label:
                raise DisclosureDenied()
            read(value['fact_id'])
            return value
        node(dataset_id, 'Dataset')
        # Discovery stays internal. Every candidate edge must independently pass
        # current support, endpoint, source and evidence checks before release.
        rows = conn.execute("SELECT DISTINCT fact_id FROM assertions WHERE "
            "json_extract(body,'$.domain')='research' AND "
            "json_extract(body,'$.target_kind')='relationship' AND "
            "json_extract(body,'$.subject_ref')=? AND json_extract(body,'$.predicate')='CONTAINS' LIMIT ?",
            (dataset_id, MAX_FILES + 1)).fetchall()
        if not rows or len(rows) > MAX_FILES:
            raise DisclosureDenied()
        members = []
        for (fid,) in rows:
            edge = read(fid)
            ref = edge['object_ref']
            node(ref, 'File')
            if ref in members:
                raise DisclosureDenied()
            members.append(ref)
        def properties(ref, label):
            rows = conn.execute("SELECT DISTINCT fact_id FROM assertions WHERE "
                "json_extract(body,'$.domain')='research' AND json_extract(body,'$.target_kind')='property' "
                "AND json_extract(body,'$.target_ref')=? LIMIT 129", (ref,)).fetchall()
            if len(rows) > 128:
                raise DisclosureDenied()
            result = {}
            for (fid,) in rows:
                # Do not disclose or request fields outside this export's ceiling.
                claim = json.loads(conn.execute('SELECT body FROM assertions WHERE fact_id=? LIMIT 1', (fid,)).fetchone()[0])
                if claim['property_key'] in FIELDS[label]:
                    value = read(fid)
                    result[value['property_key']] = value['value']
            return result
        dataset = properties(dataset_id, 'Dataset')
        files = [dict(entity_ref=ref, **properties(ref, 'File')) for ref in sorted(members)]
        return {'dataset_id': dataset_id, 'dataset': dataset, 'files': files,
                'provenance': sorted(provenance, key=lambda f: f['fact_id']),
                'scope': 'Current authorized ledger Dataset and direct CONTAINS File members only.'}


def investigator_fields(body):
    from plugins.nih_dms.config import SHARING_MODES
    allowed = {'repository', 'retention_years', 'sharing_mode', 'access_contact', 'software', 'oversight'}
    if not isinstance(body, dict) or set(body) - allowed:
        raise ValueError('Invalid investigator fields')
    for value in body.values():
        if not isinstance(value, str) or len(value) > 1000 or any(ord(c) < 32 and c != '\n' for c in value):
            raise ValueError('Invalid investigator fields')
    result = {k: v.strip() for k, v in body.items() if v.strip()}
    if result.get('sharing_mode') and result['sharing_mode'] not in SHARING_MODES:
        raise ValueError('Invalid sharing mode')
    if result.get('retention_years') and not re.fullmatch(r'[1-9][0-9]{0,2}', result['retention_years']):
        raise ValueError('Invalid retention period')
    return result


def draft_plan(snapshot, fields):
    """Use the existing NIH renderer with selected-dataset facts only."""
    from plugins.nih_dms.graph_facts import GraphFacts, FormatRow
    from plugins.nih_dms.generator import render_plan
    groups = {}
    for file in snapshot['files']:
        ext, size = file.get('extension', ''), file.get('size_bytes')
        if not isinstance(ext, str) or (size is not None and (type(size) is not int or size < 0)):
            raise DisclosureDenied()
        count, total = groups.get(ext, (0, 0))
        groups[ext] = (count + 1, total + (size or 0))
    missing = sum('size_bytes' not in f for f in snapshot['files'])
    warnings = ['Selected dataset only; membership and metadata reflect current authorized ledger support. ',
                'No global graph, publication settings or schema scan was consulted. '
                'No PHI, consent or de-identification assessment has been performed.']
    if missing:
        warnings.append(f'{missing} files have unknown size; byte totals include known sizes only.')
    facts = GraphFacts(label_counts=(('Dataset', 1), ('File', len(snapshot['files']))),
        relationship_counts=(('CONTAINS', len(snapshot['files'])),), file_count=len(snapshot['files']),
        file_bytes=sum(t for _, t in groups.values()),
        formats=tuple(FormatRow(ext, count, total, 'Investigator to confirm', None)
                      for ext, (count, total) in sorted(groups.items())),
        repository=fields.get('repository'), retention_years=fields.get('retention_years'),
        sharing_mode=fields.get('sharing_mode'), access_contact=fields.get('access_contact'),
        warnings=tuple(warnings))
    return ('# Selected dataset — NIH DMS draft\n\nInvestigator review required. Not a compliance determination.\n\n'
            + snapshot['scope'] + '\n\n' + render_plan(facts)
            + '\n\n## Investigator-supplied details\n\n' + json.dumps(fields, indent=2, ensure_ascii=False)
            + '\n\n## Field provenance\n\n```json\n' + json.dumps(snapshot, indent=2, ensure_ascii=False)
            + '\n```\n')


def safe_relative(value):
    # Portable, deliberately conservative paths. Data is never shell source.
    if (not isinstance(value, str) or len(value) > 1024 or
            not re.fullmatch(r'[A-Za-z0-9_./ -]+', value) or
            any(part in {'', '.', '..'} or part.endswith((' ', '.')) or part.startswith('-')
                or part.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL',
                    *{f'COM{i}' for i in range(1, 10)}, *{f'LPT{i}' for i in range(1, 10)}}
                for part in value.split('/')) or PurePosixPath(value).is_absolute()):
        raise DisclosureDenied()
    return value


def sharing_package(snapshot, fields):
    paths, folded = [], set()
    for file in snapshot['files']:
        path = safe_relative(file.get('relative_path'))
        if path.casefold() in folded:
            raise DisclosureDenied()
        folded.add(path.casefold())
        paths.append(path)
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('nih-dms-plan-draft.md', draft_plan(snapshot, fields))
        archive.writestr('manifest.json', json.dumps(snapshot, indent=2))
        archive.writestr('files.txt', ''.join(p + '\n' for p in paths))
        archive.writestr('README.md', INSTRUCTIONS)
        archive.writestr('prepare.sh', SHELL_SCRIPT)
        archive.writestr('prepare.ps1', POWERSHELL_SCRIPT)
    return output.getvalue()


INSTRUCTIONS = '''# Dataset sharing preparation

1. Review manifest.json, field provenance and the draft NIH DMS plan. Confirm all
   files, consent, access restrictions and recipient/repository requirements.
2. Complete all six NIH elements, especially software and oversight; confirm
   repository, retention, contact and sharing mode with the investigator.
3. Extract this package to its own folder. Inspect files.txt and the scripts.
   SourceRoot must be the local folder relative to which files.txt paths apply.
4. Linux/macOS: bash prepare.sh /absolute/source/root /new/destination
   Windows: powershell -File ./prepare.ps1 -SourceRoot C:\\source -Destination C:\\new-package
   Use your normal approved execution policy; do not disable security controls.
5. Scripts list files first and require typing COPY. They create a new destination,
   copy only listed regular files, reject links and never overwrite or upload.
   On error, inspect the partial destination; scripts do not remove it.
6. Verify the staged files against your source (including expected hashes when
   available), review for sensitive content, then follow the chosen repository's
   instructions manually. Keep the manifest and draft with your review record.

This download contains instructions and metadata, not source file contents.
Authorization is checked at generation time. Recheck permission before copying
or sharing; an offline package cannot enforce later revocations. No de-identification,
encryption, NIH compliance, or upload is performed by these scripts.
'''

SHELL_SCRIPT = '''#!/usr/bin/env bash
set -euo pipefail
if [[ $# != 2 ]]; then echo "Usage: bash prepare.sh SOURCE_ROOT NEW_DESTINATION" >&2; exit 1; fi
package_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
if [[ -L "$1" ]]; then echo 'Source root must not be a link' >&2; exit 1; fi
source_root=$(cd -- "$1" && pwd -P)
destination=$2
if [[ -e "$destination" || -L "$destination" ]]; then echo 'Destination must not exist' >&2; exit 1; fi
while IFS= read -r relative; do
  [[ -n "$relative" && "$relative" != /* && "$relative" != *\\\\* ]] || exit 1
  IFS='/' read -ra parts <<< "$relative"
  current=$source_root
  for part in "${parts[@]}"; do
    [[ -n "$part" && "$part" != . && "$part" != .. ]] || exit 1
    current="$current/$part"
    [[ ! -L "$current" ]] || { echo 'Links refused' >&2; exit 1; }
  done
  [[ -f "$current" ]] || { echo 'Missing regular file' >&2; exit 1; }
  printf '%s\\n' "$relative"
done < "$package_dir/files.txt"
read -r -p 'Review listed files. Type COPY to create a local copy: ' confirmation
[[ "$confirmation" == COPY ]] || exit 1
mkdir -- "$destination"
while IFS= read -r relative; do
  current=$source_root
  IFS='/' read -ra parts <<< "$relative"
  for part in "${parts[@]}"; do current="$current/$part"; [[ ! -L "$current" ]] || exit 1; done
  [[ -f "$current" ]] || exit 1
  mkdir -p -- "$destination/$(dirname -- "$relative")"
  cp -n -- "$current" "$destination/$relative"
done < "$package_dir/files.txt"
echo 'Local copy complete. Verify contents and review before sharing; nothing was uploaded.'
'''

POWERSHELL_SCRIPT = '''param([Parameter(Mandatory=$true)][string]$SourceRoot,
      [Parameter(Mandatory=$true)][string]$Destination)
$ErrorActionPreference = 'Stop'
$rootItem = Get-Item -LiteralPath $SourceRoot -Force
if (-not $rootItem.PSIsContainer -or ($rootItem.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Invalid source root' }
$root = $rootItem.FullName
if (Test-Path -LiteralPath $Destination) { throw 'Destination must not exist' }
$paths = @(Get-Content -LiteralPath (Join-Path $PSScriptRoot 'files.txt'))
function CheckedSource([string]$relative) {
  if (-not $relative -or [IO.Path]::IsPathRooted($relative) -or $relative.Contains('\\') -or $relative.Contains(':')) { throw 'Invalid relative path' }
  $current = $root
  foreach ($part in $relative.Split('/')) {
    if (-not $part -or $part -eq '.' -or $part -eq '..') { throw 'Unsafe path' }
    $current = Join-Path $current $part
    $item = Get-Item -LiteralPath $current -Force
    if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Links refused' }
  }
  if ((Get-Item -LiteralPath $current -Force).PSIsContainer) { throw 'Not a regular file' }
  return $current
}
foreach ($relative in $paths) { $null = CheckedSource $relative; Write-Output $relative }
if ((Read-Host 'Review listed files. Type COPY to create a local copy') -cne 'COPY') { throw 'Cancelled' }
$null = [IO.Directory]::CreateDirectory((Split-Path -Parent ([IO.Path]::GetFullPath($Destination))))
$null = New-Item -ItemType Directory -Path $Destination
foreach ($relative in $paths) {
  $source = CheckedSource $relative
  $target = Join-Path $Destination $relative
  $null = [IO.Directory]::CreateDirectory((Split-Path -Parent $target))
  [IO.File]::Copy($source, $target, $false)
}
Write-Output 'Local copy complete. Verify contents and review before sharing; nothing was uploaded.'
'''
