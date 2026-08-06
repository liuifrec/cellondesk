from __future__ import annotations

import html
import json
from collections import Counter
from pathlib import Path
from typing import Any

from .sources.census import CensusGenePreview


def _escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def _top_counts(records: list[dict[str, Any]], field: str, limit: int = 12) -> list[tuple[str, int]]:
    counts = Counter(str(record.get(field, "Missing")) for record in records)
    return counts.most_common(limit)


def render_census_report(
    preview: CensusGenePreview,
    *,
    title: str = "CellOnDesk Census Gene Preview",
) -> str:
    payload = json.dumps(preview.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    query_rows = "".join(
        f"<tr><th>{_escape(name)}</th><td>{_escape(value if value is not None else '—')}</td></tr>"
        for name, value in preview.query.model_dump().items()
    )
    breakdowns = []
    for field in ("cell_type", "tissue_general", "disease", "assay", "dataset_id"):
        rows = "".join(
            f"<tr><td>{_escape(label)}</td><td>{count:,}</td></tr>"
            for label, count in _top_counts(preview.cell_metadata, field)
        ) or '<tr><td colspan="2">No metadata available</td></tr>'
        breakdowns.append(f"<section><h3>{_escape(field)}</h3><table>{rows}</table></section>")
    warnings = "".join(f"<li>{_escape(item)}</li>" for item in preview.warnings) or "<li>No warnings.</li>"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{_escape(title)}</title>
<style>
:root{{--ink:#23313a;--muted:#65737d;--line:#d8e0e5;--bg:#f4f6f8;--accent:#167f9c;--warn:#e9a23b}}*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}header{{padding:24px 30px;background:#253942;color:#fff}}header h1{{margin:0}}header p{{margin:5px 0 0;color:#ced9dd}}main{{max-width:1300px;margin:auto;padding:24px}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:14px}}.card{{background:#fff;border:1px solid var(--line);border-radius:7px;padding:18px;margin-bottom:16px}}.metric strong{{display:block;font-size:27px;color:var(--accent)}}.metric span,.muted{{color:var(--muted)}}canvas{{width:100%;height:320px;border:1px solid var(--line);background:#fff}}table{{width:100%;border-collapse:collapse}}th,td{{text-align:left;padding:8px;border-bottom:1px solid #e5eaed}}th{{color:var(--muted);width:210px}}.breakdowns{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px}}.warning{{border-left:5px solid var(--warn)}}code{{word-break:break-all}}</style></head>
<body><header><h1>{_escape(title)}</h1><p>{_escape(preview.matched_gene)} · CELLxGENE Census { _escape(preview.query.census_version) } · bounded SOMA retrieval</p></header><main>
<div class="grid">
<div class="card metric"><strong>{preview.total_matching_cells:,}</strong><span>Matching cells</span></div>
<div class="card metric"><strong>{preview.sampled_cells:,}</strong><span>Materialized cells</span></div>
<div class="card metric"><strong>{preview.nonzero_sampled:,}</strong><span>Non-zero sampled</span></div>
<div class="card metric"><strong>{preview.maximum if preview.maximum is not None else '—'}</strong><span>Maximum</span></div>
<div class="card metric"><strong>{preview.p95 if preview.p95 is not None else '—'}</strong><span>95th percentile</span></div>
</div>
<div class="card"><h2>Expression distribution</h2><canvas id="histogram" width="1100" height="320"></canvas><p class="muted">Histogram of the bounded expression slice. Zero values are retained.</p></div>
<div class="card"><h2>Metadata composition</h2><div class="breakdowns">{''.join(breakdowns)}</div></div>
<div class="card"><h2>Query provenance</h2><table>{query_rows}<tr><th>Matched feature</th><td>{_escape(preview.matched_gene)}</td></tr><tr><th>Feature ID</th><td>{_escape(preview.feature_id or '—')}</td></tr></table></div>
<div class="card warning"><h2>Notes</h2><ul>{warnings}</ul></div>
</main><script type="application/json" id="report-data">{payload}</script><script>
const data=JSON.parse(document.getElementById('report-data').textContent),canvas=document.getElementById('histogram'),ctx=canvas.getContext('2d');
function drawHistogram(){{const values=data.values.filter(Number.isFinite),bins=30;if(!values.length){{ctx.fillStyle='#65737d';ctx.font='18px sans-serif';ctx.fillText('No finite expression values.',40,60);return;}}const min=Math.min(...values),max=Math.max(...values),counts=Array(bins).fill(0);for(const value of values){{const index=max===min?0:Math.min(bins-1,Math.floor((value-min)/(max-min)*bins));counts[index]++;}}const peak=Math.max(...counts),pad=35,w=(canvas.width-2*pad)/bins;ctx.clearRect(0,0,canvas.width,canvas.height);ctx.fillStyle='#167f9c';counts.forEach((count,index)=>{{const h=(canvas.height-2*pad)*(count/(peak||1));ctx.fillRect(pad+index*w,canvas.height-pad-h,Math.max(1,w-2),h);}});ctx.fillStyle='#65737d';ctx.font='13px sans-serif';ctx.fillText(min.toFixed(2),pad,canvas.height-10);ctx.fillText(max.toFixed(2),canvas.width-pad-45,canvas.height-10);}}drawHistogram();
</script></body></html>"""


def write_census_report(preview: CensusGenePreview, destination: str | Path) -> Path:
    destination = Path(destination)
    destination.write_text(render_census_report(preview), encoding="utf-8")
    return destination


__all__ = ["render_census_report", "write_census_report"]
