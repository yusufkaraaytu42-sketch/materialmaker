#!/usr/bin/env python3
"""GUI tool to build EngineeringData XML from manual input or a text file."""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from dataclasses import dataclass, field
from pathlib import Path
import xml.etree.ElementTree as ET
from xml.dom import minidom
from typing import Dict, List, Optional


@dataclass
class IndependentSeries:
    name: str
    unit: str = ""
    values: List[str] = field(default_factory=list)


@dataclass
class PropertyEntry:
    name: str
    dependent_name: str
    dependent_unit: str
    dependent_values: List[str]
    independent_vars: List[IndependentSeries] = field(default_factory=list)
    qualifiers: Dict[str, str] = field(default_factory=dict)
    interpolation: Optional[str] = None
    extrapolation: Optional[str] = None


@dataclass
class MaterialEntry:
    name: str
    description: str = ""
    material_class: str = ""
    subclass: str = ""
    properties: List[PropertyEntry] = field(default_factory=list)


class EngineeringDataBuilder:
    def __init__(self, materials: List[MaterialEntry]) -> None:
        self.materials = materials
        self.param_ids: Dict[tuple, str] = {}
        self.prop_ids: Dict[str, str] = {}
        self.pa_count = 1
        self.pr_count = 1

    def _param_id(self, name: str, unit: str) -> str:
        key = (name.strip(), unit.strip())
        if key not in self.param_ids:
            self.param_ids[key] = f"pa{self.pa_count}"
            self.pa_count += 1
        return self.param_ids[key]

    def _prop_id(self, name: str) -> str:
        if name not in self.prop_ids:
            self.prop_ids[name] = f"pr{self.pr_count}"
            self.pr_count += 1
        return self.prop_ids[name]

    @staticmethod
    def _append_units(parent: ET.Element, unit_text: str) -> None:
        if not unit_text.strip():
            return
        units = ET.SubElement(parent, "Units")
        for token in unit_text.split():
            token = token.strip()
            if not token:
                continue
            power = None
            name = token
            if "^" in token:
                base, pow_text = token.split("^", 1)
                name = base
                power = pow_text
            u = ET.SubElement(units, "Unit")
            if power is not None:
                u.set("power", power)
            ET.SubElement(u, "Name").text = name

    @staticmethod
    def _prettify(elem: ET.Element) -> str:
        rough = ET.tostring(elem, encoding="utf-8")
        parsed = minidom.parseString(rough)
        return parsed.toprettyxml(indent="  ")

    def build(self) -> ET.Element:
        root = ET.Element("EngineeringData", version="1.0", versiondate="2026-04-27")
        item = ET.SubElement(root, "item")
        doc = ET.SubElement(item, "MatML_Doc")

        for material in self.materials:
            m = ET.SubElement(doc, "Material")
            bulk = ET.SubElement(m, "BulkDetails")
            ET.SubElement(bulk, "Name").text = material.name
            ET.SubElement(bulk, "Description").text = material.description

            cls = ET.SubElement(bulk, "Class")
            ET.SubElement(cls, "Name").text = material.material_class

            subcls = ET.SubElement(bulk, "Subclass")
            ET.SubElement(subcls, "Name").text = material.subclass

            for prop in material.properties:
                prop_id = self._prop_id(prop.name)
                pnode = ET.SubElement(bulk, "PropertyData", property=prop_id)
                ET.SubElement(pnode, "Data", format="string").text = "-"

                for q_name, q_val in prop.qualifiers.items():
                    q = ET.SubElement(pnode, "Qualifier", name=q_name)
                    q.text = q_val

                if prop.interpolation or prop.extrapolation:
                    opt = ET.SubElement(pnode, "ParameterValue", parameter="pa6", format="string")
                    ET.SubElement(opt, "Data").text = "Interpolation Options"
                    if prop.interpolation:
                        q = ET.SubElement(opt, "Qualifier", name="AlgorithmType")
                        q.text = prop.interpolation
                    if prop.extrapolation:
                        q = ET.SubElement(opt, "Qualifier", name="ExtrapolationType")
                        q.text = prop.extrapolation

                dep_param = self._param_id(prop.dependent_name, prop.dependent_unit)
                dep = ET.SubElement(pnode, "ParameterValue", parameter=dep_param)
                ET.SubElement(dep, "Data").text = ",".join(prop.dependent_values)
                dep_q = ET.SubElement(dep, "Qualifier", name="Variable Type")
                dep_q.text = ",".join(["Dependent"] * len(prop.dependent_values))

                for indep in prop.independent_vars:
                    ind_param = self._param_id(indep.name, indep.unit)
                    ip = ET.SubElement(pnode, "ParameterValue", parameter=ind_param)
                    ET.SubElement(ip, "Data").text = ",".join(indep.values)
                    q_var = ET.SubElement(ip, "Qualifier", name="Variable Type")
                    q_var.text = ",".join(["Independent"] * len(indep.values))
                    q_field = ET.SubElement(ip, "Qualifier", name="Field Variable")
                    q_field.text = indep.name
                    if indep.unit:
                        q_units = ET.SubElement(ip, "Qualifier", name="Field Units")
                        q_units.text = indep.unit

        metadata = ET.SubElement(doc, "Metadata")

        pa6 = ET.SubElement(metadata, "ParameterDetails", id="pa6")
        ET.SubElement(pa6, "Name").text = "Interpolation Options"

        for (pname, punit), pid in sorted(self.param_ids.items(), key=lambda x: int(x[1][2:])):
            pd = ET.SubElement(metadata, "ParameterDetails", id=pid)
            ET.SubElement(pd, "Name").text = pname
            self._append_units(pd, punit)

        for pname, prid in sorted(self.prop_ids.items(), key=lambda x: int(x[1][2:])):
            prop = ET.SubElement(metadata, "PropertyDetails", id=prid)
            ET.SubElement(prop, "Name").text = pname

        return root


