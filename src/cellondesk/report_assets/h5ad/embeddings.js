// Embedding coordinates retain source row identities after non-finite filtering.
const embeddingSelect = $('embedding-select'), colorSelect = $('color-select');
const canvas = $('embedding-canvas'), context = canvas.getContext('2d');
const embeddingMetadata = data.embedding_metadata;
const rowLookup = new Map((embeddingMetadata?.row_indices || []).map((row, index) => [row, index]));
const colorColumns = embeddingMetadata?.columns || [];
let highlighted = undefined, hitPoints = [];
data.embeddings.forEach((item, index) => option(embeddingSelect, `${item.key} · dimensions 1–2 of ${item.dimensions}`, index));
if (!data.embeddings.length) noOptions(embeddingSelect, 'No embedding available');
option(colorSelect, 'Uniform color', '');
colorColumns.forEach((column, index) => option(colorSelect, `${column.name} · ${column.kind}`, index));
if (!colorColumns.length && data.embeddings.some(item => item.color_values.length)) option(colorSelect, 'Original annotation (legacy inspection)', 'legacy');
const preferredColor = colorColumns.findIndex(column => column.name === data.likely_annotation);
if (preferredColor >= 0) colorSelect.value = String(preferredColor);
else if (!colorColumns.length && colorSelect.options.length > 1) colorSelect.value = 'legacy';

