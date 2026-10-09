"""Bounded modality evidence and previews from a read-only AnnData HDF5 group."""

from __future__ import annotations

import base64
import re
import struct
import zlib
from typing import Any

from .h5ad_access import _axis_column_names, _axis_index_name, _encoding, _field
from .inspection import _read_node_values, _sample_indices, _shape_from_node
from .modality import (
    FeaturePreview,
    ImagePreview,
    ModalityEvidence,
    ModalityReport,
    ProfileActivation,
    RecordedMetric,
    SpatialPreview,
    apply_overrides,
    assay_profiles,
    capability,
)

LIMITS = {
    "feature_annotations": 4096,
    "preview_rows": 256,
    "preview_features": 8,
    "matrix_entries": 2000000,
    "image_side": 384,
    "images": 2,
    "spatial_arrays": 2,
    "modules": 4,
    "correspondence_rows": 4096,
}
FEATURE_TYPES = {
    "gene expression": "rna",
    "rna": "rna",
    "peaks": "atac",
    "chromatin accessibility": "atac",
    "antibody capture": "protein",
    "protein": "protein",
    "proteins": "protein",
    "molecular ions": "ion",
    "mass-to-charge": "ion",
    "metabolites": "ion",
}


def scalar(group: Any, path: str) -> str | None:
    if path not in group:
        return None
    node = group[path]
    if not hasattr(node, "dtype") or node.shape not in ((), (1,)):
        return None
    value = node[()] if node.shape == () else node[0]
    if isinstance(value, bytes):
        value = value.decode("utf-8", "replace")
    return str(value)[:4096]


def _preview_values(node, rows, columns, shape, np):
    """Sparse chunks are capped; abort the preview instead of inventing unscanned zeros."""
    if _shape_from_node(node) != shape:
        raise ValueError("Measurement matrix shape does not match observation/feature axes")
    if hasattr(node, "dtype"):
        if node.dtype.kind not in "iufb":
            raise ValueError("Measurement matrix is not real numeric data")
        return np.column_stack([node[rows, int(column)] for column in columns])
    encoding = _encoding(node)
    if encoding not in {"csr_matrix", "csc_matrix"}:
        raise ValueError("Unsupported measurement matrix encoding")
    data, indices, pointers = node["data"], node["indices"], node["indptr"]
    major, minor = shape if encoding == "csr_matrix" else shape[::-1]
    if (
        indices.dtype.kind not in "iu"
        or pointers.dtype.kind not in "iu"
        or data.dtype.kind not in "iufb"
        or data.ndim != 1
        or indices.ndim != 1
        or pointers.shape != (major + 1,)
        or len(data) != len(indices)
    ):
        raise ValueError("Malformed sparse matrix arrays")
    values = np.zeros((len(rows), len(columns)), dtype=float)
    selected = rows if encoding == "csr_matrix" else columns
    wanted = {
        int(value): i for i, value in enumerate(columns if encoding == "csr_matrix" else rows)
    }
    read = 0
    for position, index in enumerate(selected):
        start, stop = int(pointers[int(index)]), int(pointers[int(index) + 1])
        if not 0 <= start <= stop <= len(data):
            raise ValueError("Invalid sampled sparse pointer range")
        read += stop - start
        if read > LIMITS["matrix_entries"]:
            raise ValueError(
                "Sparse preview scan limit reached; no partial feature values exported"
            )
        for offset in range(start, stop, 16384):
            end = min(stop, offset + 16384)
            coords = np.asarray(indices[offset:end])
            chunk = np.asarray(data[offset:end], dtype=float)
            if np.any(coords < 0) or np.any(coords >= minor):
                raise ValueError("Invalid sparse index in sampled data")
            for coordinate, value in zip(coords, chunk):
                target = wanted.get(int(coordinate))
                if target is not None:
                    row, col = (
                        (position, target) if encoding == "csr_matrix" else (target, position)
                    )
                    values[row, col] += value
    return values


