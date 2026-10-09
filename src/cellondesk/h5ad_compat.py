from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import expression as _expression
from . import inspection as _core
from ._version import __version__
from .h5ad_access import (
    _axis_column_names,
    _axis_index_name,  # noqa: F401 - historical import used by legacy_feature_compat
    _axis_length,
    _candidate_feature_nodes,
    _container_keys,
    _contains_field,  # noqa: F401 - historical import used by legacy_feature_compat
    _encoding,
    _field,
)
from .h5ad_dashboard import matrix_warnings, observation_sample
from .inspection import (
    EmbeddingPreview,
    H5ADInspection,
    InspectionProvenance,
    MatrixSummary,
    ObservationSample,
)


def _embedding_previews(
    handle: Any,
    *,
    n_obs: int,
    annotation: str | None,
    max_points: int,
    np: Any,
    metadata: ObservationSample | None = None,
) -> tuple[list[EmbeddingPreview], list[str]]:
    warnings: list[str] = []
    if "obsm" not in handle:
        return [], warnings
    obsm = handle["obsm"]
    keys = _container_keys(obsm)
    priority = {"X_umap": 0, "spatial": 1, "X_spatial": 1, "X_tsne": 2, "X_pca": 3}
    keys.sort(key=lambda key: (priority.get(key, 10), key))
    indices = _core._sample_indices(n_obs, max_points, np)

    color_values: list[str] = []
    if metadata and annotation:
        column = next((c for c in metadata.columns if c.name == annotation), None)
        if column:
            color_values = ["Missing" if v is None else str(v) for v in column.values]

    previews: list[EmbeddingPreview] = []
    for key in keys:
        if key.casefold().startswith("velocity"):
            warnings.append(f"Excluded vector field {key!r} from coordinate embeddings.")
            continue
        if len(previews) >= 4:
            warnings.append(f"Embedding {key!r} omitted: the four-preview limit was reached.")
            continue
        node = _field(obsm, key)
        shape = _core._shape_from_node(node)
        if not hasattr(node, "dtype") or len(shape) != 2 or shape[1] < 2:
            warnings.append(
                f"Skipped unsupported embedding {key!r} with shape {shape or 'unknown'}."
            )
            continue
        if shape[0] != n_obs:
            warnings.append(f"Skipped embedding {key!r}: row count does not match observations.")
            continue
        if node.dtype.kind not in "biuf":
            warnings.append(
                f"Skipped embedding {key!r}: coordinates must have a real numeric dtype."
            )
            continue
        try:
            coordinates = np.asarray(node[indices, :2], dtype=float)
        except (TypeError, ValueError, IndexError, OSError) as exc:
            warnings.append(f"Could not sample embedding {key!r}: {exc}")
            continue
        finite_rows = np.isfinite(coordinates).all(axis=1)
        dropped = int(len(indices) - np.count_nonzero(finite_rows))
        if dropped:
            warnings.append(f"Embedding {key!r}: dropped {dropped} sampled non-finite coordinates.")
        coordinates = coordinates[finite_rows]
        colors = (
            [color for color, keep in zip(color_values, finite_rows, strict=False) if bool(keep)]
            if color_values
            else []
        )
        previews.append(
            EmbeddingPreview(
                key=key,
                total_points=int(shape[0]),
                dimensions=int(shape[1]),
                sampled_points=coordinates.tolist(),
                color_field=annotation if colors else None,
                color_values=colors,
                row_indices=indices[finite_rows].tolist(),
                candidate_points=len(indices),
                dropped_nonfinite=dropped,
            )
        )
    return previews, warnings


def install_legacy_h5ad_compatibility() -> None:
    """Install robust dataframe metadata helpers in the shared readers."""
    _expression._encoding = _encoding
    _expression._candidate_feature_nodes = _candidate_feature_nodes


install_legacy_h5ad_compatibility()


