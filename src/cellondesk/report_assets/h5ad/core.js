// Shared primitives. All metadata reaches the DOM through textContent.
const data = JSON.parse(document.getElementById('inspection-data').textContent);
const $ = id => document.getElementById(id);
const fmt = value => Number.isFinite(value)
  ? value.toLocaleString('en-US', Number.isSafeInteger(value)
    ? {maximumFractionDigits: 0} : {maximumSignificantDigits: 5})
  : 'Not available';
const pct = (count, total) => total ? `${(100 * count / total).toFixed(2)}%` : 'Not available';
const element = (tag, text, className) => {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
};
const option = (select, label, value) => {
  const node = element('option', label);
  node.value = value;
  select.appendChild(node);
};
const noOptions = (select, message) => {
  option(select, message, '');
  select.disabled = true;
};
const svgElement = (tag, attrs, text) => {
  const node = document.createElementNS('http://www.w3.org/2000/svg', tag);
  Object.entries(attrs).forEach(([name, value]) => node.setAttribute(name, value));
  if (text !== undefined) node.textContent = text;
  return node;
};
const palette = ['#187c80', '#d67936', '#6d63a5', '#4e9146', '#bc5679', '#377db8', '#a57d21', '#75544a'];
const categoryColor = value => {
  if (value === null) return '#98a6ab';
  let hash = 2166136261;
  for (const char of String(value)) hash = Math.imul(hash ^ char.codePointAt(0), 16777619);
  return palette[(hash >>> 0) % palette.length];
};
const displayLabel = value => {
  if (value === null) return '∅ Missing metadata';
  const label = String(value);
  return ['∅ Missing metadata', 'Σ Other categories (pooled)'].includes(label)
    ? `${label} (literal category)` : label;
};
const numericColor = t => {
  // Sequential blue/teal ramp, with luminance and labels in addition to hue.
  const stops = [[232, 243, 242], [59, 155, 157], [15, 57, 81]];
  const position = Math.max(0, Math.min(1, t)) * 2;
  const index = Math.min(1, Math.floor(position)), f = position - index;
  return `rgb(${stops[index].map((v, i) => Math.round(v + f * (stops[index + 1][i] - v))).join(',')})`;
};
const fraction = (value, low, high) => {
  if (low === high) return 0.5;
  const range = high - low;
  return Number.isFinite(range) ? (value - low) / range : (value / 2 - low / 2) / (high / 2 - low / 2);
};
const extent = values => {
  let low = Infinity, high = -Infinity;
  for (const v of values) if (Number.isFinite(v)) { low = Math.min(low, v); high = Math.max(high, v); }
  return low === Infinity ? null : [low, high];
};
const sampleScope = sample => sample ? `${sample.row_indices.length < sample.total_rows ? 'Sampled' : 'All rows'}: ${fmt(sample.row_indices.length)} / ${fmt(sample.total_rows)} observations` : 'Aligned metadata was not recorded. Regenerate the inspection to enable this view.';
const tableHead = (table, labels, caption) => {
  table.replaceChildren();
  if (caption) table.appendChild(element('caption', caption));
  const head = element('thead'), row = element('tr');
  labels.forEach(label => { const th = element('th', label); th.scope = 'col'; row.appendChild(th); });
  head.appendChild(row); table.appendChild(head);
  const body = element('tbody'); table.appendChild(body);
  return body;
};
const tableRow = (parent, values) => {
  const row = element('tr');
  values.forEach((value, i) => {
    const cell = element(i ? 'td' : 'th', value);
    if (!i) cell.scope = 'row';
    row.appendChild(cell);
  });
  parent.appendChild(row);
  return row;
};