def _png(array, np):
    """Encode a small sampled RGB(A) image using only standard-library PNG support."""
    if array.ndim == 2:
        array = np.repeat(array[:, :, None], 3, axis=2)
    if array.ndim != 3 or array.shape[2] not in (3, 4) or not np.isfinite(array).all():
        raise ValueError("Image must contain finite grayscale, RGB or RGBA pixels")
    low, high = float(array.min()), float(array.max())
    note = "Stored uint8 intensities; no physical calibration inferred."
    if array.dtype != np.uint8:
        if not np.isfinite(high - low):
            raise ValueError("Unsupported image intensity range")
        note = f"Preview-only intensity scaling from sampled range [{low:g}, {high:g}] to [0, 255]."
        array = (
            (
                (array.astype(float) - low) / (high - low) * 255
                if high > low
                else np.zeros(array.shape)
            )
            .clip(0, 255)
            .astype("u1")
        )
    height, width, channels = array.shape

    def chunk(name, value):
        return (
            struct.pack(">I", len(value))
            + name
            + value
            + struct.pack(">I", zlib.crc32(name + value))
        )

    raw = b"".join(b"\0" + array[row].tobytes() for row in range(height))
    content = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(
            b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6 if channels == 4 else 2, 0, 0, 0)
        )
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )
    return "data:image/png;base64," + base64.b64encode(content).decode("ascii"), note


