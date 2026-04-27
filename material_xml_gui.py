#!/usr/bin/env python3
"""GUI tool to build EngineeringData XML (Ansys Granta style)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import xml.etree.ElementTree as ET
from xml.dom import minidom


@dataclass
class DataSeries:
    name: str
    unit: str = ""
    values: List[str] = field(default_factory=list)


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
    """Builds XML with root EngineeringData > Notes + Materials > MatML_Doc."""

    def __init__(self, materials: List[MaterialEntry], version: str, versiondate: str) -> None:
        self.materials = materials
        self.version = version
        self.versiondate = versiondate
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
        for token in [t.strip() for t in unit_text.split() if t.strip()]:
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
    def _var_type(kind: str, count: int) -> str:
        if count <= 0:
            return kind
        return ",".join([kind] * count)

    @staticmethod
    def prettify(root: ET.Element) -> str:
        rough = ET.tostring(root, encoding="utf-8")
        return minidom.parseString(rough).toprettyxml(indent="  ")

    def build(self) -> ET.Element:
        root = ET.Element("EngineeringData", version=self.version, versiondate=self.versiondate)
        ET.SubElement(root, "Notes")
        materials_el = ET.SubElement(root, "Materials")
        doc = ET.SubElement(materials_el, "MatML_Doc")

        # pre-register option parameter if needed
        for mat in self.materials:
            for prop in mat.properties:
                if prop.interpolation or prop.extrapolation:
                    self._alloc_param_id(prop.option_parameter_name, "")

        for mat in self.materials:
            material_el = ET.SubElement(doc, "Material")
            bulk = ET.SubElement(material_el, "BulkDetails")
            ET.SubElement(bulk, "Name").text = mat.name
            if mat.description:
                ET.SubElement(bulk, "Description").text = mat.description
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
                    q = ET.SubElement(pnode, "Qualifier", name=qk)
                    q.text = qv

                if prop.interpolation or prop.extrapolation:
                    opt_pid = self._alloc_param_id(prop.option_parameter_name, "")
                    opt = ET.SubElement(pnode, "ParameterValue", parameter=opt_pid, format="string")
                    ET.SubElement(opt, "Data").text = "Interpolation Options"
                    if prop.interpolation:
                        q = ET.SubElement(opt, "Qualifier", name="AlgorithmType")
                        q.text = prop.interpolation
                    if prop.extrapolation:
                        q = ET.SubElement(opt, "Qualifier", name="ExtrapolationType")
                        q.text = prop.extrapolation

                for dep in prop.dependent_series:
                    pid = self._alloc_param_id(dep.name, dep.unit)
                    pval = ET.SubElement(pnode, "ParameterValue", parameter=pid, format="float")
                    ET.SubElement(pval, "Data").text = self._to_csv(dep.values)
                    q = ET.SubElement(pval, "Qualifier", name="Variable Type")
                    q.text = self._var_type("Dependent", len(dep.values))

                for indep in prop.independent_series:
                    pid = self._alloc_param_id(indep.name, indep.unit)
                    pval = ET.SubElement(pnode, "ParameterValue", parameter=pid, format="float")
                    ET.SubElement(pval, "Data").text = self._to_csv(indep.values)
                    q = ET.SubElement(pval, "Qualifier", name="Variable Type")
                    q.text = self._var_type("Independent", len(indep.values))
                    qf = ET.SubElement(pval, "Qualifier", name="Field Variable")
                    qf.text = indep.name
                    if indep.unit:
                        qu = ET.SubElement(pval, "Qualifier", name="Field Units")
                        qu.text = indep.unit

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
    """Simple import format for the GUI.

    MATERIAL: deneme
    DESCRIPTION: optional
    CLASS: Hyperelastic
    SUBCLASS: optional
    PROPERTY: Density
    PQUAL: Field Variable Compatible=Temperature
    OPTION_NAME: Options Variable
    INTERPOLATION: Linear Multivariate
    EXTRAPOLATION: Projection to the Bounding Box
    DEP: Density|kg m^-3|12
    IND: Temperature|C|22
    ENDPROPERTY
    ENDMATERIAL
    """

    def parse(self, content: str) -> List[MaterialEntry]:
        mats: List[MaterialEntry] = []
        m: Optional[MaterialEntry] = None
        p: Optional[PropertyEntry] = None

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
                    mats.append(m)
                m = None
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
                name, unit, values = self._parse_triplet(val)
                series = DataSeries(name=name, unit=unit, values=self._split_values(values))
                if key == "DEP":
                    p.dependent_series.append(series)
                else:
                    p.independent_series.append(series)

        if p and m:
            m.properties.append(p)
        if m:
            mats.append(m)

        return mats

    @staticmethod
    def _split_values(value: str) -> List[str]:
        return [v.strip() for v in value.split(",") if v.strip()]

    @staticmethod
    def _parse_triplet(value: str) -> Tuple[str, str, str]:
        parts = [x.strip() for x in value.split("|")]
        if len(parts) != 3:
            raise ValueError(f"Expected name|unit|values, got: {value}")
        return parts[0], parts[1], parts[2]


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("EngineeringData XML Builder")
        self.geometry("1150x760")

        self.materials: List[MaterialEntry] = []
        self.pending_properties: List[PropertyEntry] = []

        self._build_ui()

    def _build_ui(self) -> None:
        # file/header
        hdr = ttk.LabelFrame(self, text="EngineeringData Header")
        hdr.pack(fill="x", padx=10, pady=6)
        self.version = tk.StringVar(value="25.2.0.233")
        self.versiondate = tk.StringVar(value="6/12/2025 11:41:00 AM")
        ttk.Label(hdr, text="version").grid(row=0, column=0, sticky="w")
        ttk.Entry(hdr, textvariable=self.version, width=24).grid(row=0, column=1, padx=6)
        ttk.Label(hdr, text="versiondate").grid(row=0, column=2, sticky="w")
        ttk.Entry(hdr, textvariable=self.versiondate, width=30).grid(row=0, column=3, padx=6)

        mat = ttk.LabelFrame(self, text="Material")
        mat.pack(fill="x", padx=10, pady=6)
        self.mat_name = tk.StringVar()
        self.mat_class = tk.StringVar()
        self.mat_subclass = tk.StringVar()
        ttk.Label(mat, text="Name").grid(row=0, column=0, sticky="w")
        ttk.Entry(mat, textvariable=self.mat_name, width=42).grid(row=0, column=1, sticky="we", padx=4)
        ttk.Label(mat, text="Class").grid(row=0, column=2, sticky="w")
        ttk.Entry(mat, textvariable=self.mat_class, width=30).grid(row=0, column=3, sticky="we", padx=4)
        ttk.Label(mat, text="Subclass").grid(row=1, column=0, sticky="w")
        ttk.Entry(mat, textvariable=self.mat_subclass, width=42).grid(row=1, column=1, sticky="we", padx=4)
        ttk.Label(mat, text="Description").grid(row=2, column=0, sticky="nw")
        self.mat_description = tk.Text(mat, width=90, height=3)
        self.mat_description.grid(row=2, column=1, columnspan=3, sticky="we", padx=4, pady=3)

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

        ttk.Label(prop, text="Property qualifiers (one per line: key=value)").grid(row=2, column=0, sticky="nw")
        self.prop_qualifiers = tk.Text(prop, width=55, height=4)
        self.prop_qualifiers.grid(row=2, column=1, sticky="we", padx=4)

        ttk.Label(prop, text="Dependent series (one per line: name|unit|v1,v2)").grid(row=2, column=2, sticky="nw")
        self.dep_series_text = tk.Text(prop, width=55, height=4)
        self.dep_series_text.grid(row=2, column=3, sticky="we", padx=4)

        ttk.Label(prop, text="Independent series (one per line: name|unit|v1,v2)").grid(row=3, column=0, sticky="nw")
        self.ind_series_text = tk.Text(prop, width=110, height=4)
        self.ind_series_text.grid(row=3, column=1, columnspan=3, sticky="we", padx=4, pady=4)

        ttk.Button(prop, text="Add Property", command=self.add_property).grid(row=4, column=0, pady=4)
        ttk.Button(prop, text="Clear Property Inputs", command=self.clear_property_inputs).grid(row=4, column=1, sticky="w")

        list_box = ttk.LabelFrame(self, text="Queue")
        list_box.pack(fill="both", expand=True, padx=10, pady=6)
        self.queue = tk.Listbox(list_box, height=12)
        self.queue.pack(fill="both", expand=True, padx=4, pady=4)

        actions = ttk.Frame(self)
        actions.pack(fill="x", padx=10, pady=8)
        ttk.Button(actions, text="Save Material", command=self.save_material).pack(side="left", padx=4)
        ttk.Button(actions, text="Import TXT", command=self.import_txt).pack(side="left", padx=4)
        ttk.Button(actions, text="Export XML", command=self.export_xml).pack(side="right", padx=4)

    @staticmethod
    def _parse_series_block(block: str) -> List[DataSeries]:
        result: List[DataSeries] = []
        for line in block.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = [x.strip() for x in line.split("|")]
            if len(parts) != 3:
                raise ValueError(f"Invalid series line: {line}")
            values = [v.strip() for v in parts[2].split(",") if v.strip()]
            result.append(DataSeries(name=parts[0], unit=parts[1], values=values))
        return result

    @staticmethod
    def _parse_qualifiers(block: str) -> Dict[str, str]:
        data: Dict[str, str] = {}
        for line in block.splitlines():
            line = line.strip()
            if not line:
                continue
            if "=" not in line:
                raise ValueError(f"Invalid qualifier line: {line}")
            k, v = [x.strip() for x in line.split("=", 1)]
            data[k] = v
        return data

    @staticmethod
    def _material_issues(material: MaterialEntry) -> List[str]:
        observed = set()
        for prop in material.properties:
            observed.add(prop.name.casefold())
            for dep in prop.dependent_series:
                observed.add(dep.name.casefold())

        issues: List[str] = []
        if not any("density" in n for n in observed):
            issues.append("missing Density")
        if not any("young" in n and "modulus" in n for n in observed):
            issues.append("missing Young's Modulus")
        if not any("poisson" in n and "ratio" in n for n in observed):
            issues.append("missing Poisson's Ratio")
        return issues

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
                raise ValueError("Property name is required")

            qualifiers = self._parse_qualifiers(self.prop_qualifiers.get("1.0", "end"))
            deps = self._parse_series_block(self.dep_series_text.get("1.0", "end"))
            inds = self._parse_series_block(self.ind_series_text.get("1.0", "end"))

            # validate lengths when available
            if deps:
                ref_count = len(deps[0].values)
                for d in deps[1:]:
                    if len(d.values) != ref_count:
                        raise ValueError("All dependent series must have the same number of values")
                for i in inds:
                    if len(i.values) not in (0, ref_count):
                        raise ValueError("Independent series count must match dependent series count")

            p = PropertyEntry(
                name=name,
                qualifiers=qualifiers,
                dependent_series=deps,
                independent_series=inds,
                interpolation=self.interp.get().strip() or None,
                extrapolation=self.extrap.get().strip() or None,
                option_parameter_name=self.option_name.get().strip() or "Options Variable",
            )
            self.pending_properties.append(p)
            self.queue.insert("end", f"Property queued: {p.name}")
            self.clear_property_inputs()
        except Exception as exc:
            messagebox.showerror("Invalid property", str(exc))

    def save_material(self) -> None:
        try:
            name = self.mat_name.get().strip()
            if not name:
                raise ValueError("Material name is required")
            m = MaterialEntry(
                name=name,
                description=self.mat_description.get("1.0", "end").strip(),
                material_class=self.mat_class.get().strip(),
                subclass=self.mat_subclass.get().strip(),
                properties=list(self.pending_properties),
            )
            self.materials.append(m)
            self.pending_properties.clear()
            self.queue.insert("end", f"Material saved: {m.name} ({len(m.properties)} properties)")

            self.mat_name.set("")
            self.mat_class.set("")
            self.mat_subclass.set("")
            self.mat_description.delete("1.0", "end")
        except Exception as exc:
            messagebox.showerror("Cannot save material", str(exc))

    def import_txt(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("Text", "*.txt"), ("All", "*.*")])
        if not path:
            return
        try:
            content = Path(path).read_text(encoding="utf-8")
            parsed = TextListParser().parse(content)
            self.materials.extend(parsed)
            self.queue.insert("end", f"Imported {len(parsed)} materials from {Path(path).name}")
        except Exception as exc:
            messagebox.showerror("Import failed", str(exc))

    def export_xml(self) -> None:
        if self.pending_properties:
            if messagebox.askyesno("Pending properties", "Save current material first?"):
                self.save_material()

        if not self.materials:
            messagebox.showerror("Nothing to export", "No saved materials")
            return

        # Duplicate-name guard: Mechanical often exposes only one when duplicates exist.
        seen: Dict[str, int] = {}
        duplicates: List[str] = []
        for m in self.materials:
            key = m.name.casefold()
            seen[key] = seen.get(key, 0) + 1
        for m in self.materials:
            if seen[m.name.casefold()] > 1 and m.name not in duplicates:
                duplicates.append(m.name)
        if duplicates:
            messagebox.showerror(
                "Duplicate material names",
                "Duplicate names found (fix before export):\\n- " + "\\n- ".join(duplicates),
            )
            return

        # Usability warning: materials missing basic linear-elastic trio are commonly hidden in Mechanical.
        issue_lines: List[str] = []
        for m in self.materials:
            issues = self._material_issues(m)
            if issues:
                issue_lines.append(f"{m.name}: {', '.join(issues)}")
        if issue_lines:
            proceed = messagebox.askyesno(
                "Potentially unusable materials",
                "Some materials may not appear in Mechanical:\n\n- " + "\n- ".join(issue_lines) + "\n\nExport anyway?",
            )
            if not proceed:
                return

        out = filedialog.asksaveasfilename(defaultextension=".xml", filetypes=[("XML", "*.xml")])
        if not out:
            return

        builder = EngineeringDataBuilder(self.materials, self.version.get().strip(), self.versiondate.get().strip())
        root = builder.build()
        xml = EngineeringDataBuilder.prettify(root)
        Path(out).write_text(xml, encoding="utf-8")
        messagebox.showinfo("Done", f"Saved: {out}")


def main() -> None:
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
