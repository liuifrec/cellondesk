from __future__ import annotations

import html
import json
from collections import Counter
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import DatasetRecord


def _escape(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _counts(records: list[DatasetRecord], field: str) -> Counter[str]:
    values = [getattr(record, field) or "Not reported" for record in records]
    return Counter(values)


def _distribution_rows(counts: Counter[str], total: int) -> str:
    rows: list[str] = []
    for label, count in counts.most_common():
        percent = 0 if total == 0 else 100 * count / total
        rows.append(
            f'<div class="bar-row"><div class="bar-label">{_escape(label)}</div>'
            f'<div class="bar-track"><span style="width:{percent:.2f}%"></span></div>'
            f'<div class="bar-value">{count}</div></div>'
        )
    return "".join(rows) or '<p class="muted">No values available.</p>'


def render_html_report(
    records: Iterable[DatasetRecord],
    *,
    title: str = "CellOnDesk Web Summary",
    query: Mapping[str, Any] | None = None,
) -> str:
    """Render a self-contained, offline HTML dashboard for normalized datasets."""
    items = list(records)
    total = len(items)
    published = sum((record.status or "").lower() == "published" for record in items)
    public_access = sum((record.access_level or "").lower() == "public" for record in items)
    with_doi = sum(bool(record.doi_url) for record in items)
    with_donor = sum(bool(record.donor_id) for record in items)
    missing_fields = {
        "assay": sum(not record.dataset_type for record in items),
        "organ": sum(not record.organ for record in items),
        "access level": sum(not record.access_level for record in items),
    }
    warnings = [
        f"{count} dataset{'s' if count != 1 else ''} missing {label}."
        for label, count in missing_fields.items()
        if count
    ]
    query = dict(query or {})
    generated = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    records_json = json.dumps(
        [record.model_dump(mode="json") for record in items],
        ensure_ascii=False,
        separators=(",", ":"),
    ).replace("</", "<\\/")
    query_json = json.dumps(query, ensure_ascii=False, separators=(",", ":")).replace(
        "</", "<\\/"
    )

    table_rows = []
    for index, record in enumerate(items):
        portal = (
            f'<a href="{_escape(record.portal_url)}" target="_blank" rel="noopener">'
            f"{_escape(record.dataset_id)}</a>"
            if record.portal_url
            else _escape(record.dataset_id)
        )
        doi = (
            f'<a href="{_escape(record.doi_url)}" target="_blank" rel="noopener">DOI</a>'
            if record.doi_url
            else "—"
        )
        search_text = " ".join(
            filter(
                None,
                [
                    record.source,
                    record.dataset_id,
                    record.title,
                    record.dataset_type,
                    record.organ,
                    record.status,
                    record.access_level,
                    record.donor_id,
                ],
            )
        ).lower()
        table_rows.append(
            f'<tr data-search="{_escape(search_text)}" data-index="{index}">'
            f"<td>{portal}</td><td>{_escape(record.dataset_type or '—')}</td>"
            f"<td>{_escape(record.organ or '—')}</td>"
            f"<td>{_escape(record.status or '—')}</td>"
            f"<td>{_escape(record.access_level or '—')}</td>"
            f"<td>{_escape(record.donor_id or '—')}</td>"
            f"<td class=\"title-cell\">{_escape(record.title)}</td><td>{doi}</td></tr>"
        )

    warning_html = "".join(f"<li>{_escape(warning)}</li>" for warning in warnings)
    if not warning_html:
        warning_html = "<li>No metadata completeness warnings.</li>"
    query_rows = "".join(
        f"<tr><th>{_escape(key)}</th><td>{_escape(value if value is not None else 'Any')}</td></tr>"
        for key, value in query.items()
    ) or '<tr><th>Query</th><td>Not recorded</td></tr>'

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_escape(title)}</title>
<style>
:root{{--ink:#25313b;--muted:#65727d;--line:#d9e0e5;--panel:#fff;--bg:#f4f6f8;--accent:#1688a7;--accent2:#74c6d5;--warn:#f6b44b}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}
header{{background:#243640;color:white;padding:22px 30px}} header h1{{margin:0;font-size:25px}} header p{{margin:4px 0 0;color:#cbd7dc}}
nav{{position:sticky;top:0;z-index:2;background:#fff;border-bottom:1px solid var(--line);padding:0 28px}}
nav button{{border:0;background:none;padding:15px 17px;font-weight:650;color:var(--muted);cursor:pointer;border-bottom:3px solid transparent}}
nav button.active{{color:var(--accent);border-bottom-color:var(--accent)}}
main{{max-width:1400px;margin:auto;padding:24px}} .tab{{display:none}} .tab.active{{display:block}}
.grid{{display:grid;gap:16px}} .metrics{{grid-template-columns:repeat(auto-fit,minmax(170px,1fr))}} .two{{grid-template-columns:repeat(auto-fit,minmax(330px,1fr))}}
.card{{background:var(--panel);border:1px solid var(--line);border-radius:7px;padding:18px;box-shadow:0 1px 2px #0000000d}}
.metric strong{{display:block;font-size:29px;color:var(--accent)}} .metric span,.muted{{color:var(--muted)}} h2{{font-size:19px;margin:0 0 14px}} h3{{font-size:15px;margin:0 0 12px}}
.warning{{border-left:5px solid var(--warn)}} .warning ul{{margin:0;padding-left:20px}}
.bar-row{{display:grid;grid-template-columns:minmax(105px,1fr) 3fr 38px;gap:10px;align-items:center;margin:9px 0}} .bar-label{{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.bar-track{{height:12px;background:#e9eef1;border-radius:6px;overflow:hidden}} .bar-track span{{display:block;height:100%;background:linear-gradient(90deg,var(--accent),var(--accent2))}}
.bar-value{{text-align:right;font-variant-numeric:tabular-nums}} input[type=search]{{width:min(520px,100%);padding:10px 12px;border:1px solid #bfc9cf;border-radius:5px;margin-bottom:14px}}
.table-wrap{{overflow:auto;max-height:68vh;border:1px solid var(--line)}} table{{width:100%;border-collapse:collapse;background:#fff}} th,td{{padding:9px 11px;border-bottom:1px solid #e6ebee;text-align:left;vertical-align:top}} thead th{{position:sticky;top:0;background:#edf2f4;z-index:1}} tbody tr:hover{{background:#f2fafb}} .title-cell{{min-width:260px}} a{{color:#087d9c}}
.kv th{{width:170px;color:var(--muted)}} pre{{white-space:pre-wrap;word-break:break-word;background:#f7f9fa;border:1px solid var(--line);padding:14px;max-height:440px;overflow:auto}}
footer{{color:var(--muted);padding:5px 30px 25px;text-align:center}} @media print{{nav,input{{display:none}} .tab{{display:block!important;break-before:page}} .table-wrap{{max-height:none;overflow:visible}}}}
</style>
</head>
<body>
<header><h1>{_escape(title)}</h1><p>{total} dataset records · generated {generated}</p></header>
<nav>
<button class="active" data-tab="summary">Summary</button><button data-tab="datasets">Datasets</button><button data-tab="provenance">Provenance</button>
</nav>
<main>
<section id="summary" class="tab active">
<div class="grid metrics">
<div class="card metric"><strong>{total}</strong><span>Datasets</span></div>
<div class="card metric"><strong>{published}</strong><span>Published</span></div>
<div class="card metric"><strong>{public_access}</strong><span>Explicitly public</span></div>
<div class="card metric"><strong>{len(_counts(items, 'dataset_type')) if items else 0}</strong><span>Assay types</span></div>
<div class="card metric"><strong>{len(_counts(items, 'organ')) if items else 0}</strong><span>Organs</span></div>
<div class="card metric"><strong>{with_doi}</strong><span>With DOI</span></div>
<div class="card metric"><strong>{with_donor}</strong><span>With donor ID</span></div>
</div>
<div class="grid two" style="margin-top:16px">
<div class="card"><h2>Assay distribution</h2>{_distribution_rows(_counts(items, 'dataset_type'), total)}</div>
<div class="card"><h2>Organ distribution</h2>{_distribution_rows(_counts(items, 'organ'), total)}</div>
<div class="card"><h2>Access distribution</h2>{_distribution_rows(_counts(items, 'access_level'), total)}</div>
<div class="card warning"><h2>Metadata checks</h2><ul>{warning_html}</ul></div>
<div class="card"><h2>Interpretation</h2><p>This dashboard describes portal metadata and selection provenance. Published status and public download access are not treated as the same thing. It is not an experimental QC report and does not infer sequencing quality, tissue quality, or biological validity.</p></div>
</div>
</section>
<section id="datasets" class="tab">
<div class="card"><h2>Dataset inventory</h2><input id="filter" type="search" placeholder="Filter by ID, assay, organ, access, donor, status, or title…"><span id="visible-count" class="muted"></span>
<div class="table-wrap"><table><thead><tr><th>Dataset</th><th>Assay</th><th>Organ</th><th>Status</th><th>Access</th><th>Donor</th><th>Title</th><th>Citation</th></tr></thead><tbody>{''.join(table_rows)}</tbody></table></div></div>
</section>
<section id="provenance" class="tab">
<div class="grid two"><div class="card"><h2>Search parameters</h2><table class="kv"><tbody>{query_rows}</tbody></table></div>
<div class="card"><h2>Report provenance</h2><table class="kv"><tbody><tr><th>Generator</th><td>CellOnDesk</td></tr><tr><th>Format</th><td>Self-contained HTML</td></tr><tr><th>Generated</th><td>{generated}</td></tr><tr><th>Records embedded</th><td>{total}</td></tr></tbody></table></div></div>
<div class="card" style="margin-top:16px"><h2>Selected record metadata</h2><p class="muted">Choose a row in the Datasets tab to display its normalized and source metadata here.</p><pre id="record-detail">No dataset selected.</pre></div>
</section>
</main>
<footer>CellOnDesk compact web summary · all data are embedded in this file.</footer>
<script type="application/json" id="records-data">{records_json}</script>
<script type="application/json" id="query-data">{query_json}</script>
<script>
const records=JSON.parse(document.getElementById('records-data').textContent);
const tabs=document.querySelectorAll('nav button'); tabs.forEach(b=>b.addEventListener('click',()=>{{tabs.forEach(x=>x.classList.remove('active'));document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));b.classList.add('active');document.getElementById(b.dataset.tab).classList.add('active')}}));
const rows=[...document.querySelectorAll('tbody tr[data-search]')], filter=document.getElementById('filter'), count=document.getElementById('visible-count');
function applyFilter(){{const q=filter.value.trim().toLowerCase();let shown=0;rows.forEach(r=>{{const ok=!q||r.dataset.search.includes(q);r.hidden=!ok;if(ok)shown++}});count.textContent=`${{shown}} of ${{rows.length}} shown`;}} filter.addEventListener('input',applyFilter);applyFilter();
rows.forEach(r=>r.addEventListener('click',()=>{{document.getElementById('record-detail').textContent=JSON.stringify(records[Number(r.dataset.index)],null,2);tabs.forEach(x=>x.classList.toggle('active',x.dataset.tab==='provenance'));document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('active',x.id==='provenance'));}}));
</script>
</body></html>"""


def write_html_report(
    records: Iterable[DatasetRecord],
    destination: str | Path,
    *,
    title: str = "CellOnDesk Web Summary",
    query: Mapping[str, Any] | None = None,
) -> Path:
    destination = Path(destination)
    destination.write_text(
        render_html_report(records, title=title, query=query), encoding="utf-8"
    )
    return destination
