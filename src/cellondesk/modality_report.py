"""Static scientific evidence/capability markup, shared by native format readers."""

from __future__ import annotations

import html

from .modality import PROFILE_LABELS, ModalityReport


def _escape(value) -> str:
    return html.escape(str(value), quote=True)


def _row(values, attributes="") -> str:
    return f"<tr{attributes}>" + "".join(f"<td>{_escape(value)}</td>" for value in values) + "</tr>"


def _table(identifier, headings, rows) -> str:
    head = "".join(f"<th>{_escape(value)}</th>" for value in headings)
    return f'<div class="table-wrap"><table id="{identifier}"><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table></div>'


def scientific_markup(report: ModalityReport | None) -> str:
    if report is None:
        return '<p class="note">Scientific evidence was not recorded by this older inspection. General views remain available.</p>'
    profiles = (
        "".join(
            f"<li><strong>{_escape(PROFILE_LABELS.get(p.profile, p.profile))}</strong> · {_escape(p.state)} — {_escape(p.reason)}</li>"
            for p in report.profiles
        )
        or "<li>Unclassified: the file is not assumed to be RNA. Use a recorded manual override if appropriate.</li>"
    )
    modules = "".join(
        f"<li>{_escape(m.name)}: {m.observations:,} observations, {m.features:,} features; {_escape(', '.join(m.profiles) or 'unclassified')}</li>"
        for m in report.modules
    )
    notes = list(report.warnings)
    notes.extend(c.reason for c in report.capabilities if c.state == "invalid")
    warnings = "".join(f"<li>{_escape(note)}</li>" for note in dict.fromkeys(notes))
    manual = _escape(", ".join(report.manual_overrides) or "None")
    parts = [
        f"""<article class="card"><h3>Scientific profiles</h3><ul id="scientific-profiles">{profiles}</ul>
<p id="manual-profile-note">Manual interpretation: {manual}. Choices do not create measurements, QC values or correspondence.</p>
<p class="note">File annotations, validated storage structure and source assay claims are different evidence. Supported profiles do not independently validate the experimental assay.</p>
{f"<ul>{modules}</ul>" if modules else ""}</article>"""
    ]
    if warnings:
        parts.append(
            f'<article class="card warning"><h3>Scientific scope and integrity</h3><ul>{warnings}</ul></article>'
        )
    capabilities = "".join(
        _row(
            (c.title, c.state, c.reason, ", ".join(c.paths)),
            f' data-capability="{_escape(c.key)}" data-state="{_escape(c.state)}"',
        )
        for c in report.capabilities
    )
    table = _table(
        "capability-table",
        ("Panel", "State", "Evidence / limitation", "Source paths"),
        capabilities,
    )
    available = sum(c.state == "available" for c in report.capabilities)
    parts.append(
        f'<article class="card"><details><summary>Panel capabilities · {available} available · inspect missing or unsupported components</summary>{table}</details></article>'
    )
    evidence = "".join(
        _row((e.profile, e.origin, e.path, e.value, e.scope)) for e in report.evidence
    )
    table = _table(
        "modality-evidence",
        ("Profile", "Origin", "Path", "Observed declaration / structure", "Scope"),
        evidence,
    )
    limits = _escape(", ".join(f"{key}: {value:,}" for key, value in report.limits.items()))
    parts.append(
        f'<article class="card"><details><summary>Evidence, provenance and inspection limits</summary>{table}<p class="note">{limits}</p></details></article>'
    )
    if report.correspondence:
        maps = "".join(
            _row(
                (
                    c.module,
                    c.axis,
                    c.state,
                    f"{c.checked} / {c.total}",
                    c.present,
                    c.absent,
                    c.mismatched,
                    c.reason,
                )
            )
            for c in report.correspondence
        )
        table = _table(
            "correspondence-table",
            (
                "Module",
                "Axis",
                "State",
                "Inspected / total",
                "Present",
                "Absent",
                "Mismatched",
                "Interpretation",
            ),
            maps,
        )
        parts.append(
            f'<article class="card"><details open><summary>Explicit correspondence checks</summary>{table}</details></article>'
        )
    return "\n".join(parts)
