// Capabilities/evidence are static and readable without JavaScript. Controls only
// draw values already serialized by the bounded native-format adapters.
function initializeScientific() {
  const scientific = data.scientific;
  if (!scientific) return;
  const features = scientific.feature_previews || [], metrics = scientific.recorded_metrics || [];
  const spatial = scientific.spatial_previews || [], images = scientific.images || [];
  const scope = preview => `${preview.row_indices.length < preview.total_rows ? 'Sampled' : 'All rows'}: ${fmt(preview.row_indices.length)} / ${fmt(preview.total_rows)} observations; ${fmt(preview.values.filter(Number.isFinite).length)} finite values; ${fmt(preview.values.filter(v => !Number.isFinite(v)).length)} missing/non-finite.`;
  function histogram(container, values) {
    container.replaceChildren();
    const finite = values.filter(Number.isFinite), range = extent(finite);
    if (!range) { container.appendChild(element('p', 'No finite recorded values.')); return; }
    const [low, high] = range, bins = low === high ? 1 : Math.min(20, Math.ceil(Math.sqrt(finite.length)));
    const counts = Array(bins).fill(0);
    finite.forEach(value => counts[Math.min(bins - 1, Math.floor(fraction(value, low, high) * bins))]++);
    const svg = svgElement('svg', {viewBox: '0 0 900 230', role: 'img', 'aria-label': 'Histogram of stored finite values'});
    const maximum = Math.max(...counts), step = 820 / bins;
    const edge = i => low * (1 - i / bins) + high * (i / bins);
    [0, 0.5, 1].forEach(t => {
      const y = 190 - t * 165;
      svg.appendChild(svgElement('line', {x1: 40, x2: 860, y1: y, y2: y, stroke: '#dce7e3'}));
      svg.appendChild(svgElement('text', {x: 35, y: y + 4, 'text-anchor': 'end'}, fmt(t * maximum)));
    });
    counts.forEach((count, i) => {
      const height = maximum ? count / maximum * 165 : 0;
      const bar = svgElement('rect', {x: 40 + i * step, y: 190 - height, width: Math.max(1, step - 2), height, fill: '#187c80', 'data-count': count});
      const interval = low === high ? `value ${fmt(low)}` : `[${fmt(edge(i))}, ${fmt(edge(i + 1))}${i === bins - 1 ? ']' : ')'}`;
      bar.appendChild(svgElement('title', {}, `${interval}: ${count} inspected observations; stored values`));
      svg.appendChild(bar);
    });
    svg.appendChild(svgElement('text', {x: 40, y: 216}, fmt(low)));
    svg.appendChild(svgElement('text', {x: 860, y: 216, 'text-anchor': 'end'}, fmt(high)));
    svg.appendChild(svgElement('text', {x: 450, y: 216, 'text-anchor': 'middle'}, 'Stored value · height = observations / bin'));
    container.appendChild(svg);
  }
  function drawFeature() {
    const feature = features[Number($('feature-select').value)];
    if (!feature) return;
    $('feature-scope').textContent = `${feature.matrix_path} · ${feature.name} · ${feature.family} · ${scope(feature)} Units: ${feature.units || 'not reported'}.`;
    histogram($('feature-chart'), feature.values);
    const body = tableHead($('feature-values'), ['Original observation row', 'Stored value'], 'Bounded values from the selected modality matrix; row positions are not cross-modality pairing');
    feature.values.forEach((value, i) => tableRow(body, [fmt(feature.row_indices[i]), value === null ? 'Missing / non-finite' : fmt(value)]));
  }
  if (features.length) {
    $('feature-panel').hidden = false;
    features.forEach((feature, i) => option($('feature-select'), `${feature.family} · ${feature.name} · ${feature.matrix_path}`, String(i)));
    $('feature-select').addEventListener('change', drawFeature);
    drawFeature();
  }
  function drawMetric() {
    const metric = metrics[Number($('metric-select').value)];
    if (!metric) return;
    $('metric-scope').textContent = `${metric.path} · ${scope(metric)}`;
    histogram($('metric-chart'), metric.values);
  }
  if (metrics.length) {
    $('recorded-metric-panel').hidden = false;
    metrics.forEach((metric, i) => option($('metric-select'), metric.path, String(i)));
    $('metric-select').addEventListener('change', drawMetric);
    drawMetric();
  }
  function drawSpatial() {
    const preview = spatial[Number($('spatial-select').value)];
    if (!preview) return;
    const feature = $('spatial-color').value === '' ? null : features[Number($('spatial-color').value)];
    const values = feature ? new Map(feature.row_indices.map((row, i) => [row, feature.values[i]])) : null;
    const range = feature ? extent(feature.values) : null;
    const canvas = $('spatial-canvas'), ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    canvas.dataset.points = String(preview.points.length);
    const xs = extent(preview.points.map(p => p[0])), ys = extent(preview.points.map(p => p[1]));
    $('spatial-scope').textContent = `${preview.path} · ${fmt(preview.points.length)} / ${fmt(preview.total_rows)} observations plotted; ${fmt(preview.exclusions)} sampled rows excluded. Frame: ${preview.frame || 'not reported'}. Units: ${preview.units || 'not reported'}. Axes shown x-right, y-up; tissue orientation unknown.${range ? ` Color: ${feature.name}, stored range ${fmt(range[0])}–${fmt(range[1])}; missing values gray.` : ''}`;
    if (!xs || !ys) return;
    // Preserve stored numeric geometry, including extreme finite coordinates.
    const divisor = Math.max(...xs.map(Math.abs), ...ys.map(Math.abs), 1);
    const xmin = xs[0] / divisor, xmax = xs[1] / divisor;
    const ymin = ys[0] / divisor, ymax = ys[1] / divisor;
    const fit = Math.min(xmax > xmin ? 930 / (xmax - xmin) : Infinity, ymax > ymin ? 430 / (ymax - ymin) : Infinity);
    const scale = Number.isFinite(fit) ? fit : 1;
    preview.points.forEach((point, i) => {
      const value = values ? values.get(preview.row_indices[i]) : null;
      ctx.fillStyle = values ? (Number.isFinite(value) && range ? numericColor(fraction(value, ...range)) : '#98a6ab') : '#187c80';
      const x = 500 + (point[0] / divisor - (xmin + xmax) / 2) * scale;
      const y = 260 - (point[1] / divisor - (ymin + ymax) / 2) * scale;
      ctx.beginPath(); ctx.arc(x, y, 3, 0, 2 * Math.PI); ctx.fill();
    });
    ctx.fillStyle = '#324c56'; ctx.font = '13px sans-serif';
    ctx.fillText(`x: ${fmt(xs[0])} — ${fmt(xs[1])}`, 35, 510);
    ctx.fillText(`y: ${fmt(ys[0])} — ${fmt(ys[1])}`, 35, 20);
  }
  function spatialChoices() {
    const preview = spatial[Number($('spatial-select').value)], select = $('spatial-color');
    select.replaceChildren(); option(select, 'No feature color', '');
    // Only the same native observation axis may color these points. Never join
    // different modality matrices by row number or equal length.
    const prefix = preview.path.split('/obsm/')[0];
    features.forEach((feature, i) => {
      if (feature.matrix_path === `${prefix}/X` && feature.total_rows === preview.total_rows) option(select, feature.name, String(i));
    });
    drawSpatial();
  }
  if (spatial.length) {
    $('spatial-panel').hidden = false;
    spatial.forEach((preview, i) => option($('spatial-select'), preview.path, String(i)));
    $('spatial-select').addEventListener('change', spatialChoices);
    $('spatial-color').addEventListener('change', drawSpatial);
    spatialChoices();
  }
  if (images.length) {
    for (const preview of images) {
      if (!/^data:image\/png;base64,[A-Za-z0-9+/=]+$/.test(preview.data_url)) continue;
      const figure = element('figure'), image = element('img');
      image.src = preview.data_url; image.alt = `Embedded image preview: ${preview.path}`;
      image.style.maxWidth = '100%'; image.style.height = 'auto';
      figure.appendChild(image);
      figure.appendChild(element('figcaption', `${preview.path} · ${preview.original_shape.join(' × ')} → ${preview.preview_shape.join(' × ')} · frame ${preview.frame || 'not reported'}. ${preview.note} Image registration has not been established.`));
      $('scientific-images').appendChild(figure);
    }
    $('image-panel').hidden = !$('scientific-images').children.length;
  }
}
initializeScientific();
