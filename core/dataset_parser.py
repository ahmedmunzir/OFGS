"""Turn OpenFOAM post-processing files into logical plotting datasets.

This module owns all knowledge of OpenFOAM file layouts.  In particular, a
consumer of :class:`Dataset` never needs to know which source file or column a
value came from.
"""

from dataclasses import dataclass, field, replace
from pathlib import Path
import re
from typing import Dict, List, Mapping, Sequence, Tuple


Number = float


@dataclass(frozen=True)
class Dataset:
    """A graph-ready logical dataset."""

    title: str
    x_axis: Tuple[Number, ...]
    series: Mapping[str, Tuple[Number, ...]]
    x_axis_title: str = "Time"
    physical_quantity: str = ""
    source: str = ""
    graph_priority: int = field(init=False, default=100)
    graph_type: str = field(init=False, default="time_series")

    @property
    def priority(self):
        """Short alias useful to layout and sorting code."""
        return self.graph_priority

    @property
    def data_series(self):
        """Explicit alias for callers that prefer the longer name."""
        return self.series

    @property
    def identity(self):
        """Stable identity of the logical graph, independent of its source file."""
        quantity = self.physical_quantity or self.title
        return (
            self.graph_type,
            quantity.casefold(),
            self.title.casefold(),
        )


@dataclass(frozen=True)
class ResidualDataset(Dataset):
    graph_priority: int = field(init=False, default=10)
    graph_type: str = field(init=False, default="residual")


@dataclass(frozen=True)
class ScalarTimeSeriesDataset(Dataset):
    graph_priority: int = field(init=False, default=30)
    graph_type: str = field(init=False, default="scalar_time_series")


@dataclass(frozen=True)
class VectorTimeSeriesDataset(Dataset):
    graph_priority: int = field(init=False, default=30)
    graph_type: str = field(init=False, default="vector_time_series")


@dataclass(frozen=True)
class FieldMinMaxDataset(Dataset):
    graph_priority: int = field(init=False, default=20)
    graph_type: str = field(init=False, default="field_min_max")


@dataclass(frozen=True)
class PatchYPlusDataset(Dataset):
    graph_priority: int = field(init=False, default=40)
    graph_type: str = field(init=False, default="patch_y_plus")


_ROW_TOKEN = re.compile(r"\([^)]*\)|\S+")
_VECTOR_COMPONENTS = ("x", "y", "z")


def _tokens(line: str) -> List[str]:
    """Split a row while keeping an OpenFOAM parenthesised vector together."""
    return _ROW_TOKEN.findall(line)


def _value(token: str) -> Tuple[Number, ...]:
    text = token.strip("()")
    try:
        return (float(text),)
    except ValueError:
        if token.startswith("(") and token.endswith(")"):
            try:
                return tuple(float(part) for part in text.split())
            except ValueError:
                pass
    return ()


def _read_file(path: Path):
    headers = []
    rows = []
    try:
        with path.open() as stream:
            for raw_line in stream:
                line = raw_line.strip()
                if not line:
                    continue
                if line.startswith("#"):
                    text = line.lstrip("#").strip()
                    if text:
                        headers.append(_tokens(text))
                    continue
                rows.append(_tokens(line))
    except (OSError, UnicodeError):
        return [], []
    return headers, rows


def _source_label(path: Path) -> str:
    """Return a concise function-object/time/file provenance label."""
    parts = path.parts
    try:
        post_processing_index = len(parts) - 1 - parts[::-1].index("postProcessing")
    except ValueError:
        return str(path)
    return str(Path(*parts[post_processing_index + 1:]))


def _column_header(headers: Sequence[Sequence[str]], row_width: int) -> List[str]:
    candidates = [list(header) for header in headers if header and header[0].lower() == "time"]
    if not candidates:
        return []
    # Metadata comments may also begin with "Time"; the widest candidate is the
    # actual table heading in normal OpenFOAM output.
    return max(candidates, key=lambda header: min(len(header), row_width))


def _title(owner: str, quantity: str, quantity_count: int) -> str:
    if quantity_count == 1 and quantity.lower() in {"value", owner.lower()}:
        return owner
    return f"{owner} - {quantity}"


def _components(
    rows: Sequence[Sequence[str]], value_index: int
) -> Tuple[Tuple[Number, ...], ...]:
    result = []
    for row in rows:
        if value_index >= len(row):
            return ()
        parsed = _value(row[value_index])
        if not parsed:
            return ()
        result.append(parsed)
    if not result or len({len(value) for value in result}) != 1:
        return ()
    return tuple(result)


