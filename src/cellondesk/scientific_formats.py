"""Format dispatch and a conservative MuData adapter; no implicit conversion."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from ._version import __version__
from .h5ad_access import _axis_column_names, _axis_index_name, _axis_length, _field
from .h5ad_dashboard import observation_sample
from .inspection import (
    H5ADInspection,
    InspectionProvenance,
    MatrixSummary,
    _choose_annotation,
    _read_node_values,
    _require_data_dependencies,
    _sample_indices,
)
from .modality import (
    CorrespondenceCheck,
    ModalityEvidence,
    ModalityReport,
    ModuleInventory,
    ProfileActivation,
    apply_overrides,
    capability,
)
from .modality_h5ad import LIMITS, inspect_group

FORMAT_REGISTRY = {
    ".h5ad": "Bounded H5AD dashboard and evidence-gated scientific modules",
    ".h5mu": "Bounded MuData inventory, per-modality previews and explicit axis-map checks",
    ".zarr": "Planned SpatialData/AnnData-Zarr adapter; not inspected in this version",
    ".ome.tif": "Planned tiled OME imaging adapter; segmentation/registration not inspected",
    ".ome.tiff": "Planned tiled OME imaging adapter; segmentation/registration not inspected",
    ".imzml": "Planned paired imzML/ibd mass-spectrometry adapter; no ion identities inferred",
}


class ContainerInspection(H5ADInspection):
    """Common report envelope, retaining a native MuData container and its axes.

    Inheritance preserves existing report/export APIs; no AnnData is constructed
    and no joint matrix is synthesized. MatrixSummary explicitly records absence.
    """

    storage_format: str = "H5MU"


def inspection_support(filenames: list[str]) -> list[str]:
    found = []
    for suffix, description in FORMAT_REGISTRY.items():
        if any(name.casefold().split("?", 1)[0].endswith(suffix) for name in filenames):
            found.append(description + " (format support only; file contents not checked)")
    return found or ["File format/inspection capabilities not yet checked"]


def _map_check(handle, module, axis, np):
    table = handle[axis]
    child = handle[f"mod/{module}/{axis}"]
    total, child_total = _axis_length(table), _axis_length(child)
    result = CorrespondenceCheck(
        axis=axis,
        module=module,
        total=total,
        state="unverified",
        reason="No explicit map; matching row positions or counts do not establish correspondence.",
    )
    path = f"{axis}map/{module}"
    if path not in handle:
        return result
    node = handle[path]
    if not hasattr(node, "dtype") or node.shape != (total,) or node.dtype.kind not in "iu":
        return result.model_copy(
            update={
                "state": "invalid",
                "reason": "Map must be an integer vector on the global axis.",
            }
        )
    rows = _sample_indices(total, LIMITS["correspondence_rows"], np)
    values = np.asarray(node[rows])
    result.checked = len(rows)
    result.present = int(np.count_nonzero(values))
    result.absent = len(rows) - result.present
    if np.any(values > child_total) or np.any(values < 0):
        return result.model_copy(
            update={
                "state": "invalid",
                "reason": "Map contains out-of-range indices; zero is absent, positive values are 1-based.",
            }
        )
    present = values > 0
    if not np.any(present):
        result.reason = "All inspected map entries are absent; no shared observation/feature correspondence established."
        return result
    mapped = values[present].astype("int64") - 1
    if len(np.unique(mapped)) != len(mapped):
        return result.model_copy(
            update={
                "state": "invalid",
                "reason": "Duplicate sampled map targets; correspondence is not one-to-one.",
            }
        )
    global_index, child_index = _axis_index_name(table), _axis_index_name(child)
    if not global_index or not child_index:
        result.reason = "Map ranges checked, but axis identifiers are missing; identity unverified."
        return result
    global_ids = _read_node_values(_field(table, global_index), rows[present], np)
    order = np.argsort(mapped)
    sorted_ids = _read_node_values(_field(child, child_index), mapped[order], np)
    if any(value is None or not str(value).strip() for value in [*global_ids, *sorted_ids]):
        result.reason = "Inspected axis identifiers contain missing values; identity unverified."
        return result
    local_ids = [None] * len(mapped)
    for position, value in zip(order.tolist(), sorted_ids):
        local_ids[position] = value
    result.mismatched = sum(str(a) != str(b) for a, b in zip(global_ids, local_ids))
    if result.mismatched:
        result.state = "invalid"
        result.reason = (
            "Mapped identifiers disagree; no barcode or feature correspondence asserted."
        )
    elif len(set(map(str, global_ids))) != len(global_ids):
        result.state = "invalid"
        result.reason = "Duplicate sampled identifiers are ambiguous; joint comparisons withheld."
    else:
        result.state = "verified" if len(rows) == total else "sample_consistent"
        result.reason = "Map indices and corresponding identifiers agree for inspected entries only; no biological identity or cross-feature relationship inferred."
    return result


def inspect_h5mu(
    path: str | Path, *, modality_override=None, max_points=5000, annotation=None
) -> ContainerInspection:
    h5py, np = _require_data_dependencies()
    if isinstance(max_points, bool) or not isinstance(max_points, int) or max_points < 1:
        raise ValueError("max_points must be a positive integer")

    source = Path(path).expanduser().resolve()
    before = source.stat()
    scientific = ModalityReport(limits=dict(LIMITS))
    warnings = []
    with h5py.File(source, "r") as handle:
        if not all(name in handle for name in ("mod", "obs", "var")):
            raise ValueError(
                "MuData requires native mod, obs and var groups; no H5AD conversion attempted"
            )
        axis = handle.attrs.get("axis", 0)
        if axis not in (0, 1, -1):
            raise ValueError("Unsupported MuData axis declaration")
        n_obs, n_vars = _axis_length(handle["obs"]), _axis_length(handle["var"])
        rows = _sample_indices(n_obs, min(20000, max_points), np)
        names = _axis_column_names(handle["obs"])
        likely_annotation = _choose_annotation(names, annotation)
        selected = names[:50]
        if likely_annotation and likely_annotation not in selected:
            selected.append(likely_annotation)
        if annotation and likely_annotation is None:
            warnings.append(f"Requested global annotation {annotation!r} was not found.")
        obs_sample, obs_columns = observation_sample(
            handle["obs"], selected, total=n_obs, indices=rows, np=np, warnings=warnings
        )
        if len(rows) < n_obs:
            warnings.append(
                f"Global metadata samples {len(rows)} / {n_obs} observations at evenly spaced positions; not random or necessarily representative."
            )
        if len(selected) < len(names):
            warnings.append(
                f"Only {len(selected)} / {len(names)} global metadata fields inspected."
            )
        module_names = sorted(handle["mod"].keys())
        for name in module_names[: LIMITS["modules"]]:
            group = handle[f"mod/{name}"]
            if not all(axis_name in group for axis_name in ("obs", "var")):
                scientific.warnings.append(f"Module {name!r} lacks AnnData axes; omitted.")
                continue
            count, features = _axis_length(group["obs"]), _axis_length(group["var"])
            _, summaries = observation_sample(
                group["obs"],
                _axis_column_names(group["obs"])[:50],
                total=count,
                indices=_sample_indices(count, LIMITS["preview_rows"], np),
                np=np,
                warnings=scientific.warnings,
            )
            child = inspect_group(
                group,
                n_obs=count,
                n_vars=features,
                numeric_obs=[c.name for c in summaries if c.numeric is not None],
                np=np,
            )
            scientific.modules.append(
                ModuleInventory(
                    name=name,
                    observations=count,
                    features=features,
                    profiles=[p.profile for p in child.profiles],
                )
            )
            for field in (
                "evidence",
                "feature_previews",
                "spatial_previews",
                "images",
                "recorded_metrics",
                "warnings",
            ):
                getattr(scientific, field).extend(getattr(child, field))
            for profile in child.profiles:
                if not any(
                    p.profile == profile.profile and p.state == profile.state
                    for p in scientific.profiles
                ):
                    scientific.profiles.append(profile)
            for cap in child.capabilities:
                cap.reason = f"Module {name}: {cap.reason}"
                scientific.capabilities.append(cap)
            for axis_name in ("obs", "var"):
                try:
                    check = _map_check(handle, name, axis_name, np)
                except (ValueError, TypeError, KeyError, IndexError, OSError) as exc:
                    check = CorrespondenceCheck(
                        axis=axis_name, module=name, state="invalid", reason=str(exc)
                    )
                scientific.correspondence.append(check)
        if len(module_names) > LIMITS["modules"]:
            scientific.warnings.append(
                f"Only {LIMITS['modules']} / {len(module_names)} modalities inspected; other modules may contain additional capabilities."
            )
        if len(scientific.modules) > 1:
            families = {
                e.profile
                for e in scientific.evidence
                if e.origin == "file_annotation" and e.profile in {"rna", "atac", "protein", "ion"}
            }
            multiple_families = len(families) > 1
            scientific.profiles = [p for p in scientific.profiles if p.profile != "multiomics"]
            scientific.profiles.append(
                ProfileActivation(
                    profile="multiomics",
                    state="supported" if multiple_families else "suggested",
                    reason="Multiple annotated measurement families in native modules; biological pairing is not established."
                    if multiple_families
                    else "Multiple native modules observed; distinct measurement families and biological pairing must be established separately.",
                )
            )
            scientific.evidence.append(
                ModalityEvidence(
                    profile="multiomics",
                    origin="file_structure",
                    path="/mod",
                    value=", ".join(module_names[: LIMITS["modules"]]),
                    scope=f"Container axis={axis}; module names alone do not verify their experimental modalities",
                )
            )
        invalid = any(c.state == "invalid" for c in scientific.correspondence)
        scientific.capabilities = [c for c in scientific.capabilities if c.key != "joint_views"]
        scientific.capabilities.append(
            capability(
                "joint_views",
                "invalid" if invalid else "unsupported",
                "At least one correspondence map is inconsistent; no cross-modality view is enabled."
                if invalid
                else "Bounded map checks are displayed; joint analysis is outside this adapter's scope.",
            )
        )
        apply_overrides(scientific, modality_override)
        after = source.stat()
        unchanged = (before.st_size, before.st_mtime_ns, before.st_ino, before.st_dev) == (
            after.st_size,
            after.st_mtime_ns,
            after.st_ino,
            after.st_dev,
        )
        if not unchanged:
            warnings.append("Source changed during inspection; regenerate this report.")
        warnings.extend(
            [
                "MuData container preserved. Global axes are not a joint measurement matrix; module observations may overlap.",
                "Correspondence checks are bounded; zero map entries denote absent observations/features. No cross-feature biological relationship is inferred.",
            ]
        )
        return ContainerInspection(
            source_path=str(source),
            file_name=source.name,
            file_size_bytes=before.st_size,
            n_obs=n_obs,
            n_vars=n_vars,
            matrix=MatrixSummary(shape=(n_obs, n_vars), encoding="container; no joint X"),
            obs_column_names=names,
            obs_columns=obs_columns,
            obs_sample=obs_sample,
            likely_annotation=likely_annotation,
            scientific=scientific,
            warnings=warnings,
            provenance=InspectionProvenance(
                generator_version=__version__,
                inspected_at=datetime.now(timezone.utc).isoformat(),
                source_mtime_ns=before.st_mtime_ns,
                source_stat_unchanged=unchanged,
                encoding_type="MuData",
                encoding_version=str(handle.attrs.get("encoding-version", "Not reported")),
                limits=dict(LIMITS),
                dependencies={"h5py": h5py.__version__, "numpy": np.__version__},
            ),
        )


def inspect_scientific(path: str | Path, **kwargs) -> H5ADInspection:
    source = Path(path)
    if source.suffix.lower() == ".h5ad":
        from .h5ad_compat import inspect_h5ad

        return inspect_h5ad(source, **kwargs)
    if source.suffix.lower() == ".h5mu":
        return inspect_h5mu(source, **kwargs)
    raise ValueError(
        "Unsupported scientific input format. This version inspects H5AD and native H5MU; SpatialData/Zarr, OME imaging and imzML adapters are planned. No AnnData conversion attempted."
    )