def inspect_h5ad(
    path: str | Path,
    *,
    max_points: int = 5000,
    annotation: str | None = None,
    max_column_values: int = 20000,
    max_obs_columns: int = 50,
    max_var_columns: int = 30,
    modality_override: list[str] | tuple[str, ...] | None = None,
) -> H5ADInspection:
    """Inspect modern and legacy AnnData H5AD layouts with bounded reads."""
    h5py, np = _core._require_data_dependencies()
    source = Path(path).expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError(source)
    if source.suffix.lower() != ".h5ad":
        raise ValueError(f"Expected an .h5ad file, received: {source.name}")
    limits = {
        "max_points": max_points,
        "max_column_values": max_column_values,
        "max_obs_columns": max_obs_columns,
        "max_var_columns": max_var_columns,
    }
    for name, value in limits.items():
        minimum = 0 if name in {"max_obs_columns", "max_var_columns"} else 1
        if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
            qualifier = "nonnegative" if minimum == 0 else "positive"
            raise ValueError(f"{name} must be a {qualifier} integer")

    warnings: list[str] = []
    before = source.stat()
    with h5py.File(source, "r") as handle:
        obs_table, var_table = handle.get("obs"), handle.get("var")
        n_obs = _axis_length(obs_table) if obs_table is not None else 0
        n_vars = _axis_length(var_table) if var_table is not None else 0
        for name, table in (("obs", obs_table), ("var", var_table)):
            if table is not None and not hasattr(table, "keys") and not table.dtype.names:
                warnings.append(
                    f"Unsupported {name} table layout; no annotation columns inspected."
                )
        try:
            matrix = _core._matrix_summary(handle, n_obs, n_vars, np)
        except (KeyError, TypeError, ValueError, IndexError, OSError) as exc:
            matrix = MatrixSummary(shape=(n_obs, n_vars), encoding="unsupported")
            warnings.append(f"Could not summarize X: {exc}.")
        if obs_table is None:
            n_obs = matrix.shape[0]
            warnings.append("Observation metadata obs is absent.")
        if var_table is None:
            n_vars = matrix.shape[1]
            warnings.append("Variable metadata var is absent.")
        try:
            warnings.extend(matrix_warnings(handle, (n_obs, n_vars)))
        except (KeyError, TypeError, ValueError, IndexError, OSError) as exc:
            warnings.append(f"Could not check X structure: {exc}.")
        if matrix.nonfinite_entries:
            warnings.append(f"X sample contains {matrix.nonfinite_entries} non-finite entries.")

        obs_names = _axis_column_names(obs_table) if obs_table is not None else []
        var_names = _axis_column_names(var_table) if var_table is not None else []
        likely_annotation = _core._choose_annotation(obs_names, annotation)
        if annotation and likely_annotation is None:
            warnings.append(f"Requested annotation column {annotation!r} was not found.")
        selected_obs_names = obs_names[:max_obs_columns]
        if likely_annotation and likely_annotation not in selected_obs_names:
            selected_obs_names.append(likely_annotation)
        obs_indices = _core._sample_indices(n_obs, max_column_values, np)
        embedding_indices = _core._sample_indices(n_obs, max_points, np)
        obs_sample, obs_columns = observation_sample(
            obs_table,
            selected_obs_names,
            total=n_obs,
            indices=obs_indices,
            np=np,
            warnings=warnings,
        )
        if np.array_equal(obs_indices, embedding_indices):
            embedding_metadata = obs_sample
        else:
            embedding_metadata, _ = observation_sample(
                obs_table,
                selected_obs_names,
                total=n_obs,
                indices=embedding_indices,
                np=np,
                warnings=warnings,
            )
        _, var_columns = observation_sample(
            var_table,
            var_names[:max_var_columns],
            total=n_vars,
            indices=_core._sample_indices(n_vars, max_column_values, np),
            np=np,
            warnings=warnings,
            axis="var",
        )
        embeddings, embedding_warnings = _embedding_previews(
            handle,
            n_obs=n_obs,
            annotation=likely_annotation,
            max_points=max_points,
            np=np,
            metadata=embedding_metadata,
        )
        warnings.extend(embedding_warnings)
        from .modality_h5ad import inspect_group

        scientific = inspect_group(
            handle,
            n_obs=n_obs,
            n_vars=n_vars,
            numeric_obs=[column.name for column in obs_columns if column.numeric is not None],
            np=np,
            overrides=modality_override,
        )
        if len(obs_indices) < n_obs:
            warnings.append(
                f"Observation summaries/composition use {len(obs_indices):,} of {n_obs:,} rows; "
                "deterministic evenly spaced sampling is not random or necessarily "
                "representative. Rare categories may be missed; counts are not population totals."
            )
        if len(embedding_indices) < n_obs:
            warnings.append(
                f"Embeddings select at most {len(embedding_indices):,} of {n_obs:,} rows "
                "before excluding non-finite coordinates."
            )
        if len(obs_names) > len(obs_columns):
            warnings.append(
                f"Detailed summaries include {len(obs_columns)} of {len(obs_names)} obs columns. "
                "Omitted/unsupported columns are unavailable for dashboard controls."
            )
        if len(var_names) > len(var_columns):
            warnings.append(
                f"Detailed summaries include {len(var_columns)} of {len(var_names)} var columns."
            )
        if not embeddings:
            warnings.append("No two-dimensional previewable embedding was found in obsm.")
        after = source.stat()
        unchanged = (before.st_size, before.st_mtime_ns, before.st_ino, before.st_dev) == (
            after.st_size,
            after.st_mtime_ns,
            after.st_ino,
            after.st_dev,
        )
        if not unchanged:
            warnings.append(
                "Source size/mtime/identity changed during inspection; regenerate report."
            )
        return H5ADInspection(
            source_path=str(source),
            file_name=source.name,
            file_size_bytes=before.st_size,
            n_obs=n_obs,
            n_vars=n_vars,
            matrix=matrix,
            obs_column_names=obs_names,
            var_column_names=var_names,
            obs_columns=obs_columns,
            var_columns=var_columns,
            layers=_container_keys(handle["layers"]) if "layers" in handle else [],
            obsm=_container_keys(handle["obsm"]) if "obsm" in handle else [],
            uns=_container_keys(handle["uns"]) if "uns" in handle else [],
            has_raw="raw" in handle,
            likely_annotation=likely_annotation,
            embeddings=embeddings,
            warnings=list(dict.fromkeys(warnings)),
            obs_sample=obs_sample,
            embedding_metadata=embedding_metadata,
            scientific=scientific,
            provenance=InspectionProvenance(
                generator_version=__version__,
                inspected_at=datetime.now(timezone.utc).isoformat(),
                source_mtime_ns=before.st_mtime_ns,
                source_stat_unchanged=unchanged,
                encoding_type=_encoding(handle),
                encoding_version=str(
                    _core._decode_scalar(
                        handle.attrs.get("encoding-version", "Not recorded"),
                    )
                ),
                limits=limits,
                dependencies={"h5py": h5py.__version__, "numpy": np.__version__},
            ),
        )


__all__ = ["H5ADInspection", "inspect_h5ad"]