class TextListParser:
    """Parses a simple list format from .txt into materials.

    Format:
      MATERIAL: Air, gas
      DESCRIPTION: Some text
      CLASS: Fluids
      SUBCLASS: Gases

      PROPERTY: Density
      DEPENDENT: Density|kg m^-3|1.16,1.00
      INDEPENDENT: Temperature|C|23,100
      QUALIFIER: Behavior=Isotropic
      INTERPOLATION: Linear Multivariate (Qhull)
      EXTRAPOLATION: Projection to the Bounding Box
      ENDPROPERTY
      ENDMATERIAL
    """

    def parse(self, content: str) -> List[MaterialEntry]:
        materials: List[MaterialEntry] = []
        cur_mat: Optional[MaterialEntry] = None
        cur_prop: Optional[PropertyEntry] = None

        for raw_line in content.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue

            if line == "ENDPROPERTY":
                if cur_mat and cur_prop:
                    self._validate_property(cur_prop)
                    cur_mat.properties.append(cur_prop)
                cur_prop = None
                continue

            if line == "ENDMATERIAL":
                if cur_mat:
                    materials.append(cur_mat)
                cur_mat = None
                continue

            if ":" not in line:
                continue

            key, value = [part.strip() for part in line.split(":", 1)]
            key = key.upper()

            if key == "MATERIAL":
                cur_mat = MaterialEntry(name=value)
            elif key == "DESCRIPTION" and cur_mat:
                cur_mat.description = value
            elif key == "CLASS" and cur_mat:
                cur_mat.material_class = value
            elif key == "SUBCLASS" and cur_mat:
                cur_mat.subclass = value
            elif key == "PROPERTY":
                cur_prop = PropertyEntry(
                    name=value,
                    dependent_name="Value",
                    dependent_unit="",
                    dependent_values=[],
                )
            elif key == "DEPENDENT" and cur_prop:
                p_name, unit, vals = self._split_triplet(value)
                cur_prop.dependent_name = p_name
                cur_prop.dependent_unit = unit
                cur_prop.dependent_values = self._split_values(vals)
            elif key == "INDEPENDENT" and cur_prop:
                p_name, unit, vals = self._split_triplet(value)
                cur_prop.independent_vars.append(
                    IndependentSeries(name=p_name, unit=unit, values=self._split_values(vals))
                )
            elif key == "QUALIFIER" and cur_prop and "=" in value:
                qk, qv = [x.strip() for x in value.split("=", 1)]
                cur_prop.qualifiers[qk] = qv
            elif key == "INTERPOLATION" and cur_prop:
                cur_prop.interpolation = value
            elif key == "EXTRAPOLATION" and cur_prop:
                cur_prop.extrapolation = value

        if cur_prop and cur_mat:
            self._validate_property(cur_prop)
            cur_mat.properties.append(cur_prop)
        if cur_mat:
            materials.append(cur_mat)

        return materials

    @staticmethod
    def _split_triplet(value: str) -> tuple[str, str, str]:
        parts = [p.strip() for p in value.split("|")]
        if len(parts) != 3:
            raise ValueError(f"Expected 3 parts (name|unit|values), got: {value}")
        return parts[0], parts[1], parts[2]

    @staticmethod
    def _split_values(value: str) -> List[str]:
        return [v.strip() for v in value.split(",") if v.strip()]

    @staticmethod
    def _validate_property(prop: PropertyEntry) -> None:
        if not prop.dependent_values:
            raise ValueError(f"Property '{prop.name}' has no dependent values")
        dep_count = len(prop.dependent_values)
        for indep in prop.independent_vars:
            if len(indep.values) != dep_count:
                raise ValueError(
                    f"Value count mismatch in '{prop.name}': dependent={dep_count}, "
                    f"{indep.name}={len(indep.values)}"
                )


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Material XML Builder")
        self.geometry("1050x700")

        self.materials: List[MaterialEntry] = []
        self.current_material: Optional[MaterialEntry] = None
        self.pending_properties: List[PropertyEntry] = []

        self._build_ui()

    def _build_ui(self) -> None:
        top = ttk.LabelFrame(self, text="Material Details")
        top.pack(fill="x", padx=10, pady=8)

        self.name_var = tk.StringVar()
        self.class_var = tk.StringVar()
        self.subclass_var = tk.StringVar()

        ttk.Label(top, text="Name").grid(row=0, column=0, sticky="w")
        ttk.Entry(top, textvariable=self.name_var, width=40).grid(row=0, column=1, sticky="we", padx=5)

        ttk.Label(top, text="Class").grid(row=0, column=2, sticky="w")
        ttk.Entry(top, textvariable=self.class_var, width=30).grid(row=0, column=3, sticky="we", padx=5)

        ttk.Label(top, text="Subclass").grid(row=1, column=0, sticky="w")
        ttk.Entry(top, textvariable=self.subclass_var, width=40).grid(row=1, column=1, sticky="we", padx=5)

        ttk.Label(top, text="Description").grid(row=2, column=0, sticky="nw")
        self.desc_text = tk.Text(top, height=4, width=90)
        self.desc_text.grid(row=2, column=1, columnspan=3, sticky="we", pady=4)

        prop_frame = ttk.LabelFrame(self, text="Property Editor")
        prop_frame.pack(fill="x", padx=10, pady=8)

        self.prop_name = tk.StringVar()
        self.dep_name = tk.StringVar(value="Value")
        self.dep_unit = tk.StringVar()
        self.dep_values = tk.StringVar()
        self.indep_name = tk.StringVar(value="Temperature")
        self.indep_unit = tk.StringVar(value="C")
        self.indep_values = tk.StringVar()
        self.qualifier = tk.StringVar()
        self.interpolation = tk.StringVar()
        self.extrapolation = tk.StringVar()

        row = 0
        for label, var in [
            ("Property Name", self.prop_name),
            ("Dependent Name", self.dep_name),
            ("Dependent Unit", self.dep_unit),
            ("Dependent Values (comma-separated)", self.dep_values),
            ("Independent Name", self.indep_name),
            ("Independent Unit", self.indep_unit),
            ("Independent Values (comma-separated)", self.indep_values),
            ("Qualifiers (k=v;k2=v2)", self.qualifier),
            ("Interpolation", self.interpolation),
            ("Extrapolation", self.extrapolation),
        ]:
            ttk.Label(prop_frame, text=label).grid(row=row, column=0, sticky="w")
            ttk.Entry(prop_frame, textvariable=var, width=90).grid(row=row, column=1, sticky="we", pady=2)
            row += 1

        ttk.Button(prop_frame, text="Add Property", command=self.add_property).grid(row=row, column=0, pady=6)
        ttk.Button(prop_frame, text="Clear Fields", command=self.clear_property_fields).grid(row=row, column=1, sticky="w")

        list_frame = ttk.LabelFrame(self, text="Pending Properties / Materials")
        list_frame.pack(fill="both", expand=True, padx=10, pady=8)

        self.prop_list = tk.Listbox(list_frame, height=10)
        self.prop_list.pack(fill="both", expand=True, padx=5, pady=5)

        btns = ttk.Frame(self)
        btns.pack(fill="x", padx=10, pady=8)
        ttk.Button(btns, text="Save Current Material", command=self.save_current_material).pack(side="left", padx=5)
        ttk.Button(btns, text="Import Materials from TXT", command=self.import_txt).pack(side="left", padx=5)
        ttk.Button(btns, text="Export XML", command=self.export_xml).pack(side="right", padx=5)

    def clear_property_fields(self) -> None:
        self.prop_name.set("")
        self.dep_name.set("Value")
        self.dep_unit.set("")
        self.dep_values.set("")
        self.indep_name.set("Temperature")
        self.indep_unit.set("C")
        self.indep_values.set("")
        self.qualifier.set("")
        self.interpolation.set("")
        self.extrapolation.set("")

    def add_property(self) -> None:
        dep_values = [x.strip() for x in self.dep_values.get().split(",") if x.strip()]
        indep_values = [x.strip() for x in self.indep_values.get().split(",") if x.strip()]
        if not self.prop_name.get().strip() or not dep_values:
            messagebox.showerror("Invalid property", "Property name and dependent values are required.")
            return
        if indep_values and len(indep_values) != len(dep_values):
            messagebox.showerror("Invalid property", "Independent and dependent value counts must match.")
            return

        qualifiers: Dict[str, str] = {}
        if self.qualifier.get().strip():
            for chunk in self.qualifier.get().split(";"):
                if "=" in chunk:
                    k, v = [x.strip() for x in chunk.split("=", 1)]
                    qualifiers[k] = v

        indeps = []
        if indep_values:
            indeps.append(
                IndependentSeries(
                    name=self.indep_name.get().strip() or "Independent",
                    unit=self.indep_unit.get().strip(),
                    values=indep_values,
                )
            )

        prop = PropertyEntry(
            name=self.prop_name.get().strip(),
            dependent_name=self.dep_name.get().strip() or "Value",
            dependent_unit=self.dep_unit.get().strip(),
            dependent_values=dep_values,
            independent_vars=indeps,
            qualifiers=qualifiers,
            interpolation=self.interpolation.get().strip() or None,
            extrapolation=self.extrapolation.get().strip() or None,
        )

        self.pending_properties.append(prop)
        self.prop_list.insert("end", f"Property: {prop.name} ({len(dep_values)} pts)")
        self.clear_property_fields()

    def save_current_material(self) -> None:
        name = self.name_var.get().strip()
        if not name:
            messagebox.showerror("Missing name", "Material name is required.")
            return
        if not self.pending_properties:
            if not messagebox.askyesno("No properties", "Save material without properties?"):
                return

        material = MaterialEntry(
            name=name,
            description=self.desc_text.get("1.0", "end").strip(),
            material_class=self.class_var.get().strip(),
            subclass=self.subclass_var.get().strip(),
            properties=list(self.pending_properties),
        )
        self.materials.append(material)
        self.pending_properties.clear()
        self.prop_list.insert("end", f"Material saved: {material.name} ({len(material.properties)} properties)")

        self.name_var.set("")
        self.class_var.set("")
        self.subclass_var.set("")
        self.desc_text.delete("1.0", "end")

    def import_txt(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if not path:
            return
        try:
            content = Path(path).read_text(encoding="utf-8")
            parser = TextListParser()
            parsed = parser.parse(content)
            self.materials.extend(parsed)
            self.prop_list.insert("end", f"Imported {len(parsed)} materials from {Path(path).name}")
            messagebox.showinfo("Import complete", f"Imported {len(parsed)} material(s).")
        except Exception as exc:
            messagebox.showerror("Import failed", str(exc))

    def export_xml(self) -> None:
        if self.pending_properties:
            if messagebox.askyesno("Unsaved material", "You have pending properties. Save as a material now?"):
                self.save_current_material()
        if not self.materials:
            messagebox.showerror("Nothing to export", "No materials available. Add or import first.")
            return

        path = filedialog.asksaveasfilename(defaultextension=".xml", filetypes=[("XML files", "*.xml")])
        if not path:
            return

        root = EngineeringDataBuilder(self.materials).build()
        xml_str = EngineeringDataBuilder._prettify(root)
        Path(path).write_text(xml_str, encoding="utf-8")
        messagebox.showinfo("Export complete", f"Wrote XML file:\n{path}")


def main() -> None:
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
