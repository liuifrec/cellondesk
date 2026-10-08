// Histograms contain only existing finite numeric obs values; no X-derived QC.
const qcSelect = $('qc-field');
const qcPriority = ['total_counts', 'n_counts', 'n_genes_by_counts', 'n_genes', 'pct_counts_mt', 'pct_counts_mito'];
const numericColumns = data.obs_columns.filter(column => column.numeric).sort((a, b) => {
  const rank = name => { const i = qcPriority.indexOf(name.toLowerCase()); return i < 0 ? 100 : i; };
  return rank(a.name) - rank(b.name);
});
numericColumns.forEach((column, index) => option(qcSelect, column.name, index));
if (!numericColumns.length) noOptions(qcSelect, 'No numeric metadata');
function drawQC() {
  const column = numericColumns[Number(qcSelect.value) || 0];
  $('qc-chart').replaceChildren(); $('qc-stats').replaceChildren(); $('qc-bins').replaceChildren();
  if (!column) {
    $('qc-scope').textContent = 'No numeric obs metadata was recorded. QC distributions are unavailable.';
    $('qc-chart').appendChild(element('p', 'No available QC values. Nothing has been inferred from the expression matrix.', 'empty')); return;
  }
  const summary = column.numeric;
  const inspected = column.sampled_values ?? summary.count + summary.missing;
  $('qc-scope').textContent = `${column.name} · ${column.sampled ? 'Sampled' : 'All rows'}: ${fmt(inspected)} / ${fmt(column.total_values ?? data.n_obs)} rows · finite: ${fmt(summary.count)} · missing/non-finite: ${fmt(summary.missing)}. Histogram denominator: finite values only.`;
  [['Minimum', summary.minimum], ['p05', summary.p05], ['Median', summary.median], ['p95', summary.p95], ['Maximum', summary.maximum]].forEach(([label, value]) => {
    const metric = element('span', label); metric.appendChild(element('strong', fmt(value))); $('qc-stats').appendChild(metric);
  });
  const histogram = summary.histogram;
  if (!histogram?.counts.length || !summary.count) {
    $('qc-chart').appendChild(element('p', summary.count ? 'Histogram bins were not recorded by this older inspection. Regenerate the report to enable this chart.' : 'No finite values are available for a histogram.', 'empty')); return;
  }
  const {edges, counts} = histogram, maxCount = Math.max(...counts, 1);
  const svg = svgElement('svg', {viewBox: '0 0 1000 360', role: 'img', 'aria-label': `${column.name}: ${summary.count} finite values in ${counts.length} bins`});
  const left = 70, top = 20, width = 900, height = 270;
  svg.appendChild(svgElement('title', {}, `${column.name} — observed finite values only`));
  [0, .25, .5, .75, 1].forEach(t => {
    const y = top + height * (1 - t);
    svg.appendChild(svgElement('line', {x1: left, y1: y, x2: left + width, y2: y, stroke: '#dce7e3'}));
    svg.appendChild(svgElement('text', {x: left - 10, y: y + 4, 'text-anchor': 'end'}, fmt(maxCount * t)));
  });
  const body = tableHead($('qc-bins'), ['Bin interval', 'Finite values'], 'Intervals are [left, right); the final bin includes its right edge.');
  counts.forEach((count, i) => {
    const low = edges[i], high = edges[i + 1], constant = edges[0] === edges[edges.length - 1];
    const start = constant ? 0.25 : fraction(low, edges[0], edges[edges.length - 1]);
    const stop = constant ? 0.75 : fraction(high, edges[0], edges[edges.length - 1]);
    const rect = svgElement('rect', {x: left + width * start + 1, y: top + height * (1 - count / maxCount), width: Math.max(1, width * (stop - start) - 2), height: height * count / maxCount, fill: '#187c80', 'data-count': count});
    const interval = constant ? `Exactly ${low}` : `[${low}, ${high}${i === counts.length - 1 ? ']' : ')'}`;
    rect.appendChild(svgElement('title', {}, `${interval}: ${fmt(count)} values`)); svg.appendChild(rect);
    tableRow(body, [interval, fmt(count)]);
  });
  svg.appendChild(svgElement('text', {x: left, y: 317}, fmt(edges[0])));
  svg.appendChild(svgElement('text', {x: left + width, y: 317, 'text-anchor': 'end'}, fmt(edges[edges.length - 1])));
  svg.appendChild(svgElement('text', {x: left + width / 2, y: 350, 'text-anchor': 'middle'}, `${column.name} (stored values)`));
  svg.appendChild(svgElement('text', {x: 17, y: 150, transform: 'rotate(-90 17 150)', 'text-anchor': 'middle'}, 'Finite values / bin'));
  $('qc-chart').appendChild(svg);
}
qcSelect.addEventListener('change', drawQC);