def inspect_group(handle, *, n_obs, n_vars, numeric_obs, np, overrides=None) -> ModalityReport:
    report = ModalityReport(limits=dict(LIMITS))
    prefix = handle.name.rstrip("/")
    scope = f"Bounded file annotation inspection; at most {LIMITS['feature_annotations']} / {n_vars} features"
    var = handle.get("var")
    feature_rows = _sample_indices(n_vars, LIMITS["feature_annotations"], np)
    names = [f"feature row {i}" for i in feature_rows]
    families = ["unclassified"] * len(feature_rows)
    observed = set()
    suggested = set()
    try:
        if var is not None:
            index = _axis_index_name(var)
            if index:
                names = [
                    str(value) for value in _read_node_values(_field(var, index), feature_rows, np)
                ]
            fields = _axis_column_names(var)
            type_field = next(
                (name for name in ("feature_types", "feature_type", "modality") if name in fields),
                None,
            )
            if type_field:
                from .h5ad_dashboard import _validate_column

                _validate_column(_field(var, type_field), n_vars)
                types = _read_node_values(_field(var, type_field), feature_rows, np)
                families = [
                    FEATURE_TYPES.get(str(value).strip().casefold(), "unclassified")
                    for value in types
                ]
                observed.update(family for family in families if family != "unclassified")
                for family in sorted(observed):
                    report.evidence.append(
                        ModalityEvidence(
                            profile=family,
                            origin="file_annotation",
                            path=f"{prefix}/var/{type_field}",
                            value=", ".join(
                                sorted(
                                    {
                                        str(value)
                                        for value, kind in zip(types, families)
                                        if kind == family
                                    }
                                )
                            ),
                            scope=scope,
                        )
                    )
            if not observed and any(re.fullmatch(r"[^\s:]+:\d+-\d+", name) for name in names):
                suggested.add("atac")
                report.evidence.append(
                    ModalityEvidence(
                        profile="atac",
                        origin="file_annotation",
                        path=f"{prefix}/var/index",
                        value="Interval-like feature names",
                        scope=scope + "; intervals alone do not establish an ATAC assay",
                    )
                )
    except (ValueError, TypeError, KeyError, IndexError, OSError) as exc:
        report.warnings.append(f"Feature annotation evidence unavailable: {exc}")
    for path in ("uns/assay", "uns/modality", "uns/technology"):
        value = scalar(handle, path)
        if value:
            hints = assay_profiles(value)
            suggested.update(hints)
            for profile in hints or ["unclassified"]:
                report.evidence.append(
                    ModalityEvidence(
                        profile=profile,
                        origin="file_annotation",
                        path=f"{prefix}/{path}",
                        value=value,
                        scope="File declaration only; does not validate measurements or assay",
                    )
                )

    rows = _sample_indices(n_obs, LIMITS["preview_rows"], np)
    # Select across feature families before filling remaining slots, to retain hybrids.
    selected = []
    for family in ("rna", "atac", "protein", "ion", "unclassified"):
        selected.extend([i for i, value in enumerate(families) if value == family][:2])
    selected = selected[: LIMITS["preview_features"]]
    try:
        if "X" in handle and selected and len(rows):
            cols = [int(feature_rows[i]) for i in selected]
            values = _preview_values(handle["X"], rows, cols, (n_obs, n_vars), np)
            for index, position in enumerate(selected):
                report.feature_previews.append(
                    FeaturePreview(
                        matrix_path=f"{prefix}/X",
                        name=names[position],
                        feature_index=cols[index],
                        family=families[position],
                        row_indices=rows.tolist(),
                        total_rows=n_obs,
                        values=[
                            float(value) if np.isfinite(value) else None
                            for value in values[:, index]
                        ],
                    )
                )
    except (ValueError, TypeError, KeyError, IndexError, OSError, OverflowError) as exc:
        report.warnings.append(f"Feature preview unavailable: {exc}")

    coord_frame = scalar(handle, "uns/cellondesk_spatial/coordinate_frame")
    image_frame = scalar(handle, "uns/cellondesk_spatial/image_frame")
    units = scalar(handle, "uns/cellondesk_spatial/units")
    obsm = handle.get("obsm")
    if obsm is not None:
        for key in ("spatial", "X_spatial"):
            try:
                node = _field(obsm, key)
                shape = _shape_from_node(node)
                if (
                    len(shape) != 2
                    or shape[0] != n_obs
                    or shape[1] < 2
                    or node.dtype.kind not in "iuf"
                ):
                    raise ValueError(
                        "Spatial coordinate axes do not match observation rows and two numeric dimensions"
                    )
                points = np.asarray(node[rows, :2], dtype=float)
                finite = np.isfinite(points).all(axis=1)
                report.spatial_previews.append(
                    SpatialPreview(
                        path=f"{prefix}/obsm/{key}",
                        row_indices=rows[finite].tolist(),
                        total_rows=n_obs,
                        points=points[finite].tolist(),
                        exclusions=int((~finite).sum()),
                        frame=coord_frame,
                        units=units,
                    )
                )
                report.evidence.append(
                    ModalityEvidence(
                        profile="spatial",
                        origin="file_structure",
                        path=f"{prefix}/obsm/{key}",
                        value=f"{shape[0]} rows × {shape[1]} axes",
                        scope="Row alignment checked; first two axes sampled; units/orientation not inferred",
                    )
                )
            except KeyError:
                continue
            except (ValueError, TypeError, IndexError, OSError, AttributeError) as exc:
                report.warnings.append(f"Spatial coordinates {key!r} unavailable: {exc}")
    spatial = handle.get("uns/spatial")
    if spatial is not None and hasattr(spatial, "keys"):
        for library in list(spatial.keys())[: LIMITS["images"]]:
            images = spatial[library].get("images") if hasattr(spatial[library], "get") else None
            if images is None or not hasattr(images, "keys"):
                continue
            for key in sorted(images.keys(), key=lambda name: (name != "lowres", name))[:1]:
                node = images[key]
                try:
                    shape = node.shape
                    if (
                        len(shape) not in (2, 3)
                        or min(shape[:2]) < 1
                        or (len(shape) == 3 and shape[2] not in (3, 4))
                    ):
                        raise ValueError("Unsupported embedded image axes/channels")
                    if node.dtype.kind not in "uif":
                        raise ValueError("Unsupported embedded image dtype")
                    step = max(1, int(np.ceil(max(shape[:2]) / LIMITS["image_side"])))
                    array = np.asarray(node[::step, ::step])
                    url, note = _png(array, np)
                    report.images.append(
                        ImagePreview(
                            path=f"{prefix}/uns/spatial/{library}/images/{key}",
                            original_shape=list(shape),
                            preview_shape=list(array.shape),
                            data_url=url,
                            note=f"Every {step}th pixel per axis. {note}",
                            frame=image_frame,
                        )
                    )
                except (ValueError, TypeError, IndexError, OSError, AttributeError) as exc:
                    report.warnings.append(f"Embedded image {library}/{key} unavailable: {exc}")

    supported = observed & {"rna", "atac"}
    if report.spatial_previews:
        for family, profile in (
            ("rna", "spatial_transcriptomics"),
            ("protein", "spatial_proteomics"),
            ("ion", "spatial_metabolomics"),
        ):
            if family in observed:
                supported.add(profile)
    if len(observed) > 1:
        supported.add("multiomics")
        report.evidence.append(
            ModalityEvidence(
                profile="multiomics",
                origin="file_structure",
                path=f"{prefix}/X",
                value="Multiple annotated feature families on one observation axis",
                scope="Storage correspondence only; biological pairing and cross-feature relationships are not established",
            )
        )
    for profile in sorted(supported | suggested):
        report.profiles.append(
            ProfileActivation(
                profile=profile,
                state="supported" if profile in supported else "suggested",
                reason="Supported by observed feature annotations/structure; experimental assay is not independently validated."
                if profile in supported
                else "Suggestive metadata only; confirm interpretation before drawing scientific conclusions.",
            )
        )
    apply_overrides(report, overrides)
    for key, family in (
        ("rna_values", "rna"),
        ("accessibility", "atac"),
        ("protein_values", "protein"),
        ("ion_values", "ion"),
    ):
        previews = [p for p in report.feature_previews if p.family == family]
        report.capabilities.append(
            capability(
                key,
                "available" if previews else "missing",
                "Bounded stored values; scale/normalization/units are not inferred."
                if previews
                else "No readable explicitly typed feature values found within inspection bounds.",
                [p.matrix_path for p in previews],
            )
        )
    for key, candidates in (
        ("rna_qc", {"total_counts", "n_genes_by_counts", "pct_counts_mt", "n_counts", "n_genes"}),
        (
            "atac_qc",
            {
                "tss_enrichment",
                "tss_score",
                "frip",
                "pct_reads_in_peaks",
                "n_fragments",
                "total_fragments",
            },
        ),
    ):
        paths = [f"{prefix}/obs/{name}" for name in numeric_obs if name.casefold() in candidates]
        readable_paths = []
        for path in paths:
            name = path.rsplit("/", 1)[-1]
            try:
                values = _read_node_values(_field(handle["obs"], name), rows, np)
                report.recorded_metrics.append(
                    RecordedMetric(
                        path=path,
                        name=name,
                        row_indices=rows.tolist(),
                        total_rows=n_obs,
                        values=[
                            float(value) if value is not None and np.isfinite(value) else None
                            for value in values
                        ],
                    )
                )
                readable_paths.append(path)
            except (ValueError, TypeError, KeyError, IndexError, OSError) as exc:
                report.warnings.append(f"Recorded metric {path} preview unavailable: {exc}")
        report.capabilities.append(
            capability(
                key,
                "available" if readable_paths else "missing",
                "Use recorded numeric metadata only; definitions/units remain source-defined."
                if readable_paths
                else "No readable matching numeric metadata was inspected; no QC metric computed.",
                readable_paths,
            )
        )
    report.capabilities.extend(
        [
            capability(
                "spatial_coordinates",
                "available" if report.spatial_previews else "missing",
                "First two stored axes, without inferred units or orientation."
                if report.spatial_previews
                else "No readable row-aligned spatial coordinates.",
            ),
            capability(
                "tissue_image",
                "available" if report.images else "missing",
                "Independent embedded image preview; no registration is implied."
                if report.images
                else "No supported embedded image; external images are not fetched.",
            ),
            capability(
                "image_overlay",
                "invalid"
                if coord_frame and image_frame and coord_frame != image_frame
                else "unsupported",
                f"Incompatible coordinate frames: {coord_frame} vs {image_frame}."
                if coord_frame and image_frame and coord_frame != image_frame
                else "No validated coordinate-to-image transform in this adapter; overlay withheld even if a scale factor is present.",
            ),
            capability(
                "gene_activity",
                "unsupported",
                "Gene-activity matrices require explicit feature identity and semantics; X or a similarly named layer is not assumed to be gene activity.",
            ),
            capability(
                "segmentation",
                "unsupported",
                "Segmentation geometry/object correspondence requires an imaging adapter; an obs label is not a segmentation mask.",
            ),
            capability(
                "neighborhoods",
                "unsupported",
                "No neighborhoods inferred from distances or an unverified coordinate frame.",
            ),
            capability(
                "joint_views",
                "unsupported",
                "Shared rows do not establish cross-feature biological relationships; no joint inference is performed.",
            ),
            capability(
                "mass_spectra",
                "unsupported",
                "Native spectra, ion identities, adducts and calibration require a format-specific MS adapter.",
            ),
        ]
    )
    if not report.profiles:
        report.warnings.append(
            "Scientific modality is unclassified. General H5AD views remain available; X is not assumed to be RNA."
        )
    if len(feature_rows) < n_vars:
        report.warnings.append(
            f"Feature evidence inspects {len(feature_rows)} / {n_vars} rows; unobserved modalities may be present."
        )
    return report
