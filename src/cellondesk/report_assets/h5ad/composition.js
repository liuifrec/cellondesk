// Aggregates use the metadata sample, never the embedding's filtered coordinates.
const obsSample = data.obs_sample;
const categoricalColumns = (obsSample?.columns || []).filter(column => column.kind === 'categorical');
const compositionSelect = $('composition-field'), sampleSelect = $('sample-field');
const OTHER = Symbol('pooled categories');
const groupLabel = value => value === OTHER ? 'Σ Other categories (pooled)' : displayLabel(value);
const groupColor = value => value === OTHER ? '#65767c' : categoryColor(value);

function pooled(values, limit = 20) {
  const counts = new Map();
  values.forEach(value => counts.set(value, (counts.get(value) || 0) + 1));
  const ranked = [...counts].filter(([value]) => value !== null).sort((a, b) => b[1] - a[1] || String(a[0]).localeCompare(String(b[0]), 'en'));
  const kept = new Set(ranked.slice(0, limit).map(([value]) => value));
  const groups = ranked.slice(0, limit).map(([value, count]) => ({value, count}));
  if (counts.has(null)) groups.push({value: null, count: counts.get(null)});
  const omitted = ranked.slice(limit), otherCount = omitted.reduce((sum, pair) => sum + pair[1], 0);
  if (omitted.length) groups.push({value: OTHER, count: otherCount});
  return {groups, omitted: omitted.length, assign: value => value === null || kept.has(value) ? value : OTHER};
}
categoricalColumns.forEach((column, index) => option(compositionSelect, column.name, index));
// Numeric identifiers are allowed as explicit exact-value grouping, without inference.
(obsSample?.columns || []).forEach((column, index) => option(sampleSelect, `${column.name}${column.kind === 'numeric' ? ' · numeric exact values' : ''}`, index));
if (!categoricalColumns.length) noOptions(compositionSelect, 'No categorical metadata');
if (!obsSample?.columns.length) noOptions(sampleSelect, 'No grouping metadata');
const annotationIndex = categoricalColumns.findIndex(column => column.name === data.likely_annotation);
if (annotationIndex >= 0) compositionSelect.value = String(annotationIndex);
const sampleCandidates = ['sample_id', 'sample', 'donor_id', 'donor', 'batch', 'orig.ident'];
const sampleIndex = sampleCandidates.map(name => (obsSample?.columns || []).findIndex(column => column.name.toLowerCase() === name)).find(index => index >= 0);
if (sampleIndex !== undefined) sampleSelect.value = String(sampleIndex);

function drawComposition() {
  const column = categoricalColumns[Number(compositionSelect.value) || 0];
  $('composition-scope').textContent = `${sampleScope(obsSample)}${obsSample ? ' · denominator includes missing annotation values; counts are not extrapolated.' : ''}`;
  $('composition-bars').replaceChildren(); $('composition-table').replaceChildren();
  $('composition-note').textContent = '';
  if (!column || !column.values.length) {
    $('composition-bars').appendChild(element('p', 'No categorical observation values are available for composition.', 'empty'));
    drawCrossTab(null); return;
  }
  const grouping = pooled(column.values), total = column.values.length;
  const maximum = Math.max(...grouping.groups.map(group => group.count), 1);
  const body = tableHead($('composition-table'), ['Annotation', 'Observations', '% of inspected rows'], `${column.name} · denominator ${fmt(total)} inspected observations`);
  for (const group of grouping.groups) {
    const row = element('div', undefined, 'bar-row');
    const track = element('div', undefined, 'bar-track'), fill = element('div', undefined, 'bar-fill');
    const percentMode = $('composition-mode').value === 'percent';
    fill.style.width = `${100 * group.count / (percentMode ? total : maximum)}%`;
    fill.style.background = groupColor(group.value); track.appendChild(fill);
    row.append(element('span', groupLabel(group.value), 'bar-label'), track, element('span', `${fmt(group.count)} · ${pct(group.count, total)}`, 'bar-count'));
    $('composition-bars').appendChild(row);
    tableRow(body, [groupLabel(group.value), fmt(group.count), pct(group.count, total)]);
  }
  $('composition-note').textContent = `${grouping.omitted ? `${grouping.omitted} categories beyond the 20 most frequent are pooled into Other. ` : ''}Missing metadata is a separate group, distinct from a literal category named “Missing”. Percentages describe inspected rows, not biological replicates or population estimates.`;
  drawCrossTab(grouping);
}
function drawCrossTab(annotationGrouping) {
  const annotation = categoricalColumns[Number(compositionSelect.value) || 0];
  const sample = obsSample?.columns[Number(sampleSelect.value) || 0];
  $('cross-table').replaceChildren(); $('cross-note').textContent = '';
  if (!annotationGrouping || !sample || !sample.values.length) {
    $('cross-scope').textContent = 'A categorical annotation and aligned grouping field are required.'; return;
  }
  const samples = pooled(sample.values), cols = annotationGrouping.groups, rows = samples.groups;
  const colIndex = new Map(cols.map((group, index) => [group.value, index]));
  const rowIndex = new Map(rows.map((group, index) => [group.value, index]));
  const counts = rows.map(() => cols.map(() => 0));
  annotation.values.forEach((value, index) => {
    counts[rowIndex.get(samples.assign(sample.values[index]))][colIndex.get(annotationGrouping.assign(value))]++;
  });
  const percentMode = $('cross-mode').value === 'percent';
  const total = annotation.values.length;
  $('cross-scope').textContent = `${sampleScope(obsSample)} · ${percentMode ? 'percent within each sample row; Total shows its observation count' : 'observation counts'} · missing annotations and sample values included.`;
  const body = tableHead($('cross-table'), [sample.name, ...cols.map(group => groupLabel(group.value)), 'Total observations'], `${sample.name} × ${annotation.name}`);
  rows.forEach((group, row) => {
    const cells = counts[row].map(value => percentMode ? pct(value, group.count) : fmt(value));
    const tr = tableRow(body, [groupLabel(group.value), ...cells, fmt(group.count)]);
    counts[row].forEach((value, col) => {
      const cell = tr.children[col + 1];
      cell.dataset.count = value;
      cell.style.background = `rgba(8,127,120,${0.04 + 0.23 * value / group.count})`;
      cell.title = `${fmt(value)} / ${fmt(group.count)} observations in this sample row`;
    });
  });
  const foot = element('tfoot');
  tableRow(foot, ['Total', ...cols.map(group => percentMode ? pct(group.count, total) : fmt(group.count)), fmt(total)]);
  $('cross-table').appendChild(foot);
  $('cross-note').textContent = `${samples.omitted ? `${samples.omitted} sample values are pooled into Other. ` : ''}${annotationGrouping.omitted ? `${annotationGrouping.omitted} annotation categories are pooled into Other. ` : ''}${percentMode ? 'Footer percentages use all inspected rows as denominator. ' : ''}Rows are supplied grouping labels, not inferred donors. Counts do not measure replicate-level variability or statistical significance.`;
}
compositionSelect.addEventListener('change', drawComposition);
$('composition-mode').addEventListener('change', drawComposition);
sampleSelect.addEventListener('change', drawComposition);
$('cross-mode').addEventListener('change', drawComposition);