def _time_series(owner: str, path: Path):
    headers, rows = _read_file(path)
    rows = [row for row in rows if row and len(_value(row[0])) == 1]
    if not rows or len(rows[0]) < 2:
        return []

    width = min(len(row) for row in rows)
    headings = _column_header(headers, width)
    quantity_count = width - 1
    names = headings[1:width] if len(headings) >= width else []
    if len(names) != quantity_count:
        names = ["Value"] if quantity_count == 1 else [
            f"Value {index}" for index in range(1, quantity_count + 1)
        ]

    # A vector is normally written as one parenthesised value.  Some producers
    # instead write three scalar columns named Ux/Uy/Uz (or U_x/U_y/U_z);
    # recognise those as one physical quantity too.
    quantities = []
    index = 0
    while index < len(names):
        component_match = re.match(r"(.+?)(?:_)?([xyz])$", names[index], re.IGNORECASE)
        if component_match and index + 2 < len(names):
            base = component_match.group(1)
            matches = [
                re.match(r"(.+?)(?:_)?([xyz])$", candidate, re.IGNORECASE)
                for candidate in names[index:index + 3]
            ]
            if (
                all(matches)
                and all(match.group(1) == base for match in matches)
                and [match.group(2).lower() for match in matches] == ["x", "y", "z"]
            ):
                quantities.append((base, tuple(range(index + 1, index + 4)), _VECTOR_COMPONENTS))
                index += 3
                continue
        quantities.append((names[index], (index + 1,), (names[index],)))
        index += 1

    x_axis = tuple(_value(row[0])[0] for row in rows)
    datasets = []
    for name, indices, labels in quantities:
        dataset_title = _title(owner, name, quantity_count)
        if len(indices) == 1:
            values = _components(rows, indices[0])
            if not values:
                continue
            component_count = len(values[0])
        else:
            values = ()
            component_count = len(indices)

        if component_count == 1:
            datasets.append(
                ScalarTimeSeriesDataset(
                    title=dataset_title,
                    x_axis=x_axis,
                    series={name: tuple(value[0] for value in values)},
                    physical_quantity=name,
                    source=_source_label(path),
                )
            )
        else:
            if len(indices) == 1:
                labels = _VECTOR_COMPONENTS[:component_count]
                if len(labels) < component_count:
                    labels += tuple(str(i) for i in range(len(labels), component_count))
                named_series = {
                    label: tuple(value[i] for value in values)
                    for i, label in enumerate(labels)
                }
            else:
                named_series = {}
                for label, value_index in zip(labels, indices):
                    component_values = _components(rows, value_index)
                    if not component_values or len(component_values[0]) != 1:
                        named_series = {}
                        break
                    named_series[label] = tuple(value[0] for value in component_values)
                if not named_series:
                    continue
            datasets.append(
                VectorTimeSeriesDataset(
                    title=dataset_title,
                    x_axis=x_axis,
                    series=named_series,
                    physical_quantity=name,
                    source=_source_label(path),
                )
            )
    return datasets


def _residuals(owner: str, path: Path):
    headers, rows = _read_file(path)
    rows = [row for row in rows if row and len(_value(row[0])) == 1]
    if not rows:
        return []
    width = min(len(row) for row in rows)
    headings = _column_header(headers, width)
    if not headings:
        headings = ["Time"] + [f"Column{index}" for index in range(2, width + 1)]

    metrics: Dict[str, Dict[str, int]] = {}
    for index, heading in enumerate(headings[1:width], start=1):
        match = re.match(r"(.+?)_(initial|final)(?:Residual)?$", heading, re.IGNORECASE)
        if match:
            field, metric = match.groups()
            metrics.setdefault(field, {})[metric.lower()] = index

    # Some older files use unqualified InitialResidual/FinalResidual headings.
    if not metrics:
        lowered = [heading.lower() for heading in headings]
        initial = next((i for i, value in enumerate(lowered) if "initial" in value), None)
        final = next((i for i, value in enumerate(lowered) if "final" in value), None)
        if initial is not None:
            metrics[owner] = {"initial": initial}
            if final is not None:
                metrics[owner]["final"] = final

    datasets = []
    x_axis = tuple(_value(row[0])[0] for row in rows)
    for field, indices in metrics.items():
        named_series = {}
        for metric_name in ("initial", "final"):
            index = indices.get(metric_name)
            values = _components(rows, index) if index is not None else ()
            if values and len(values[0]) == 1:
                named_series[metric_name.capitalize()] = tuple(value[0] for value in values)
        if named_series:
            datasets.append(
                ResidualDataset(
                    title=_title(owner, field, len(metrics)),
                    x_axis=x_axis,
                    series=named_series,
                    physical_quantity=field,
                    source=_source_label(path),
                )
            )
    return datasets


def _grouped_rows(rows: Sequence[Sequence[str]], label_index: int):
    grouped: Dict[str, List[Sequence[str]]] = {}
    for row in rows:
        if len(row) > label_index and len(_value(row[0])) == 1:
            grouped.setdefault(row[label_index], []).append(row)
    return grouped


