#!/usr/bin/env python3
"""ANSYS Material XML Bot (GUI + CLI).

Supports two material schemas in one file:
1) GENERIC: arbitrary PROPERTY rows (name/value/unit/temperature)
2) ELECTROMAGNETIC: fixed B-H curve + guid + color structure
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import uuid
import xml.etree.ElementTree as ET
from xml.dom import minidom


@dataclass
class GenericProperty:
    name: str
    value: str
    unit: str = ""
    temperature_c: str = "23"


@dataclass
class MaterialItem:
    name: str
    kind: str = "GENERIC"  # GENERIC | ELECTROMAGNETIC
    mat_class: str = "User Materials"
    subclass: str = "Imported"
    description: str = ""

    # Generic fields
    properties: list[GenericProperty] = field(default_factory=list)

    # Electromagnetic fields
    bh_b: str = "0,1"
    bh_h: str = "0,1"
    red: float = 181.0
    green: float = 168.0
    blue: float = 168.0
    guid: str = ""


def _split_number_list(csv_text: str) -> list[str]:
    vals = [x.strip() for x in csv_text.split(",") if x.strip()]
    if not vals:
        raise ValueError("List cannot be empty.")
    return vals


def parse_material_text(raw_text: str) -> list[MaterialItem]:
    text = raw_text.replace("\\r\\n", "\n").replace("\\n", "\n")
    lines = text.splitlines()

    mats: list[MaterialItem] = []
    cur: MaterialItem | None = None

    for idx, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        upper = line.upper()

        if upper.startswith("MATERIAL:"):
            if cur:
                mats.append(cur)
            name = line.split(":", 1)[1].strip()
            if not name:
                raise ValueError(f"Line {idx}: MATERIAL name is required.")
            cur = MaterialItem(name=name)
        elif cur and upper.startswith("TYPE:"):
            t = line.split(":", 1)[1].strip().upper()
            if t not in {"GENERIC", "ELECTROMAGNETIC"}:
                raise ValueError(f"Line {idx}: TYPE must be GENERIC or ELECTROMAGNETIC.")
            cur.kind = t
            if t == "ELECTROMAGNETIC" and not cur.guid:
                cur.guid = str(uuid.uuid4())
                if cur.mat_class == "User Materials":
                    cur.mat_class = "Electromagnetic"
        elif cur and upper.startswith("CLASS:"):
            cur.mat_class = line.split(":", 1)[1].strip() or cur.mat_class
        elif cur and upper.startswith("SUBCLASS:"):
            cur.subclass = line.split(":", 1)[1].strip() or cur.subclass
        elif cur and upper.startswith("DESCRIPTION:"):
            cur.description = line.split(":", 1)[1].strip()
        elif cur and upper.startswith("PROPERTY:"):
            payload = line.split(":", 1)[1].strip()
            parts = [x.strip() for x in payload.split("|")]
            if len(parts) < 2 or not parts[0] or not parts[1]:
                raise ValueError(f"Line {idx}: PROPERTY must be PROPERTY: Name|Value|Unit|TemperatureC")
            while len(parts) < 4:
                parts.append("")
            cur.properties.append(
                GenericProperty(
                    name=parts[0],
                    value=parts[1],
                    unit=parts[2],
                    temperature_c=parts[3] or "23",
                )
            )
        elif cur and upper.startswith("BH_B:"):
            cur.bh_b = line.split(":", 1)[1].strip()
            cur.kind = "ELECTROMAGNETIC"
            if not cur.guid:
                cur.guid = str(uuid.uuid4())
            if cur.mat_class == "User Materials":
                cur.mat_class = "Electromagnetic"
        elif cur and upper.startswith("BH_H:"):
            cur.bh_h = line.split(":", 1)[1].strip()
            cur.kind = "ELECTROMAGNETIC"
        elif cur and upper.startswith("COLOR:"):
            rgb = [x.strip() for x in line.split(":", 1)[1].split(",")]
            if len(rgb) != 3:
                raise ValueError(f"Line {idx}: COLOR must be COLOR: R,G,B")
            cur.red, cur.green, cur.blue = [float(x) for x in rgb]
            cur.kind = "ELECTROMAGNETIC"
        elif cur and upper.startswith("GUID:"):
            cur.guid = line.split(":", 1)[1].strip() or str(uuid.uuid4())
            cur.kind = "ELECTROMAGNETIC"
        elif cur and upper == "END":
            mats.append(cur)
            cur = None
        else:
            raise ValueError(f"Line {idx}: Unrecognized input '{line}'.")

    if cur:
        mats.append(cur)

    for m in mats:
        if m.kind == "ELECTROMAGNETIC":
            b = _split_number_list(m.bh_b)
            h = _split_number_list(m.bh_h)
            if len(b) != len(h):
                raise ValueError(f"Material '{m.name}': BH_B and BH_H lengths differ.")
            if not m.guid:
                m.guid = str(uuid.uuid4())
        else:
            if not m.properties:
                raise ValueError(f"Material '{m.name}': GENERIC materials need at least one PROPERTY line.")

    return mats


def _var_type_text(kind: str, count: int) -> str:
    return ",".join([kind] * count)


def build_xml_tree(materials: list[MaterialItem]) -> ET.Element:
    root = ET.Element("EngineeringData", version="25.2.0.233", versiondate="6/12/2025 11:41:00 AM")
    ET.SubElement(root, "Notes")
    mats_node = ET.SubElement(root, "Materials")
    matml_doc = ET.SubElement(mats_node, "MatML_Doc")

    used_em = False
    generic_property_names: list[str] = []

    # Start generated IDs away from electromagnetic fixed IDs
    next_pr = 100
    next_pa = 100

    for m in materials:
        mat = ET.SubElement(matml_doc, "Material")
        bulk = ET.SubElement(mat, "BulkDetails")
        ET.SubElement(bulk, "Name").text = m.name
        if m.description:
            ET.SubElement(bulk, "Description").text = m.description

        cls = ET.SubElement(bulk, "Class")
        ET.SubElement(cls, "Name").text = m.mat_class

        if m.subclass:
            sub = ET.SubElement(bulk, "Subclass")
            ET.SubElement(sub, "Name").text = m.subclass

        if m.kind == "ELECTROMAGNETIC":
            used_em = True
            b_vals = _split_number_list(m.bh_b)
            h_vals = _split_number_list(m.bh_h)

            pr0 = ET.SubElement(bulk, "PropertyData", property="pr0")
            ET.SubElement(pr0, "Data", format="string").text = "-"
            pa0 = ET.SubElement(pr0, "ParameterValue", parameter="pa0", format="float")
            ET.SubElement(pa0, "Data").text = ",".join(b_vals)
            ET.SubElement(pa0, "Qualifier", name="Variable Type").text = _var_type_text("Dependent", len(b_vals))
            pa1 = ET.SubElement(pr0, "ParameterValue", parameter="pa1", format="float")
            ET.SubElement(pa1, "Data").text = ",".join(h_vals)
            ET.SubElement(pa1, "Qualifier", name="Variable Type").text = _var_type_text("Independent", len(h_vals))

            pr1 = ET.SubElement(bulk, "PropertyData", property="pr1")
            ET.SubElement(pr1, "Data", format="string").text = "-"
            ET.SubElement(pr1, "Qualifier", name="guid").text = m.guid
            ET.SubElement(pr1, "Qualifier", name="Display").text = "False"

            pr2 = ET.SubElement(bulk, "PropertyData", property="pr2")
            ET.SubElement(pr2, "Data", format="string").text = "-"
            for pid, val in (("pa2", m.red), ("pa3", m.green), ("pa4", m.blue)):
                p = ET.SubElement(pr2, "ParameterValue", parameter=pid, format="float")
                ET.SubElement(p, "Data").text = str(val).rstrip("0").rstrip(".")
                ET.SubElement(p, "Qualifier", name="Variable Type").text = "Dependent"
            pa5 = ET.SubElement(pr2, "ParameterValue", parameter="pa5", format="string")
            ET.SubElement(pa5, "Data").text = "Appearance"
        else:
            for prop in m.properties:
                prid = f"pr{next_pr}"
                next_pr += 1
                generic_property_names.append((prid, prop.name))

                pd = ET.SubElement(bulk, "PropertyData", property=prid)
                ET.SubElement(pd, "Data", format="string").text = "-"

                pa_dep_id = f"pa{next_pa}"
                next_pa += 1
                dep = ET.SubElement(pd, "ParameterValue", parameter=pa_dep_id, format="float")
                ET.SubElement(dep, "Data").text = prop.value
                ET.SubElement(dep, "Qualifier", name="Variable Type").text = "Dependent"
                if prop.unit:
                    ET.SubElement(dep, "Qualifier", name="Units").text = prop.unit

                pa_temp_id = f"pa{next_pa}"
                next_pa += 1
                ind = ET.SubElement(pd, "ParameterValue", parameter=pa_temp_id, format="float")
                ET.SubElement(ind, "Data").text = prop.temperature_c
                ET.SubElement(ind, "Qualifier", name="Variable Type").text = "Independent"
                ET.SubElement(ind, "Qualifier", name="Field Variable").text = "Temperature"
                ET.SubElement(ind, "Qualifier", name="Field Units").text = "C"

                # Save parameter names by putting as attributes for metadata generation
                pd.set("_dep_id", pa_dep_id)
                pd.set("_temp_id", pa_temp_id)
                pd.set("_prop_name", prop.name)

    _append_metadata(matml_doc, used_em)
    _append_generic_metadata(matml_doc)
    return root


def _append_metadata(parent: ET.Element, include_em: bool) -> None:
    if not include_em:
        return
    md = ET.SubElement(parent, "Metadata")

    pa0 = ET.SubElement(md, "ParameterDetails", id="pa0")
    ET.SubElement(pa0, "Name").text = "Magnetic Flux Density"
    u0 = ET.SubElement(pa0, "Units", name="Magnetic Flux Density")
    u00 = ET.SubElement(u0, "Unit")
    ET.SubElement(u00, "Name").text = "T"

    pa1 = ET.SubElement(md, "ParameterDetails", id="pa1")
    ET.SubElement(pa1, "Name").text = "Magnetic Field Intensity"
    u1 = ET.SubElement(pa1, "Units", name="Magnetic Field Intensity")
    u10 = ET.SubElement(u1, "Unit")
    ET.SubElement(u10, "Name").text = "A"
    u11 = ET.SubElement(u1, "Unit", power="-1")
    ET.SubElement(u11, "Name").text = "m"

    for pid, pname in (("pa2", "Red"), ("pa3", "Green"), ("pa4", "Blue"), ("pa5", "Material Property")):
        p = ET.SubElement(md, "ParameterDetails", id=pid)
        ET.SubElement(p, "Name").text = pname
        ET.SubElement(p, "Unitless")

    for prid, pname in (("pr0", "B-H Curve"), ("pr1", "Material Unique Id"), ("pr2", "Color")):
        p = ET.SubElement(md, "PropertyDetails", id=prid)
        ET.SubElement(p, "Unitless")
        ET.SubElement(p, "Name").text = pname


def _append_generic_metadata(matml_doc: ET.Element) -> None:
    # find generated generic property IDs stored on PropertyData attrs
    generic_nodes = []
    for pd in matml_doc.findall("./Material/BulkDetails/PropertyData"):
        prop_id = pd.get("property", "")
        if prop_id.startswith("pr") and prop_id[2:].isdigit() and int(prop_id[2:]) >= 100:
            generic_nodes.append(pd)

    if not generic_nodes:
        return

    md = ET.SubElement(matml_doc, "Metadata")
    seen_params: set[str] = set()

    for pd in generic_nodes:
        prop_id = pd.get("property")
        prop_name = pd.get("_prop_name", "Property")
        dep_id = pd.get("_dep_id")
        temp_id = pd.get("_temp_id")

        if dep_id and dep_id not in seen_params:
            seen_params.add(dep_id)
            p = ET.SubElement(md, "ParameterDetails", id=dep_id)
            ET.SubElement(p, "Name").text = f"{prop_name} Value"
            ET.SubElement(p, "Unitless")

        if temp_id and temp_id not in seen_params:
            seen_params.add(temp_id)
            p = ET.SubElement(md, "ParameterDetails", id=temp_id)
            ET.SubElement(p, "Name").text = "Temperature"
            units = ET.SubElement(p, "Units", name="Temperature")
            u = ET.SubElement(units, "Unit")
            ET.SubElement(u, "Name").text = "C"

        if prop_id:
            pr = ET.SubElement(md, "PropertyDetails", id=prop_id)
            ET.SubElement(pr, "Unitless")
            ET.SubElement(pr, "Name").text = prop_name

    # cleanup helper attributes before output
    for pd in generic_nodes:
        for k in ("_dep_id", "_temp_id", "_prop_name"):
            if k in pd.attrib:
                del pd.attrib[k]


def write_xml(materials: list[MaterialItem], output: Path) -> None:
    root = build_xml_tree(materials)
    xml = ET.tostring(root, encoding="utf-8")
    pretty = minidom.parseString(xml).toprettyxml(indent="  ")
    output.write_text(pretty, encoding="utf-8")


class MaterialXMLBot:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("ANSYS Material XML Bot (Any Materials)")
        self.root.geometry("1200x760")
        self.materials: list[MaterialItem] = []
        self._build_ui()

    def _build_ui(self) -> None:
        frm = ttk.Frame(self.root, padding=10)
        frm.pack(fill=tk.BOTH, expand=True)

        left = ttk.LabelFrame(frm, text="Manual Material Entry", padding=10)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 8))

        self.type_var = tk.StringVar(value="GENERIC")
        self.name_var = tk.StringVar()
        self.class_var = tk.StringVar(value="User Materials")
        self.subclass_var = tk.StringVar(value="Imported")
        self.desc_var = tk.StringVar()

        self.guid_var = tk.StringVar(value=str(uuid.uuid4()))
        self.bh_b_var = tk.StringVar(value="0,1")
        self.bh_h_var = tk.StringVar(value="0,1")
        self.red_var = tk.StringVar(value="181")
        self.green_var = tk.StringVar(value="168")
        self.blue_var = tk.StringVar(value="168")

        ttk.Label(left, text="Type").grid(row=0, column=0, sticky="w")
        ttk.Combobox(left, textvariable=self.type_var, values=["GENERIC", "ELECTROMAGNETIC"], state="readonly").grid(row=0, column=1, sticky="ew", pady=2)
        ttk.Label(left, text="Material Name *").grid(row=1, column=0, sticky="w")
        ttk.Entry(left, textvariable=self.name_var).grid(row=1, column=1, sticky="ew", pady=2)
        ttk.Label(left, text="Class").grid(row=2, column=0, sticky="w")
        ttk.Entry(left, textvariable=self.class_var).grid(row=2, column=1, sticky="ew", pady=2)
        ttk.Label(left, text="Subclass").grid(row=3, column=0, sticky="w")
        ttk.Entry(left, textvariable=self.subclass_var).grid(row=3, column=1, sticky="ew", pady=2)
        ttk.Label(left, text="Description").grid(row=4, column=0, sticky="w")
        ttk.Entry(left, textvariable=self.desc_var).grid(row=4, column=1, sticky="ew", pady=2)

        # Generic property lines
        gbox = ttk.LabelFrame(left, text="GENERIC properties (one per line: Name|Value|Unit|TempC)", padding=6)
        gbox.grid(row=5, column=0, columnspan=2, sticky="nsew", pady=(8, 4))
        self.prop_text = tk.Text(gbox, height=9)
        self.prop_text.pack(fill=tk.BOTH, expand=True)

        # Electromagnetic fields
        ebox = ttk.LabelFrame(left, text="ELECTROMAGNETIC fields", padding=6)
        ebox.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(4, 4))
        ttk.Label(ebox, text="GUID").grid(row=0, column=0, sticky="w")
        ttk.Entry(ebox, textvariable=self.guid_var, width=42).grid(row=0, column=1, sticky="ew", pady=2)
        ttk.Button(ebox, text="New GUID", command=lambda: self.guid_var.set(str(uuid.uuid4()))).grid(row=0, column=2, padx=4)
        ttk.Label(ebox, text="BH_B").grid(row=1, column=0, sticky="w")
        ttk.Entry(ebox, textvariable=self.bh_b_var).grid(row=1, column=1, columnspan=2, sticky="ew", pady=2)
        ttk.Label(ebox, text="BH_H").grid(row=2, column=0, sticky="w")
        ttk.Entry(ebox, textvariable=self.bh_h_var).grid(row=2, column=1, columnspan=2, sticky="ew", pady=2)
        ttk.Label(ebox, text="Color R,G,B").grid(row=3, column=0, sticky="w")
        colors = ttk.Frame(ebox)
        colors.grid(row=3, column=1, columnspan=2, sticky="ew")
        ttk.Entry(colors, textvariable=self.red_var, width=8).pack(side=tk.LEFT, padx=2)
        ttk.Entry(colors, textvariable=self.green_var, width=8).pack(side=tk.LEFT, padx=2)
        ttk.Entry(colors, textvariable=self.blue_var, width=8).pack(side=tk.LEFT, padx=2)

        left.grid_columnconfigure(1, weight=1)
        left.grid_rowconfigure(5, weight=1)

        ttk.Button(left, text="Add Material to Queue", command=self.add_material).grid(row=7, column=0, columnspan=2, sticky="ew", pady=(6, 0))

        right = ttk.LabelFrame(frm, text="Queue / Operations", padding=10)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.listbox = tk.Listbox(right)
        self.listbox.pack(fill=tk.BOTH, expand=True)
        ttk.Button(right, text="Import Text File", command=self.import_txt).pack(fill=tk.X, pady=2)
        ttk.Button(right, text="Remove Selected", command=self.remove_selected).pack(fill=tk.X, pady=2)
        ttk.Button(right, text="Save XML", command=self.save_xml).pack(fill=tk.X, pady=2)
        ttk.Button(right, text="Clear All", command=self.clear_all).pack(fill=tk.X, pady=2)

    def add_material(self) -> None:
        try:
            kind = self.type_var.get().strip().upper() or "GENERIC"
            name = self.name_var.get().strip()
            if not name:
                raise ValueError("Material name is required.")
            m = MaterialItem(
                name=name,
                kind=kind,
                mat_class=self.class_var.get().strip() or ("Electromagnetic" if kind == "ELECTROMAGNETIC" else "User Materials"),
                subclass=self.subclass_var.get().strip() or "Imported",
                description=self.desc_var.get().strip(),
            )

            if kind == "ELECTROMAGNETIC":
                m.guid = self.guid_var.get().strip() or str(uuid.uuid4())
                m.bh_b = self.bh_b_var.get().strip()
                m.bh_h = self.bh_h_var.get().strip()
                m.red = float(self.red_var.get().strip())
                m.green = float(self.green_var.get().strip())
                m.blue = float(self.blue_var.get().strip())
                if len(_split_number_list(m.bh_b)) != len(_split_number_list(m.bh_h)):
                    raise ValueError("BH_B and BH_H must have the same number of points.")
            else:
                raw_lines = self.prop_text.get("1.0", tk.END).splitlines()
                for line in raw_lines:
                    line = line.strip()
                    if not line:
                        continue
                    parts = [x.strip() for x in line.split("|")]
                    if len(parts) < 2 or not parts[0] or not parts[1]:
                        raise ValueError(f"Invalid property line: {line}")
                    while len(parts) < 4:
                        parts.append("")
                    m.properties.append(GenericProperty(parts[0], parts[1], parts[2], parts[3] or "23"))
                if not m.properties:
                    raise ValueError("GENERIC materials require at least one property line.")

            self.materials.append(m)
            self.listbox.insert(tk.END, f"{m.name} [{m.kind}]")
            self.name_var.set("")
            if kind == "ELECTROMAGNETIC":
                self.guid_var.set(str(uuid.uuid4()))
            else:
                self.prop_text.delete("1.0", tk.END)
        except Exception as exc:
            messagebox.showerror("Invalid material", str(exc))

    def import_txt(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if not path:
            return
        try:
            mats = parse_material_text(Path(path).read_text(encoding="utf-8"))
            self.materials.extend(mats)
            for m in mats:
                self.listbox.insert(tk.END, f"{m.name} [{m.kind}]")
            messagebox.showinfo("Import complete", f"Imported {len(mats)} material(s).")
        except Exception as exc:
            messagebox.showerror("Import failed", str(exc))

    def remove_selected(self) -> None:
        sel = self.listbox.curselection()
        if not sel:
            return
        i = sel[0]
        self.listbox.delete(i)
        self.materials.pop(i)

    def clear_all(self) -> None:
        self.materials.clear()
        self.listbox.delete(0, tk.END)

    def save_xml(self) -> None:
        if not self.materials:
            messagebox.showwarning("No materials", "Please add/import materials first.")
            return
        out = filedialog.asksaveasfilename(defaultextension=".xml", filetypes=[("XML files", "*.xml")])
        if not out:
            return
        write_xml(self.materials, Path(out))
        messagebox.showinfo("Saved", f"Saved XML to:\n{out}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build ANSYS EngineeringData XML for any materials.")
    parser.add_argument("--from-file", help="Input text file")
    parser.add_argument("--output", help="Output XML file")
    args = parser.parse_args()

    if args.from_file:
        if not args.output:
            raise SystemExit("Error: --output is required with --from-file")
        mats = parse_material_text(Path(args.from_file).read_text(encoding="utf-8"))
        write_xml(mats, Path(args.output))
        print(f"Wrote {len(mats)} material(s) to {args.output}")
        return

    root = tk.Tk()
    MaterialXMLBot(root)
    root.mainloop()


if __name__ == "__main__":
    main()
