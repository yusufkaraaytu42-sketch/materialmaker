#!/usr/bin/env python3
"""GUI tool to build EngineeringData XML compatible with Ansys Mechanical."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import xml.etree.ElementTree as ET
from xml.dom import minidom
import zipfile


@dataclass
class DataSeries:
    name: str
    unit: str = ""
    values: List[str] = field(default_factory=list)
    default: str = ""


@dataclass
class PropertyEntry:
    name: str
    qualifiers: Dict[str, str] = field(default_factory=dict)
    dependent_series: List[DataSeries] = field(default_factory=list)
    independent_series: List[DataSeries] = field(default_factory=list)
    interpolation: Optional[str] = None
    extrapolation: Optional[str] = None
    option_parameter_name: str = "Options Variable"


@dataclass
class MaterialEntry:
    name: str
    description: str = ""
    material_class: str = ""
    subclass: str = ""
    properties: List[PropertyEntry] = field(default_factory=list)


class EngineeringDataBuilder:
    def __init__(self, materials: List[MaterialEntry], version: str, versiondate: str, include_class: bool = True) -> None:
        self.materials = materials
        self.version = version
        self.versiondate = versiondate
        self.include_class = include_class
        self.param_ids: Dict[Tuple[str, str], str] = {}
        self.prop_ids: Dict[str, str] = {}
        self.param_counter = 0
        self.prop_counter = 0

    def _alloc_param_id(self, name: str, unit: str) -> str:
        key = (name.strip(), unit.strip())
        if key not in self.param_ids:
            self.param_ids[key] = f"pa{self.param_counter}"
            self.param_counter += 1
        return self.param_ids[key]

    def _alloc_prop_id(self, name: str) -> str:
        key = name.strip() or "Unnamed Property"
        if key not in self.prop_ids:
            self.prop_ids[key] = f"pr{self.prop_counter}"
            self.prop_counter += 1
        return self.prop_ids[key]

    @staticmethod
    def _append_units(parent: ET.Element, unit_text: str) -> None:
        if not unit_text.strip():
            ET.SubElement(parent, "Unitless")
            return
        units = ET.SubElement(parent, "Units")
        for token in unit_text.split():
            node = ET.SubElement(units, "Unit")
            if "^" in token:
                base, power = token.split("^", 1)
                node.set("power", power)
                ET.SubElement(node, "Name").text = base
            else:
                ET.SubElement(node, "Name").text = token

    @staticmethod
    def _to_csv(values: List[str]) -> str:
        return ",".join(v.strip() for v in values if v.strip())

    @staticmethod
    def _is_float_like(value: str) -> bool:
        try:
            float(value.strip())
            return True
        except ValueError:
            return False

    @classmethod
    def _series_format(cls, values: List[str]) -> str:
        non_empty = [v.strip() for v in values if v.strip()]
        if not non_empty:
            return "float"
        return "float" if all(cls._is_float_like(v) for v in non_empty) else "string"

    @staticmethod
    def _var_type(kind: str, count: int) -> str:
        return kind if count <= 1 else ",".join([kind] * count)

    @staticmethod
    def prettify(root: ET.Element) -> str:
        rough = ET.tostring(root, encoding="utf-8")
        return minidom.parseString(rough).toprettyxml(indent="  ")

    def build(self) -> ET.Element:
        root = ET.Element("EngineeringData", version=self.version, versiondate=self.versiondate)
        ET.SubElement(root, "Notes")
        materials_el = ET.SubElement(root, "Materials")
        doc = ET.SubElement(materials_el, "MatML_Doc")

        for mat in self.materials:
            material_el = ET.SubElement(doc, "Material")
            bulk = ET.SubElement(material_el, "BulkDetails")
            ET.SubElement(bulk, "Name").text = mat.name
            if mat.description:
                ET.SubElement(bulk, "Description").text = mat.description
            if self.include_class:
                if mat.material_class:
                    cls = ET.SubElement(bulk, "Class")
                    ET.SubElement(cls, "Name").text = mat.material_class
                if mat.subclass:
                    sub = ET.SubElement(bulk, "Subclass")
                    ET.SubElement(sub, "Name").text = mat.subclass

            for prop in mat.properties:
                pnode = ET.SubElement(bulk, "PropertyData", property=self._alloc_prop_id(prop.name))
                ET.SubElement(pnode, "Data", format="string").text = "-"

                for qk, qv in prop.qualifiers.items():
                    ET.SubElement(pnode, "Qualifier", name=qk).text = qv

                if prop.interpolation or prop.extrapolation:
                    opt_pid = self._alloc_param_id(prop.option_parameter_name, "")
                    opt = ET.SubElement(pnode, "ParameterValue", parameter=opt_pid, format="string")
                    ET.SubElement(opt, "Data").text = "Interpolation Options"
                    if prop.interpolation:
                        ET.SubElement(opt, "Qualifier", name="AlgorithmType").text = prop.interpolation
                    if prop.extrapolation:
                        ET.SubElement(opt, "Qualifier", name="ExtrapolationType").text = prop.extrapolation

                for dep in prop.dependent_series:
                    pid = self._alloc_param_id(dep.name, dep.unit)
                    fmt = self._series_format(dep.values)
                    pval = ET.SubElement(pnode, "ParameterValue", parameter=pid, format=fmt)
                    ET.SubElement(pval, "Data").text = self._to_csv(dep.values)
                    if fmt == "float":
                        ET.SubElement(pval, "Qualifier", name="Variable Type").text = self._var_type("Dependent", len(dep.values))

                for indep in prop.independent_series:
                    pid = self._alloc_param_id(indep.name, indep.unit)
                    fmt = self._series_format(indep.values)
                    pval = ET.SubElement(pnode, "ParameterValue", parameter=pid, format=fmt)
                    ET.SubElement(pval, "Data").text = self._to_csv(indep.values)
                    ET.SubElement(pval, "Qualifier", name="Variable Type").text = self._var_type("Independent", len(indep.values))
                    ET.SubElement(pval, "Qualifier", name="Field Variable").text = indep.name
                    if indep.unit:
                        ET.SubElement(pval, "Qualifier", name="Field Units").text = indep.unit
                    default_val = indep.default if indep.default else (indep.values[0] if indep.values else "")
                    if default_val:
                        ET.SubElement(pval, "Qualifier", name="Default Data").text = default_val

        metadata = ET.SubElement(doc, "Metadata")
        for (name, unit), pid in sorted(self.param_ids.items(), key=lambda x: int(x[1][2:])):
            pd = ET.SubElement(metadata, "ParameterDetails", id=pid)
            ET.SubElement(pd, "Name").text = name
            self._append_units(pd, unit)

        for pname, prid in sorted(self.prop_ids.items(), key=lambda x: int(x[1][2:])):
            pr = ET.SubElement(metadata, "PropertyDetails", id=prid)
            ET.SubElement(pr, "Unitless")
            ET.SubElement(pr, "Name").text = pname

        return root


class TextListParser:
    """Import format supporting grouped isotropic elasticity.

    Example:
    MATERIAL: Aluminum 6061-T6
    CLASS: Solids
    SUBCLASS: Wrought
    DESCRIPTION: ...
    PROPERTY: Density
    PQUAL: Field Variable Compatible=Temperature
    DEP: Density|kg m^-3|2700
    IND: Temperature|C|22|22
    ENDPROPERTY
    PROPERTY: IsotropicElasticity
    PQUAL: Behavior=Isotropic
    PQUAL: Matrix Type=Stiffness
    PQUAL: Format=IEEE
    DEP: Young's Modulus|Pa|6.89e10
    DEP: Poisson's Ratio||0.33
    IND: Temperature|C|22|22
    ENDPROPERTY
    ENDMATERIAL
    """
    @dataclass
    class PropertyTemplate:
        qualifiers: Dict[str, str] = field(default_factory=dict)
        dependent_series: List[DataSeries] = field(default_factory=list)
        independent_series: List[DataSeries] = field(default_factory=list)
        interpolation: Optional[str] = None
        extrapolation: Optional[str] = None
        option_parameter_name: str = "Options Variable"

    def __init__(self, template_zip: str = "AllXmls.zip") -> None:
        self.templates: Dict[str, TextListParser.PropertyTemplate] = self._load_templates(Path(template_zip))

    @staticmethod
    def _read_template_from_propertydata(
        pnode: ET.Element, prop_name: str, param_map: Dict[str, Tuple[str, str]]
    ) -> "TextListParser.PropertyTemplate":
        qualifiers: Dict[str, str] = {}
        dependent_series: List[DataSeries] = []
        independent_series: List[DataSeries] = []
        interpolation: Optional[str] = None
        extrapolation: Optional[str] = None
        option_parameter_name = "Options Variable"

        for q in pnode.findall("Qualifier"):
            name = q.attrib.get("name", "").strip()
            value = (q.text or "").strip()
            if name:
                qualifiers[name] = value

        for pval in pnode.findall("ParameterValue"):
            pid = pval.attrib.get("parameter", "")
            series_name, series_unit = param_map.get(pid, (pid or "Unknown", ""))
            csv = (pval.findtext("Data") or "").strip()
            values = [v.strip() for v in csv.split(",") if v.strip()]
            qmap: Dict[str, str] = {}
            for q in pval.findall("Qualifier"):
                qn = q.attrib.get("name", "").strip()
                qv = (q.text or "").strip()
                if qn:
                    qmap[qn] = qv

            vtype = qmap.get("Variable Type", "").lower()
            if "independent" in vtype:
                independent_series.append(
                    DataSeries(
                        name=qmap.get("Field Variable", series_name),
                        unit=qmap.get("Field Units", series_unit),
                        values=values,
                        default=qmap.get("Default Data", ""),
                    )
                )
            elif "dependent" in vtype:
                dependent_series.append(DataSeries(name=series_name, unit=series_unit, values=values, default=""))
            elif "Interpolation Options" in csv:
                option_parameter_name = series_name or "Options Variable"
                interpolation = qmap.get("AlgorithmType")
                extrapolation = qmap.get("ExtrapolationType")
            else:
                dependent_series.append(DataSeries(name=series_name, unit=series_unit, values=values, default=""))

        return TextListParser.PropertyTemplate(
            qualifiers=qualifiers,
            dependent_series=dependent_series,
            independent_series=independent_series,
            interpolation=interpolation,
            extrapolation=extrapolation,
            option_parameter_name=option_parameter_name,
        )

    def _load_templates(self, zip_path: Path) -> Dict[str, "TextListParser.PropertyTemplate"]:
        templates: Dict[str, TextListParser.PropertyTemplate] = {}
        if not zip_path.exists():
            return templates

        try:
            with zipfile.ZipFile(zip_path) as zf:
                for member in zf.namelist():
                    if not member.lower().endswith(".xml"):
                        continue
                    try:
                        root = ET.fromstring(zf.read(member))
                    except Exception:
                        continue

                    for matml in root.findall(".//MatML_Doc"):
                        metadata = matml.find("Metadata")
                        if metadata is None:
                            continue
                        prop_map: Dict[str, str] = {}
                        param_map: Dict[str, Tuple[str, str]] = {}

                        for pd in metadata.findall("PropertyDetails"):
                            pid = pd.attrib.get("id", "").strip()
                            name = (pd.findtext("Name") or "").strip()
                            if pid and name:
                                prop_map[pid] = name

                        for pa in metadata.findall("ParameterDetails"):
                            pid = pa.attrib.get("id", "").strip()
                            name = (pa.findtext("Name") or "").strip()
                            unit_tokens: List[str] = []
                            units_node = pa.find("Units")
                            if units_node is not None:
                                for u in units_node.findall("Unit"):
                                    uname = (u.findtext("Name") or "").strip()
                                    if not uname:
                                        continue
                                    power = u.attrib.get("power")
                                    unit_tokens.append(f"{uname}^{power}" if power is not None else uname)
                            unit = " ".join(unit_tokens)
                            if pid and name:
                                param_map[pid] = (name, unit)

                        for pnode in matml.findall(".//PropertyData"):
                            prop_id = pnode.attrib.get("property", "").strip()
                            prop_name = prop_map.get(prop_id, "").strip()
                            if not prop_name or prop_name in templates:
                                continue
                            templates[prop_name] = self._read_template_from_propertydata(pnode, prop_name, param_map)
        except Exception:
            return templates

        return templates

    def _apply_templates(self, material: MaterialEntry, mode: str) -> None:
        if mode.upper() in {"NONE", "OFF", "FALSE", "NO"}:
            return
        existing = {p.name.casefold() for p in material.properties}
        for prop_name, template in self.templates.items():
            if prop_name.casefold() in existing:
                continue
            material.properties.append(
                PropertyEntry(
                    name=prop_name,
                    qualifiers=dict(template.qualifiers),
                    dependent_series=[DataSeries(name=s.name, unit=s.unit, values=list(s.values), default=s.default) for s in template.dependent_series],
                    independent_series=[DataSeries(name=s.name, unit=s.unit, values=list(s.values), default=s.default) for s in template.independent_series],
                    interpolation=template.interpolation,
                    extrapolation=template.extrapolation,
                    option_parameter_name=template.option_parameter_name,
                )
            )

    def parse(self, content: str) -> List[MaterialEntry]:
        mats: List[MaterialEntry] = []
        m: Optional[MaterialEntry] = None
        p: Optional[PropertyEntry] = None
        auto_mode = "ALL"

        for raw in content.splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line == "ENDPROPERTY":
                if m and p:
                    m.properties.append(p)
                p = None
                continue
            if line == "ENDMATERIAL":
                if m:
                    self._apply_templates(m, auto_mode)
                    mats.append(m)
                m = None
                auto_mode = "ALL"
                continue
            if ":" not in line:
                continue
            key, val = [x.strip() for x in line.split(":", 1)]
            key = key.upper()

            if key == "MATERIAL":
                m = MaterialEntry(name=val)
            elif key == "DESCRIPTION" and m:
                m.description = val
            elif key == "CLASS" and m:
                m.material_class = val
            elif key == "SUBCLASS" and m:
                m.subclass = val
            elif key == "AUTO_PROPERTIES" and m:
                auto_mode = val or "ALL"
            elif key == "PROPERTY":
                p = PropertyEntry(name=val)
            elif key == "PQUAL" and p and "=" in val:
                qk, qv = [x.strip() for x in val.split("=", 1)]
                p.qualifiers[qk] = qv
            elif key == "OPTION_NAME" and p:
                p.option_parameter_name = val or "Options Variable"
            elif key == "INTERPOLATION" and p:
                p.interpolation = val
            elif key == "EXTRAPOLATION" and p:
                p.extrapolation = val
            elif key in {"DEP", "IND"} and p:
                parts = [x.strip() for x in val.split("|")]
                if len(parts) not in (3, 4):
                    raise ValueError(f"Expected name|unit|values or name|unit|values|default, got: {val}")
                name, unit, values = parts[0], parts[1], parts[2]
                default = parts[3] if len(parts) == 4 else ""
                series = DataSeries(name=name, unit=unit, values=[v.strip() for v in values.split(",")], default=default)
                if key == "DEP":
                    p.dependent_series.append(series)
                else:
                    p.independent_series.append(series)

        if p and m:
            m.properties.append(p)
        if m:
            self._apply_templates(m, auto_mode)
            mats.append(m)
        return mats


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("EngineeringData XML Builder - Mechanical Compatible")
        self.geometry("1200x800")

        self.materials: List[MaterialEntry] = []
        self.pending_properties: List[PropertyEntry] = []

        self._build_ui()

    def _build_ui(self) -> None:
        # Header
        hdr = ttk.LabelFrame(self, text="EngineeringData Header")
        hdr.pack(fill="x", padx=10, pady=6)
        self.version = tk.StringVar(value="25.2.0.233")
        self.versiondate = tk.StringVar(value="6/12/2025 11:41:00 AM")
        ttk.Label(hdr, text="version").grid(row=0, column=0, sticky="w")
        ttk.Entry(hdr, textvariable=self.version, width=24).grid(row=0, column=1, padx=6)
        ttk.Label(hdr, text="versiondate").grid(row=0, column=2, sticky="w")
        ttk.Entry(hdr, textvariable=self.versiondate, width=30).grid(row=0, column=3, padx=6)

        self.include_class = tk.BooleanVar(value=True)
        ttk.Checkbutton(hdr, text="Include <Class> and <Subclass> (may break Mechanical)", variable=self.include_class).grid(row=0, column=4, padx=20)

        # Material entry
        mat = ttk.LabelFrame(self, text="Material")
        mat.pack(fill="x", padx=10, pady=6)
        self.mat_name = tk.StringVar()
        self.mat_class = tk.StringVar()
        self.mat_subclass = tk.StringVar()
        ttk.Label(mat, text="Name *").grid(row=0, column=0, sticky="w")
        ttk.Entry(mat, textvariable=self.mat_name, width=42).grid(row=0, column=1, sticky="we", padx=4)
        ttk.Label(mat, text="Class").grid(row=0, column=2, sticky="w")
        ttk.Entry(mat, textvariable=self.mat_class, width=30).grid(row=0, column=3, sticky="we", padx=4)
        ttk.Label(mat, text="Subclass").grid(row=1, column=0, sticky="w")
        ttk.Entry(mat, textvariable=self.mat_subclass, width=42).grid(row=1, column=1, sticky="we", padx=4)
        ttk.Label(mat, text="Description").grid(row=2, column=0, sticky="nw")
        self.mat_description = tk.Text(mat, width=90, height=3)
        self.mat_description.grid(row=2, column=1, columnspan=3, sticky="we", padx=4, pady=3)

        # Property
        prop = ttk.LabelFrame(self, text="Property (supports multiple dependent/independent series)")
        prop.pack(fill="x", padx=10, pady=6)
        self.prop_name = tk.StringVar()
        self.option_name = tk.StringVar(value="Options Variable")
        self.interp = tk.StringVar()
        self.extrap = tk.StringVar()

        ttk.Label(prop, text="Property Name").grid(row=0, column=0, sticky="w")
        ttk.Entry(prop, textvariable=self.prop_name, width=45).grid(row=0, column=1, sticky="we", padx=4)

        ttk.Label(prop, text="Option Param Name").grid(row=0, column=2, sticky="w")
        ttk.Entry(prop, textvariable=self.option_name, width=28).grid(row=0, column=3, sticky="we", padx=4)

        ttk.Label(prop, text="Interpolation").grid(row=1, column=0, sticky="w")
        ttk.Entry(prop, textvariable=self.interp, width=45).grid(row=1, column=1, sticky="we", padx=4)
        ttk.Label(prop, text="Extrapolation").grid(row=1, column=2, sticky="w")
        ttk.Entry(prop, textvariable=self.extrap, width=28).grid(row=1, column=3, sticky="we", padx=4)

        ttk.Label(prop, text="Qualifiers (key=value per line)").grid(row=2, column=0, sticky="nw")
        self.prop_qualifiers = tk.Text(prop, width=55, height=4)
        self.prop_qualifiers.grid(row=2, column=1, sticky="we", padx=4)

        ttk.Label(prop, text="Dependent series (name|unit|v1,v2)").grid(row=2, column=2, sticky="nw")
        self.dep_series_text = tk.Text(prop, width=55, height=4)
        self.dep_series_text.grid(row=2, column=3, sticky="we", padx=4)

        ttk.Label(prop, text="Independent series (name|unit|v1,v2|default)").grid(row=3, column=0, sticky="nw")
        self.ind_series_text = tk.Text(prop, width=110, height=4)
        self.ind_series_text.grid(row=3, column=1, columnspan=3, sticky="we", padx=4, pady=4)

        btn_frame = ttk.Frame(prop)
        btn_frame.grid(row=4, column=0, columnspan=4, pady=4)
        ttk.Button(btn_frame, text="Add Property", command=self.add_property).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Add Isotropic Elasticity (Mechanical)", command=self.add_isotropic_elasticity).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Clear Property Inputs", command=self.clear_property_inputs).pack(side="left", padx=4)

        # Queue
        list_box = ttk.LabelFrame(self, text="Properties & Materials Queue")
        list_box.pack(fill="both", expand=True, padx=10, pady=6)
        self.queue = tk.Listbox(list_box, height=12)
        self.queue.pack(fill="both", expand=True, padx=4, pady=4)

        actions = ttk.Frame(self)
        actions.pack(fill="x", padx=10, pady=8)
        ttk.Button(actions, text="Save Material", command=self.save_material).pack(side="left", padx=4)
        ttk.Button(actions, text="Import TXT", command=self.import_txt).pack(side="left", padx=4)
        ttk.Button(actions, text="Export XML", command=self.export_xml).pack(side="right", padx=4)

    def add_isotropic_elasticity(self) -> None:
        """Pre-fill a property that Mechanical will recognise as linear elastic."""
        self.prop_name.set("IsotropicElasticity")
        self.prop_qualifiers.delete("1.0", "end")
        self.prop_qualifiers.insert("1.0", "Behavior=Isotropic\nMatrix Type=Stiffness\nFormat=IEEE")
        self.dep_series_text.delete("1.0", "end")
        self.dep_series_text.insert("1.0", "Young's Modulus|Pa|\nPoisson's Ratio||")
        self.ind_series_text.delete("1.0", "end")
        self.ind_series_text.insert("1.0", "Temperature|C|22|22")

    def _parse_series_block(self, block: str) -> List[DataSeries]:
        result = []
        for line in block.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = [x.strip() for x in line.split("|")]
            if len(parts) < 3 or len(parts) > 4:
                raise ValueError(f"Invalid series: {line}")
            values = [v.strip() for v in parts[2].split(",") if v.strip()]
            default = parts[3] if len(parts) == 4 else ""
            result.append(DataSeries(name=parts[0], unit=parts[1], values=values, default=default))
        return result

    def _parse_qualifiers(self, block: str) -> Dict[str, str]:
        data = {}
        for line in block.splitlines():
            line = line.strip()
            if not line:
                continue
            if "=" not in line:
                raise ValueError(f"Invalid qualifier: {line}")
            k, v = [x.strip() for x in line.split("=", 1)]
            data[k] = v
        return data

    def clear_property_inputs(self) -> None:
        self.prop_name.set("")
        self.option_name.set("Options Variable")
        self.interp.set("")
        self.extrap.set("")
        self.prop_qualifiers.delete("1.0", "end")
        self.dep_series_text.delete("1.0", "end")
        self.ind_series_text.delete("1.0", "end")

    def add_property(self) -> None:
        try:
            name = self.prop_name.get().strip()
            if not name:
                raise ValueError("Property name required")
            qualifiers = self._parse_qualifiers(self.prop_qualifiers.get("1.0", "end"))
            deps = self._parse_series_block(self.dep_series_text.get("1.0", "end"))
            inds = self._parse_series_block(self.ind_series_text.get("1.0", "end"))

            if deps:
                ref = len(deps[0].values)
                for d in deps[1:]:
                    if len(d.values) != ref:
                        raise ValueError("All dependent series must have same length")
                for i in inds:
                    if i.values and len(i.values) != ref:
                        raise ValueError("Independent series length must match dependent length")

            prop = PropertyEntry(
                name=name, qualifiers=qualifiers, dependent_series=deps, independent_series=inds,
                interpolation=self.interp.get().strip() or None,
                extrapolation=self.extrap.get().strip() or None,
                option_parameter_name=self.option_name.get().strip() or "Options Variable"
            )
            self.pending_properties.append(prop)
            self.queue.insert("end", f"Property: {prop.name} (deps={len(deps)}, indeps={len(inds)})")
            self.clear_property_inputs()
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def save_material(self) -> None:
        try:
            name = self.mat_name.get().strip()
            if not name:
                raise ValueError("Material name required")
            mat = MaterialEntry(
                name=name,
                description=self.mat_description.get("1.0", "end").strip(),
                material_class=self.mat_class.get().strip(),
                subclass=self.mat_subclass.get().strip(),
                properties=list(self.pending_properties)
            )
            self.materials.append(mat)
            self.pending_properties.clear()
            self.queue.insert("end", f"Material saved: {mat.name} ({len(mat.properties)} properties)")
            self.mat_name.set("")
            self.mat_class.set("")
            self.mat_subclass.set("")
            self.mat_description.delete("1.0", "end")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def import_txt(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("Text", "*.txt")])
        if not path:
            return
        try:
            content = Path(path).read_text(encoding="utf-8")
            parsed = TextListParser().parse(content)
            self.materials.extend(parsed)
            self.queue.insert("end", f"Imported {len(parsed)} materials from {Path(path).name}")
        except Exception as e:
            messagebox.showerror("Import failed", str(e))

    def export_xml(self) -> None:
        if self.pending_properties:
            if messagebox.askyesno("Pending properties", "Save current material first?"):
                self.save_material()
        if not self.materials:
            messagebox.showerror("Nothing to export", "No materials")
            return

        # Check for duplicate names
        seen = {}
        for m in self.materials:
            key = m.name.casefold()
            seen[key] = seen.get(key, 0) + 1
        dupes = [m.name for m in self.materials if seen[m.name.casefold()] > 1]
        if dupes:
            messagebox.showerror("Duplicate names", "Fix duplicates:\n" + "\n".join(set(dupes)))
            return

        # Warning if using separate Young/ Poisson properties
        for m in self.materials:
            has_young = any("young" in p.name.casefold() and "modulus" in p.name.casefold() for p in m.properties)
            has_poisson = any("poisson" in p.name.casefold() for p in m.properties)
            if has_young and has_poisson and not any(p.name == "IsotropicElasticity" for p in m.properties):
                if not messagebox.askyesno("Separate properties detected", f"Material '{m.name}' uses separate Young's Modulus and Poisson Ratio properties.\nMechanical will NOT recognise them.\nUse 'IsotropicElasticity' instead.\n\nContinue export anyway?"):
                    return

        out = filedialog.asksaveasfilename(defaultextension=".xml", filetypes=[("XML", "*.xml")])
        if not out:
            return

        builder = EngineeringDataBuilder(self.materials, self.version.get().strip(), self.versiondate.get().strip(),
                                         include_class=self.include_class.get())
        root = builder.build()
        xml = builder.prettify(root)
        Path(out).write_text(xml, encoding="utf-8")
        messagebox.showinfo("Success", f"Saved to {out}\n\nIf materials still don't appear in Mechanical, uncheck 'Include <Class>' and ensure you used 'IsotropicElasticity'.")

def main():
    App().mainloop()

if __name__ == "__main__":
    main()