def _field_min_max(owner: str, path: Path):
    headers, rows = _read_file(path)
    if not rows:
        return []
    width = min(len(row) for row in rows)
    headings = _column_header(headers, width)
    lowered = [heading.lower() for heading in headings]
    field_index = next(
        (i for i, value in enumerate(lowered) if value in {"field", "fieldname"}), 1
    )
    min_index = next((i for i, value in enumerate(lowered) if value == "min"), 2)
    max_index = next((i for i, value in enumerate(lowered) if value == "max"), 3)
    groups = _grouped_rows(rows, field_index)

    datasets = []
    for field, field_rows in sorted(groups.items()):
        minima = _components(field_rows, min_index)
        maxima = _components(field_rows, max_index)
        if not minima or not maxima or len(minima[0]) != len(maxima[0]):
            continue
        x_axis = tuple(_value(row[0])[0] for row in field_rows)
        if len(minima[0]) == 1:
            series = {
                "Min": tuple(value[0] for value in minima),
                "Max": tuple(value[0] for value in maxima),
            }
        else:
            series = {}
            for index in range(len(minima[0])):
                label = _VECTOR_COMPONENTS[index] if index < 3 else str(index)
                series[f"Min {label}"] = tuple(value[index] for value in minima)
                series[f"Max {label}"] = tuple(value[index] for value in maxima)
        datasets.append(
            FieldMinMaxDataset(
                title=f"{field} (Min/Max)",
                x_axis=x_axis,
                series=series,
                physical_quantity=field,
                source=_source_label(path),
            )
        )
    return datasets


def _patch_y_plus(owner: str, path: Path):
    headers, rows = _read_file(path)
    if not rows:
        return []
    width = min(len(row) for row in rows)
    headings = _column_header(headers, width)
    lowered = [heading.lower() for heading in headings]
    has_patch_column = width >= 5 and not _value(rows[0][1])
    patch_index = 1 if has_patch_column else None
    min_index = next((i for i, value in enumerate(lowered) if value == "min"), 2 if has_patch_column else 1)
    max_index = next((i for i, value in enumerate(lowered) if value == "max"), 3 if has_patch_column else 2)
    average_index = next(
        (i for i, value in enumerate(lowered) if value in {"average", "avg", "mean"}),
        4 if has_patch_column else 3,
    )
    groups = _grouped_rows(rows, patch_index) if patch_index is not None else {owner: rows}

    datasets = []
    for patch, patch_rows in sorted(groups.items()):
        values_by_name = {}
        for label, index in (("Min", min_index), ("Max", max_index), ("Average", average_index)):
            values = _components(patch_rows, index)
            if values and len(values[0]) == 1:
                values_by_name[label] = tuple(value[0] for value in values)
        if len(values_by_name) != 3:
            continue
        datasets.append(
            PatchYPlusDataset(
                title=f"{patch} y+",
                x_axis=tuple(_value(row[0])[0] for row in patch_rows),
                series=values_by_name,
                physical_quantity=patch,
                source=_source_label(path),
            )
        )
    return datasets


_PARSERS = {
    "surfaceFieldValue.dat": _time_series,
    "solverInfo.dat": _residuals,
    "fieldMinMax.dat": _field_min_max,
    "patchYPlus.dat": _patch_y_plus,
    "yPlus.dat": _patch_y_plus,
}


def parse_data_file(name: str, path: Path):
    """Parse one supported OpenFOAM data file into logical datasets."""
    parser = _PARSERS.get(path.name)
    return parser(name, path) if parser else []


def _merge_logical_datasets(datasets: Sequence[Dataset]) -> Dataset:
    """Combine source fragments which represent one logical graph."""
    ordered = sorted(datasets, key=lambda dataset: dataset.source.casefold())
    first = ordered[0]
    series_names = []
    for dataset in ordered:
        for name in dataset.series:
            if name not in series_names:
                series_names.append(name)

    values_by_series = {name: {} for name in series_names}
    for dataset in ordered:
        for name, values in dataset.series.items():
            for x_value, y_value in zip(dataset.x_axis, values):
                # A deterministic source order resolves overlapping samples.
                values_by_series[name].setdefault(x_value, y_value)

    shared_x_values = set(values_by_series[series_names[0]])
    for values in values_by_series.values():
        shared_x_values.intersection_update(values)
    x_axis = tuple(sorted(shared_x_values))
    merged_series = {
        name: tuple(values_by_series[name][x_value] for x_value in x_axis)
        for name in series_names
    }
    sources = tuple(dict.fromkeys(dataset.source for dataset in ordered if dataset.source))
    return replace(
        first,
        x_axis=x_axis,
        series=merged_series,
        source=", ".join(sources),
    )


def _unique_datasets(datasets: Sequence[Dataset]) -> List[Dataset]:
    grouped: Dict[Tuple[str, str, str], List[Dataset]] = {}
    for dataset in datasets:
        grouped.setdefault(dataset.identity, []).append(dataset)
    return [_merge_logical_datasets(group) for group in grouped.values()]


def parse_datasets(outputs) -> List[Dataset]:
    """Convert the result of ``discover_post_processing`` into datasets."""
    datasets = []
    for name, info in outputs.items():
        latest = info.get("latest")
        latest_path = Path(latest).absolute() if latest is not None else None
        seen_paths = set()
        for path in info.get("files", ()):
            path = Path(path)
            path_key = path.absolute()
            if path_key in seen_paths:
                continue
            seen_paths.add(path_key)
            if latest_path is not None and path.parent.absolute() != latest_path:
                continue
            datasets.extend(parse_data_file(name, path))
    datasets = _unique_datasets(datasets)
    return sorted(datasets, key=lambda dataset: (dataset.graph_priority, dataset.title))
