from __future__ import annotations

import html
import json
from pathlib import Path

from .expression import GeneExpressionPreview
from .inspection import H5ADInspection


def _escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def render_gene_expression_report(
    inspection: H5ADInspection,
    expression: GeneExpressionPreview,
    *,
    title: str = "CellOnDesk Gene Expression Preview",
) -> str:
    payload = json.dumps(
        {
            "inspection": inspection.model_dump(mode="json"),
            "expression": expression.model_dump(mode="json"),
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ).replace("</", "<\\/")
    options = "".join(
        f'<option value="{index}">{_escape(item.key)} '
        f'({len(item.sampled_points):,} sampled)</option>'
        for index, item in enumerate(inspection.embeddings)
        if item.key in expression.embedding_values
    )
    if not options:
        options = '<option value="">No aligned embedding available</option>'
    warnings = "".join(
        f"<li>{_escape(item)}</li>"
        for item in [*inspection.warnings, *expression.warnings]
    ) or "<li>No warnings.</li>"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{_escape(title)}</title>
<style>
:root{{--ink:#23313a;--muted:#65737d;--line:#d8e0e5;--bg:#f4f6f8;--accent:#167f9c;--warn:#e9a23b}}*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}header{{padding:24px 30px;background:#253942;color:#fff}}header h1{{margin:0}}header p{{margin:5px 0 0;color:#ced9dd}}main{{max-width:1300px;margin:auto;padding:24px}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:14px}}.card{{background:#fff;border:1px solid var(--line);border-radius:7px;padding:18px;margin-bottom:16px}}.metric strong{{display:block;font-size:27px;color:var(--accent)}}.metric span,.muted{{color:var(--muted)}}.controls{{display:flex;gap:12px;align-items:center;margin-bottom:12px;flex-wrap:wrap}}select{{padding:8px}}canvas{{width:100%;height:min(68vh,680px);border:1px solid var(--line);background:#fff}}.bar{{height:12px;background:linear-gradient(90deg,#e8eef1,#2c7fb8,#d7301f);border-radius:6px}}.warning{{border-left:5px solid var(--warn)}}table{{width:100%;border-collapse:collapse}}th,td{{text-align:left;padding:8px;border-bottom:1px solid #e5eaed}}th{{color:var(--muted);width:210px}}code{{word-break:break-all}}</style></head>
<body><header><h1>{_escape(title)}</h1><p>{_escape(inspection.file_name)} · {_escape(expression.matched_gene)} from {_escape(expression.matrix_source)} · sampled without loading the complete matrix</p></header><main>
<div class="grid">
<div class="card metric"><strong>{inspection.n_obs:,}</strong><span>Total observations</span></div>
<div class="card metric"><strong>{expression.sampled_observations:,}</strong><span>Sampled observations</span></div>
<div class="card metric"><strong>{expression.nonzero_sampled:,}</strong><span>Non-zero sampled</span></div>
<div class="card metric"><strong>{expression.maximum if expression.maximum is not None else '—'}</strong><span>Sample maximum</span></div>
<div class="card metric"><strong>{expression.p95 if expression.p95 is not None else '—'}</strong><span>Sample p95</span></div>
</div>
<div class="card"><div class="controls"><label><strong>Embedding</strong></label><select id="view">{options}</select><span id="count" class="muted"></span></div><canvas id="plot" width="1100" height="700"></canvas><div class="bar"></div><p class="muted">Low expression → high expression. Values above the sampled 95th percentile share the upper color range.</p></div>
<div class="card"><h2>Gene lookup</h2><table><tr><th>Requested</th><td>{_escape(expression.requested_gene)}</td></tr><tr><th>Matched</th><td>{_escape(expression.matched_gene)}</td></tr><tr><th>Matched field</th><td>{_escape(expression.matched_field)}</td></tr><tr><th>Feature index</th><td>{expression.feature_index}</td></tr><tr><th>Matrix</th><td>{_escape(expression.matrix_source)}</td></tr><tr><th>Source</th><td><code>{_escape(inspection.source_path)}</code></td></tr></table></div>
<div class="card warning"><h2>Notes</h2><ul>{warnings}</ul></div>
</main><script type="application/json" id="report-data">{payload}</script><script>
const data=JSON.parse(document.getElementById('report-data').textContent),view=document.getElementById('view'),canvas=document.getElementById('plot'),ctx=canvas.getContext('2d'),count=document.getElementById('count');const available=data.inspection.embeddings.filter(e=>Object.prototype.hasOwnProperty.call(data.expression.embedding_values,e.key));
function color(value,max){{if(value===null||!Number.isFinite(value))return '#b7c0c5';const t=Math.max(0,Math.min(1,value/(max||1)));const hue=210-200*t;return `hsl(${{hue}} 70% ${{58-12*t}}%)`;}}
function draw(){{ctx.clearRect(0,0,canvas.width,canvas.height);if(!available.length){{ctx.fillStyle='#65737d';ctx.font='18px sans-serif';ctx.fillText('No aligned two-dimensional embedding found.',40,60);return;}}const item=available[Number(view.value)||0],pts=item.sampled_points,vals=data.expression.embedding_values[item.key]||[],xs=pts.map(p=>p[0]),ys=pts.map(p=>p[1]),xmin=Math.min(...xs),xmax=Math.max(...xs),ymin=Math.min(...ys),ymax=Math.max(...ys),pad=30,sx=(canvas.width-2*pad)/(xmax-xmin||1),sy=(canvas.height-2*pad)/(ymax-ymin||1),cap=data.expression.p95||data.expression.maximum||1;for(let i=0;i<pts.length;i++){{ctx.fillStyle=color(vals[i],cap);ctx.beginPath();ctx.arc(pad+(pts[i][0]-xmin)*sx,canvas.height-pad-(pts[i][1]-ymin)*sy,2.3,0,Math.PI*2);ctx.fill();}}count.textContent=`${{pts.length.toLocaleString()}} points · ${{item.key}}`;}}view.addEventListener('change',draw);draw();
</script></body></html>"""


def write_gene_expression_report(
    inspection: H5ADInspection,
    expression: GeneExpressionPreview,
    destination: str | Path,
) -> Path:
    destination = Path(destination)
    destination.write_text(
        render_gene_expression_report(inspection, expression),
        encoding="utf-8",
    )
    return destination
