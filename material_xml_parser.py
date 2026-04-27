#!/usr/bin/env python3
"""Parser for Ansys Granta MatML/EngineeringData XML files."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
import xml.etree.ElementTree as ET


def _text(node: Optional[ET.Element]) -> str:
    return (node.text or "").strip() if node is not None and node.text else ""


def _split_csv(value: str) -> List[str]:
    parts = [v.strip() for v in value.split(",")]
    return [v for v in parts if v != ""]


def _maybe_number(value: str, as_string: bool = False) -> Any:
    if as_string:
        return value
    try:
        if value.lower() in {"true", "false"}:
            return value.lower() == "true"
    except AttributeError:
        return value
    try:
        if any(ch in value for ch in [".", "e", "E"]):
            return float(value)
        return int(value)
    except (ValueError, TypeError):
        return value


def _read_qualifiers(parent: ET.Element) -> Dict[str, str]:
    qualifiers: Dict[str, str] = {}
    for q in parent.findall("Qualifier"):
        name = q.attrib.get("name") or q.attrib.get("Name")
        if not name:
            continue
        qualifiers[name] = q.attrib.get("value") or _text(q)
    return qualifiers


def _unit_string(parameter_details: ET.Element) -> Optional[str]:
    if parameter_details.find("Unitless") is not None:
        return None

    units_node = parameter_details.find("Units")
    if units_node is None:
        return None

    parts: List[str] = []
    for unit in units_node.findall("Unit"):
        base = _text(unit.find("Name")) or _text(unit)
        if not base:
            continue
        power = unit.attrib.get("power")
        parts.append(f"{base}^{power}" if power is not None else base)

    return " ".join(parts) if parts else None


@dataclass
class IndependentValue:
    name: str
    value: Any
    unit: Optional[str] = None
    default: Optional[Any] = None
    qualifiers: Dict[str, str] = field(default_factory=dict)


@dataclass
class PropertyPoint:
    dependent: Any
    independent: List[IndependentValue] = field(default_factory=list)


@dataclass
class MaterialProperty:
    name: str
    unit: Optional[str]
    qualifiers: Dict[str, str] = field(default_factory=dict)
    interpolation: Optional[str] = None
    extrapolation: Optional[str] = None
    values: List[PropertyPoint] = field(default_factory=list)
    parameter_qualifiers: Dict[str, Dict[str, str]] = field(default_factory=dict)


@dataclass
class Material:
    name: str
    description: str = ""
    material_class: str = ""
    subclass: str = ""
    properties: Dict[str, MaterialProperty] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["class"] = data.pop("material_class")
        return data


@dataclass
class MaterialDatabase:
    materials: List[Material]

    def get_material(self, name: str) -> Optional[Material]:
        target = name.casefold()
        for material in self.materials:
            if material.name.casefold() == target:
                return material
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {"materials": [m.to_dict() for m in self.materials]}

    def to_json(self, filepath: Optional[str] = None, indent: int = 2) -> str:
        payload = json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)
        if filepath:
            Path(filepath).write_text(payload, encoding="utf-8")
        return payload


def _parse_metadata(matml_doc: ET.Element) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, str]]:
    metadata = matml_doc.find("Metadata")
    if metadata is None:
        return {}, {}

    params: Dict[str, Dict[str, Any]] = {}
    props: Dict[str, str] = {}

    for p in metadata.findall("ParameterDetails"):
        pid = p.attrib.get("id", "")
        if not pid:
            continue
        params[pid] = {
            "name": _text(p.find("Name")) or pid,
            "unit": _unit_string(p),
        }

    for p in metadata.findall("PropertyDetails"):
        prid = p.attrib.get("id", "")
        if not prid:
            continue
        props[prid] = _text(p.find("Name")) or prid

    return params, props


def _iter_matml_docs(root: ET.Element) -> Iterable[ET.Element]:
    if root.tag == "MatML_Doc":
        yield root
        return

    if root.tag == "EngineeringData":
        mats = root.find("Materials")
        if mats is not None:
            for doc in mats.findall("MatML_Doc"):
                yield doc
        else:
            for doc in root.findall("MatML_Doc"):
                yield doc
        return

    if root.tag == "merged":
        for item in root.findall("item"):
            eng = item.find("EngineeringData")
            if eng is not None:
                yield from _iter_matml_docs(eng)
        return

    for eng in root.findall(".//EngineeringData"):
        yield from _iter_matml_docs(eng)


def _parse_property_data(
    node: ET.Element,
    param_lookup: Dict[str, Dict[str, Any]],
    prop_lookup: Dict[str, str],
) -> MaterialProperty:
    prop_id = node.attrib.get("property", "")
    prop_name = prop_lookup.get(prop_id, prop_id or "Unknown Property")

    property_qualifiers = _read_qualifiers(node)
    if property_qualifiers.get("Display", "").lower() == "false":
        # Keep behavior configurable by caller if needed; default keeps the property.
        pass

    dependent_values: Optional[List[Any]] = None
    dependent_qualifiers: Dict[str, str] = {}
    dependent_unit: Optional[str] = None
    independent_series: List[Dict[str, Any]] = []

    interpolation = None
    extrapolation = None
    parameter_qualifiers: Dict[str, Dict[str, str]] = {}

    for pv in node.findall("ParameterValue"):
        parameter_id = pv.attrib.get("parameter", "")
        fmt = pv.attrib.get("format", "float").lower()
        raw_data = _text(pv.find("Data"))
        qualifiers = _read_qualifiers(pv)
        parameter_qualifiers[parameter_id] = qualifiers

        # Interpolation options node
        if parameter_id == "pa6":
            interpolation = qualifiers.get("AlgorithmType", interpolation)
            extrapolation = qualifiers.get("ExtrapolationType", extrapolation)
            continue

        values_raw = _split_csv(raw_data)
        values = [_maybe_number(v, as_string=(fmt == "string")) for v in values_raw]

        variable_type_raw = qualifiers.get("Variable Type", "")
        variable_type_items = [v.strip().casefold() for v in _split_csv(variable_type_raw)] if variable_type_raw else []

        role: str
        if any("independent" in v for v in variable_type_items):
            role = "independent"
        elif any("dependent" in v for v in variable_type_items):
            role = "dependent"
        else:
            # Fallback behavior for malformed files.
            role = "dependent" if dependent_values is None else "independent"

        pmeta = param_lookup.get(parameter_id, {"name": parameter_id, "unit": None})

        if role == "dependent":
            dependent_values = values
            dependent_qualifiers = qualifiers
            dependent_unit = pmeta.get("unit")
        else:
            field_name = qualifiers.get("Field Variable") or pmeta.get("name") or parameter_id
            field_unit = qualifiers.get("Field Units") or pmeta.get("unit")
            default_raw = qualifiers.get("Default Data")
            independent_series.append(
                {
                    "name": field_name,
                    "unit": field_unit,
                    "default": _maybe_number(default_raw) if default_raw else None,
                    "values": values,
                    "qualifiers": qualifiers,
                }
            )

    if dependent_values is None:
        raise ValueError(f"Property '{prop_name}' has no dependent series.")

    points_count = len(dependent_values)
    for series in independent_series:
        if len(series["values"]) != points_count:
            raise ValueError(
                f"Length mismatch in '{prop_name}': dependent has {points_count}, "
                f"{series['name']} has {len(series['values'])}."
            )

    points: List[PropertyPoint] = []
    for idx in range(points_count):
        indep_values = [
            IndependentValue(
                name=series["name"],
                value=series["values"][idx],
                unit=series["unit"],
                default=series["default"],
                qualifiers=series["qualifiers"],
            )
            for series in independent_series
        ]
        points.append(PropertyPoint(dependent=dependent_values[idx], independent=indep_values))

    # Merge dependent qualifiers only if absent at property level.
    for key, value in dependent_qualifiers.items():
        property_qualifiers.setdefault(key, value)

    return MaterialProperty(
        name=prop_name,
        unit=dependent_unit,
        qualifiers=property_qualifiers,
        interpolation=interpolation,
        extrapolation=extrapolation,
        values=points,
        parameter_qualifiers=parameter_qualifiers,
    )


def load_from_xml(filepath: str) -> MaterialDatabase:
    root = ET.parse(filepath).getroot()
    materials: List[Material] = []

    for doc in _iter_matml_docs(root):
        param_lookup, prop_lookup = _parse_metadata(doc)

        for mat_node in doc.findall("Material"):
            bulk = mat_node.find("BulkDetails")
            if bulk is None:
                continue

            material = Material(
                name=_text(bulk.find("Name")),
                description=_text(bulk.find("Description")),
                material_class=_text(bulk.find("Class/Name")),
                subclass=_text(bulk.find("Subclass/Name")),
                properties={},
            )

            for prop_node in bulk.findall("PropertyData"):
                parsed_prop = _parse_property_data(prop_node, param_lookup, prop_lookup)
                material.properties[parsed_prop.name] = parsed_prop

            materials.append(material)

    return MaterialDatabase(materials=materials)


def to_json(material_db: MaterialDatabase, filepath: str) -> None:
    material_db.to_json(filepath=filepath)


def get_material(material_db: MaterialDatabase, name: str) -> Optional[Material]:
    return material_db.get_material(name)


def evaluate_property(material: Material, prop_name: str, **field_vars: float) -> float:
    """Optional helper: evaluate property.

    - If property has no independents, returns first dependent value.
    - If one independent variable is provided, returns linear interpolation.
    - If multiple independents, returns exact-match dependent only.
    """

    prop = material.properties[prop_name]
    if not prop.values:
        raise ValueError(f"Property '{prop_name}' has no data points.")

    indep_dim = len(prop.values[0].independent)
    if indep_dim == 0:
        return float(prop.values[0].dependent)

    if indep_dim == 1:
        field_name = prop.values[0].independent[0].name
        if field_name not in field_vars:
            raise ValueError(f"Missing field variable '{field_name}'.")
        x = float(field_vars[field_name])

        pairs = sorted((float(p.independent[0].value), float(p.dependent)) for p in prop.values)
        if x <= pairs[0][0]:
            return pairs[0][1]
        if x >= pairs[-1][0]:
            return pairs[-1][1]

        for (x0, y0), (x1, y1) in zip(pairs, pairs[1:]):
            if x0 <= x <= x1:
                if x1 == x0:
                    return y0
                t = (x - x0) / (x1 - x0)
                return y0 + t * (y1 - y0)

    # Multi-dimensional fallback: exact match only
    for point in prop.values:
        if all(iv.name in field_vars and float(field_vars[iv.name]) == float(iv.value) for iv in point.independent):
            return float(point.dependent)

    raise ValueError(f"Could not evaluate '{prop_name}' for {field_vars}.")


__all__ = [
    "IndependentValue",
    "PropertyPoint",
    "MaterialProperty",
    "Material",
    "MaterialDatabase",
    "load_from_xml",
    "to_json",
    "get_material",
    "evaluate_property",
]
