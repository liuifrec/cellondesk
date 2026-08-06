from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from .inspection import H5ADInspection


def _escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def _format_bytes(value: int) -> str:
    units = ("B", "KB", "MB", "GB", "TB")
    amount = float(value)
    for unit in units:
        if abs(amount) < 1024 or unit == units[-1]:
            return f"{amount:.1f} {unit}"
        amount /= 1024
    return f"{value} B"


def _format_number(value: float | None) -> str:
    if value is None:
        return "—"
    if abs(value) >= 1000 or (value and abs(value) < 0.001):
        return f"{value:.3g}"
    return f"{value:.3f}".rstrip("0").rstrip(".")


def _column_rows(columns: list[Any]) -> str:
    rows: list[str] = []
    for column in columns:
        top = ", ".join(
            f"{item.value} ({item.count})" for item in column.top_values[:5]
        )
        if column.numeric:
            detail = (
                f"median {_format_number(column.numeric.median)}; "
                f"p05–p95 {_format_number(column.numeric.p05)}–"
                f"{_format_number(column.numeric.p95)}"
            )
        else:
            detail = top or "—"
        sampled = "sampled" if column.sampled else "complete"
        rows.append(
            "<tr>"
            f"<td>{_escape(column.name)}</td>"
            f"<td>{_escape(column.dtype)}</td>"
            f"<td>{_escape(column.encoding)}</td>"
            f"<td>{_escape(sampled)}</td>"
            f"<td>{_escape(detail)}</td>"
            "</tr>"
        )
    return "".join(rows) or '<tr><td colspan="5">No columns found.</td></tr>'