function drawEmbedding() {
  context.clearRect(0, 0, canvas.width, canvas.height);
  $('legend').replaceChildren(); $('color-note').textContent = ''; hitPoints = [];
  const item = data.embeddings[Number(embeddingSelect.value) || 0];
  if (!item) {
    $('point-count').textContent = 'No previewable embedding is available.';
    context.fillStyle = '#536c73'; context.font = '18px system-ui';
    context.fillText('No embedding coordinates recorded.', 40, 70);
    return;
  }
  const points = item.sampled_points;
  $('point-count').textContent = `${fmt(points.length)} plotted / ${fmt(item.total_points)} total observations · ${item.candidate_points === null || item.candidate_points === undefined ? 'candidate count not recorded' : `${fmt(item.candidate_points)} candidate rows`} · ${item.dropped_nonfinite === null || item.dropped_nonfinite === undefined ? 'coordinate exclusions not recorded' : `${fmt(item.dropped_nonfinite)} non-finite coordinates excluded`}`;
  const column = colorSelect.value !== '' && colorSelect.value !== 'legacy' ? colorColumns[Number(colorSelect.value)] : null;
  const numeric = column?.kind === 'numeric';
  const values = points.map((_, index) => {
    if (colorSelect.value === 'legacy') return item.color_values[index] ?? null;
    if (!column) return null;
    const position = rowLookup.get(item.row_indices[index]);
    return position === undefined ? null : column.values[position] ?? null;
  });
  const range = numeric ? extent(values) : null;
  const missing = values.filter(value => value === null).length;
  const color = value => numeric ? (value === null || !range ? '#98a6ab' : numericColor(fraction(value, ...range))) : categoryColor(value);
  if (!points.length) {
    context.fillStyle = '#536c73'; context.font = '18px system-ui';
    context.fillText('No finite coordinates among the selected rows.', 40, 70);
  } else {
    const xRange = extent(points.map(p => p[0])), yRange = extent(points.map(p => p[1]));
    const pad = 52, width = canvas.width - 2 * pad, height = canvas.height - 2 * pad;
    // Normalize together, preserving aspect ratio even for extreme coordinate magnitudes.
    const divisor = Math.max(...xRange.map(Math.abs), ...yRange.map(Math.abs), 1);
    const xmin = xRange[0] / divisor, xmax = xRange[1] / divisor;
    const ymin = yRange[0] / divisor, ymax = yRange[1] / divisor;
    const fit = Math.min(xmax > xmin ? width / (xmax - xmin) : Infinity, ymax > ymin ? height / (ymax - ymin) : Infinity);
    const scale = Number.isFinite(fit) ? fit : 1;
    const centerX = (xmin + xmax) / 2, centerY = (ymin + ymax) / 2;
    context.strokeStyle = '#dce7e3'; context.beginPath();
    context.moveTo(pad, pad); context.lineTo(pad, canvas.height - pad); context.lineTo(canvas.width - pad, canvas.height - pad); context.stroke();
    context.fillStyle = '#536c73'; context.font = '13px system-ui'; context.textAlign = 'center';
    context.fillText(`${item.key} · dimension 1`, canvas.width / 2, canvas.height - 13);
    context.save(); context.translate(18, canvas.height / 2); context.rotate(-Math.PI / 2);
    context.fillText(`${item.key} · dimension 2`, 0, 0); context.restore(); context.textAlign = 'left';
    points.forEach((point, index) => {
      const x = canvas.width / 2 + (point[0] / divisor - centerX) * scale;
      const y = canvas.height / 2 - (point[1] / divisor - centerY) * scale;
      const value = values[index];
      context.globalAlpha = highlighted !== undefined && value !== highlighted ? 0.12 : 0.82;
      context.fillStyle = colorSelect.value === '' ? '#187c80' : color(value);
      context.beginPath(); context.arc(x, y, Number($('point-size').value), 0, Math.PI * 2); context.fill();
      hitPoints.push({x, y, index, value});
    });
    context.globalAlpha = 1;
  }
  canvas.setAttribute('aria-label', `${item.key}, ${points.length} points, colored by ${column?.name || (colorSelect.value === 'legacy' ? item.color_field : 'uniform color')}`);
  if (numeric) {
    if (range) {
      $('legend').appendChild(element('span', fmt(range[0]), 'scale-label'));
      const ramp = element('div', undefined, 'color-scale');
      ramp.style.background = `linear-gradient(90deg,${numericColor(0)},${numericColor(.5)},${numericColor(1)})`;
      $('legend').appendChild(ramp); $('legend').appendChild(element('span', fmt(range[1]), 'scale-label'));
    }
    $('color-note').textContent = `${range ? `Linear color range of finite plotted values${range[0] === range[1] ? ' (constant value)' : ''}; no clipping` : 'No finite plotted values; no numeric color scale available'}. Missing/non-finite: ${fmt(missing)} (gray).`;
  } else if (colorSelect.value !== '') {
    const counts = new Map(); values.forEach(value => counts.set(value, (counts.get(value) || 0) + 1));
    const entries = [...counts].sort((a, b) => b[1] - a[1]);
    const shown = entries.slice(0, 24);
    if (counts.has(null) && !shown.some(([value]) => value === null)) shown.push([null, counts.get(null)]);
    shown.forEach(([value, count]) => {
      const button = element('button', undefined, 'legend-item'); button.type = 'button';
      button.setAttribute('aria-pressed', String(highlighted === value));
      const swatch = element('span', undefined, 'swatch'); swatch.style.background = color(value);
      button.append(swatch, element('span', `${displayLabel(value)} · ${fmt(count)}`));
      button.addEventListener('click', () => { highlighted = highlighted === value ? undefined : value; drawEmbedding(); });
      $('legend').appendChild(button);
    });
    $('color-note').textContent = `Click a legend entry to highlight it. ${fmt(counts.size)} categories among plotted points; missing values remain gray.${entries.length > shown.length ? ` Legend shows ${shown.length}; ${entries.length - shown.length} additional categories remain plotted. Colors may repeat.` : ' Colors may repeat.'}${colorSelect.value === 'legacy' ? ' Legacy labels may conflate missing values with a literal “Missing” category.' : ''}`;
  } else $('color-note').textContent = 'Uniform color. Choose a stored metadata field to explore annotations or numeric values.';
}
embeddingSelect.addEventListener('change', () => { highlighted = undefined; drawEmbedding(); });
colorSelect.addEventListener('change', () => { highlighted = undefined; drawEmbedding(); });
$('point-size').addEventListener('input', drawEmbedding);
$('reset-highlight').addEventListener('click', () => { highlighted = undefined; drawEmbedding(); });
canvas.addEventListener('mousemove', event => {
  const bounds = canvas.getBoundingClientRect();
  const x = (event.clientX - bounds.left) * canvas.width / bounds.width;
  const y = (event.clientY - bounds.top) * canvas.height / bounds.height;
  let best = null, distance = 100;
  hitPoints.forEach(point => { const d = (point.x - x) ** 2 + (point.y - y) ** 2; if (d < distance) { best = point; distance = d; } });
  const item = data.embeddings[Number(embeddingSelect.value) || 0];
  $('point-detail').textContent = best ? `Observation row (zero-based): ${item.row_indices[best.index] ?? 'not recorded'} · ${colorSelect.value === '' ? 'Uniform color' : displayLabel(best.value)}` : 'Hover over a point for its original observation row and metadata value.';
});