def render_h5ad_report(
    inspection: H5ADInspection,
    *,
    title: str = "CellOnDesk H5AD Summary",
) -> str:
    """Render a self-contained HTML dashboard for a local H5AD inspection."""
    payload = json.dumps(
        inspection.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
    ).replace("</", "<\\/")
    matrix = inspection.matrix
    density = f"{matrix.density * 100:.3f}%" if matrix.density is not None else "—"
    warnings = "".join(f"<li>{_escape(item)}</li>" for item in inspection.warnings)
    warnings = warnings or "<li>No structural warnings.</li>"
    embedding_options = "".join(
        f'<option value="{index}">{_escape(item.key)} '
        f'({len(item.sampled_points):,} sampled)</option>'
        for index, item in enumerate(inspection.embeddings)
    )
    if not embedding_options:
        embedding_options = '<option value="">No preview available</option>'

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_escape(title)}</title>
<style>
:root{{--ink:#23313a;--muted:#65737d;--line:#d8e0e5;--panel:#fff;--bg:#f4f6f8;--accent:#167f9c;--warn:#e9a23b}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}
header{{padding:23px 30px;background:#253942;color:white}}header h1{{margin:0;font-size:25px}}header p{{margin:5px 0 0;color:#ced9dd}}
nav{{position:sticky;top:0;z-index:3;background:#fff;border-bottom:1px solid var(--line);padding:0 28px}}
nav button{{padding:14px 17px;border:0;border-bottom:3px solid transparent;background:none;color:var(--muted);font-weight:650;cursor:pointer}}
nav button.active{{color:var(--accent);border-bottom-color:var(--accent)}}main{{max-width:1400px;margin:auto;padding:24px}}
.tab{{display:none}}.tab.active{{display:block}}.grid{{display:grid;gap:16px}}.metrics{{grid-template-columns:repeat(auto-fit,minmax(170px,1fr))}}.two{{grid-template-columns:repeat(auto-fit,minmax(350px,1fr))}}
.card{{background:var(--panel);border:1px solid var(--line);border-radius:7px;padding:18px;box-shadow:0 1px 2px #0000000d}}.metric strong{{display:block;font-size:28px;color:var(--accent)}}.metric span,.muted{{color:var(--muted)}}
h2{{font-size:18px;margin:0 0 13px}}.warning{{border-left:5px solid var(--warn)}}.warning ul{{margin:0;padding-left:20px}}
table{{width:100%;border-collapse:collapse}}th,td{{padding:9px 10px;border-bottom:1px solid #e5eaed;text-align:left;vertical-align:top}}th{{background:#edf2f4;position:sticky;top:0}}.table-wrap{{max-height:65vh;overflow:auto;border:1px solid var(--line)}}
.controls{{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-bottom:12px}}select{{padding:8px 10px;border:1px solid #bcc7cd;border-radius:5px;background:white}}canvas{{display:block;width:100%;height:min(68vh,680px);background:#fff;border:1px solid var(--line);border-radius:5px}}
.legend{{display:flex;flex-wrap:wrap;gap:7px 13px;margin-top:10px;max-height:105px;overflow:auto}}.legend-item{{display:flex;gap:5px;align-items:center;font-size:12px}}.swatch{{width:10px;height:10px;border-radius:50%}}
.kv th{{position:static;width:190px;color:var(--muted)}}code{{word-break:break-all}}footer{{padding:0 24px 25px;text-align:center;color:var(--muted)}}
@media print{{nav{{display:none}}.tab{{display:block!important;break-before:page}}canvas{{height:500px}}.table-wrap{{max-height:none;overflow:visible}}}}
</style>
</head>
<body>
<header><h1>{_escape(title)}</h1><p>{_escape(inspection.file_name)} · structure inspected directly from HDF5 without loading the complete expression matrix</p></header>
<nav><button class="active" data-tab="summary">Summary</button><button data-tab="embeddings">Embeddings</button><button data-tab="metadata">Metadata</button><button data-tab="provenance">Provenance</button></nav>
<main>
<section id="summary" class="tab active">
<div class="grid metrics">
<div class="card metric"><strong>{inspection.n_obs:,}</strong><span>Cells / observations</span></div>
<div class="card metric"><strong>{inspection.n_vars:,}</strong><span>Genes / variables</span></div>
<div class="card metric"><strong>{_format_bytes(inspection.file_size_bytes)}</strong><span>File size</span></div>
<div class="card metric"><strong>{density}</strong><span>Matrix density</span></div>
<div class="card metric"><strong>{len(inspection.layers)}</strong><span>Layers</span></div>
<div class="card metric"><strong>{len(inspection.embeddings)}</strong><span>Previewable embeddings</span></div>
</div>
<div class="grid two" style="margin-top:16px">
<div class="card"><h2>Expression matrix</h2><table class="kv"><tbody>
<tr><th>Shape</th><td>{matrix.shape[0]:,} × {matrix.shape[1]:,}</td></tr>
<tr><th>Encoding</th><td>{_escape(matrix.encoding)}</td></tr>
<tr><th>Data type</th><td>{_escape(matrix.dtype or 'Not reported')}</td></tr>
<tr><th>Non-zero entries</th><td>{f'{matrix.nnz:,}' if matrix.nnz is not None else 'Sampled only'}</td></tr>
<tr><th>Sample range</th><td>{_format_number(matrix.sample_minimum)} to {_format_number(matrix.sample_maximum)}</td></tr>
<tr><th>Sample mean</th><td>{_format_number(matrix.sample_mean)}</td></tr>
</tbody></table></div>
<div class="card"><h2>Available structures</h2><table class="kv"><tbody>
<tr><th>Annotation field</th><td>{_escape(inspection.likely_annotation or 'Not detected')}</td></tr>
<tr><th>obsm</th><td>{_escape(', '.join(inspection.obsm) or 'None')}</td></tr>
<tr><th>layers</th><td>{_escape(', '.join(inspection.layers) or 'None')}</td></tr>
<tr><th>uns</th><td>{_escape(', '.join(inspection.uns[:30]) or 'None')}</td></tr>
<tr><th>raw</th><td>{'Present' if inspection.has_raw else 'Absent'}</td></tr>
</tbody></table></div>
<div class="card warning"><h2>Inspection notes</h2><ul>{warnings}</ul></div>
<div class="card"><h2>Interpretation</h2><p>This is a structural and sampled metadata preview. It does not claim sequencing, tissue, segmentation, or biological quality. Numeric and free-text column summaries may be sampled to keep inspection bounded in memory and time.</p></div>
</div>
</section>
<section id="embeddings" class="tab">
<div class="card"><div class="controls"><label for="embedding-select"><strong>View</strong></label><select id="embedding-select">{embedding_options}</select><span id="point-count" class="muted"></span></div><canvas id="embedding-canvas" width="1100" height="700"></canvas><div id="legend" class="legend"></div></div>
</section>
<section id="metadata" class="tab">
<div class="card"><h2>Observation columns</h2><p class="muted">{len(inspection.obs_column_names)} total columns; {len(inspection.obs_columns)} shown with detailed summaries.</p><div class="table-wrap"><table><thead><tr><th>Name</th><th>Dtype</th><th>Encoding</th><th>Coverage</th><th>Preview</th></tr></thead><tbody>{_column_rows(inspection.obs_columns)}</tbody></table></div></div>
<div class="card" style="margin-top:16px"><h2>Variable columns</h2><p class="muted">{len(inspection.var_column_names)} total columns; {len(inspection.var_columns)} shown with detailed summaries.</p><div class="table-wrap"><table><thead><tr><th>Name</th><th>Dtype</th><th>Encoding</th><th>Coverage</th><th>Preview</th></tr></thead><tbody>{_column_rows(inspection.var_columns)}</tbody></table></div></div>
</section>
<section id="provenance" class="tab"><div class="card"><h2>File provenance</h2><table class="kv"><tbody><tr><th>Source path</th><td><code>{_escape(inspection.source_path)}</code></td></tr><tr><th>Generator</th><td>CellOnDesk</td></tr><tr><th>Reader</th><td>Direct HDF5 structural inspection</td></tr><tr><th>Expression loading</th><td>Full matrix not loaded</td></tr><tr><th>Embedded points</th><td>{sum(len(item.sampled_points) for item in inspection.embeddings):,}</td></tr></tbody></table></div></section>
</main>
<footer>CellOnDesk local H5AD summary · all report data and scripts are embedded in this file.</footer>
<script type="application/json" id="inspection-data">{payload}</script>
<script>
const data=JSON.parse(document.getElementById('inspection-data').textContent);
const tabs=[...document.querySelectorAll('nav button')];tabs.forEach(button=>button.addEventListener('click',()=>{{tabs.forEach(item=>item.classList.remove('active'));document.querySelectorAll('.tab').forEach(item=>item.classList.remove('active'));button.classList.add('active');document.getElementById(button.dataset.tab).classList.add('active');if(button.dataset.tab==='embeddings')draw();}}));
const select=document.getElementById('embedding-select'),canvas=document.getElementById('embedding-canvas'),ctx=canvas.getContext('2d'),legend=document.getElementById('legend'),count=document.getElementById('point-count');
function hue(label){{let h=2166136261;for(let i=0;i<label.length;i++){{h^=label.charCodeAt(i);h=Math.imul(h,16777619);}}return Math.abs(h)%360;}}
function draw(){{ctx.clearRect(0,0,canvas.width,canvas.height);legend.innerHTML='';if(!data.embeddings.length){{ctx.fillStyle='#65737d';ctx.font='18px sans-serif';ctx.fillText('No previewable embedding found.',40,60);count.textContent='';return;}}const item=data.embeddings[Number(select.value)||0],pts=item.sampled_points;if(!pts.length)return;const xs=pts.map(p=>p[0]),ys=pts.map(p=>p[1]),xmin=Math.min(...xs),xmax=Math.max(...xs),ymin=Math.min(...ys),ymax=Math.max(...ys),pad=30,sx=(canvas.width-2*pad)/(xmax-xmin||1),sy=(canvas.height-2*pad)/(ymax-ymin||1);const categories=[...new Set(item.color_values||[])];const colors=new Map(categories.map(label=>[label,`hsl(${{hue(label)}} 58% 47%)`]));ctx.globalAlpha=0.7;for(let i=0;i<pts.length;i++){{const p=pts[i],label=(item.color_values||[])[i],color=label?colors.get(label):'#167f9c';ctx.fillStyle=color;ctx.beginPath();ctx.arc(pad+(p[0]-xmin)*sx,canvas.height-pad-(p[1]-ymin)*sy,2.2,0,Math.PI*2);ctx.fill();}}ctx.globalAlpha=1;count.textContent=`${{pts.length.toLocaleString()}} of ${{item.total_points.toLocaleString()}} points · ${{item.key}}`;categories.slice(0,24).forEach(label=>{{const node=document.createElement('span');node.className='legend-item';node.innerHTML=`<span class="swatch" style="background:${{colors.get(label)}}"></span><span></span>`;node.lastChild.textContent=label;legend.appendChild(node);}});if(categories.length>24){{const node=document.createElement('span');node.className='muted';node.textContent=`+${{categories.length-24}} more`;legend.appendChild(node);}}}}
select.addEventListener('change',draw);draw();
</script>
</body></html>"""


def write_h5ad_report(
    inspection: H5ADInspection,
    destination: str | Path,
    *,
    title: str = "CellOnDesk H5AD Summary",
) -> Path:
    destination = Path(destination)
    destination.write_text(render_h5ad_report(inspection, title=title), encoding="utf-8")
    return destination
