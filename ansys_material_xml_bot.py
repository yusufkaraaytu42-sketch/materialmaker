#!/usr/bin/env python3
"""ANSYS Electromagnetic Material XML Bot (GUI + CLI).

Builds EngineeringData XML in the same structure used by ANSYS electromagnetic
materials with:
- pr0: B-H Curve (pa0/pa1)
- pr1: Material Unique Id (guid/display)
- pr2: Color (pa2/pa3/pa4 + pa5='Appearance')
- shared Metadata for pa0..pa5 and pr0..pr2
"""
from __future__ import annotations

import argparse
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from dataclasses import dataclass
from pathlib import Path
import uuid
import xml.etree.ElementTree as ET
from xml.dom import minidom


@dataclass
class MaterialItem:
    name: str
    mat_class: str = "Electromagnetic"
    bh_b: str = "0,1"
    bh_h: str = "0,1"
    red: float = 180.0
    green: float = 180.0
    blue: float = 180.0
    guid: str = ""


def _split_number_list(csv_text: str) -> list[str]:
    parts = [x.strip() for x in csv_text.split(",") if x.strip()]
    if not parts:
        raise ValueError("B-H list cannot be empty.")
    return parts


def parse_material_text(raw_text: str) -> list[MaterialItem]:
    text = raw_text.replace("\\r\\n", "\n").replace("\\n", "\n")
    lines = text.splitlines()

    mats: list[MaterialItem] = []
    current: MaterialItem | None = None

    for idx, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue

        upper = line.upper()
        if upper.startswith("MATERIAL:"):
            if current:
                mats.append(current)
            name = line.split(":", 1)[1].strip()
            if not name:
                raise ValueError(f"Line {idx}: MATERIAL name is required.")
            current = MaterialItem(name=name, guid=str(uuid.uuid4()))
        elif current and upper.startswith("CLASS:"):
            current.mat_class = line.split(":", 1)[1].strip() or current.mat_class
        elif current and upper.startswith("BH_B:"):
            current.bh_b = line.split(":", 1)[1].strip()
        elif current and upper.startswith("BH_H:"):
            current.bh_h = line.split(":", 1)[1].strip()
        elif current and upper.startswith("COLOR:"):
            rgb = [x.strip() for x in line.split(":", 1)[1].split(",")]
            if len(rgb) != 3:
                raise ValueError(f"Line {idx}: COLOR must be 'COLOR: R,G,B'.")
            current.red, current.green, current.blue = [float(x) for x in rgb]
        elif current and upper.startswith("GUID:"):
            current.guid = line.split(":", 1)[1].strip() or str(uuid.uuid4())
        elif current and upper == "END":
            mats.append(current)
            current = None
        else:
            raise ValueError(f"Line {idx}: Unrecognized input '{line}'.")

    if current:
        mats.append(current)

    for m in mats:
        b = _split_number_list(m.bh_b)
        h = _split_number_list(m.bh_h)
        if len(b) != len(h):
            raise ValueError(f"Material '{m.name}': BH_B and BH_H must have the same number of points.")
        if not m.guid:
            m.guid = str(uuid.uuid4())

    return mats


def _var_type_text(kind: str, count: int) -> str:
    return ",".join([kind] * count)


def build_xml_tree(materials: list[MaterialItem]) -> ET.Element:
    root = ET.Element("EngineeringData", version="25.2.0.233", versiondate="6/12/2025 11:41:00 AM")
    ET.SubElement(root, "Notes")
    materials_node = ET.SubElement(root, "Materials")
    matml_doc = ET.SubElement(materials_node, "MatML_Doc")

    for m in materials:
        b_vals = _split_number_list(m.bh_b)
        h_vals = _split_number_list(m.bh_h)

        mat = ET.SubElement(matml_doc, "Material")
        bulk = ET.SubElement(mat, "BulkDetails")
        ET.SubElement(bulk, "Name").text = m.name

        cls = ET.SubElement(bulk, "Class")
        ET.SubElement(cls, "Name").text = m.mat_class

        # pr0: B-H Curve
        pr0 = ET.SubElement(bulk, "PropertyData", property="pr0")
        ET.SubElement(pr0, "Data", format="string").text = "-"

        pa0 = ET.SubElement(pr0, "ParameterValue", parameter="pa0", format="float")
        ET.SubElement(pa0, "Data").text = ",".join(b_vals)
        ET.SubElement(pa0, "Qualifier", name="Variable Type").text = _var_type_text("Dependent", len(b_vals))

        pa1 = ET.SubElement(pr0, "ParameterValue", parameter="pa1", format="float")
        ET.SubElement(pa1, "Data").text = ",".join(h_vals)
        ET.SubElement(pa1, "Qualifier", name="Variable Type").text = _var_type_text("Independent", len(h_vals))

        # pr1: Material Unique Id
        pr1 = ET.SubElement(bulk, "PropertyData", property="pr1")
        ET.SubElement(pr1, "Data", format="string").text = "-"
        ET.SubElement(pr1, "Qualifier", name="guid").text = m.guid
        ET.SubElement(pr1, "Qualifier", name="Display").text = "False"

        # pr2: Color
        pr2 = ET.SubElement(bulk, "PropertyData", property="pr2")
        ET.SubElement(pr2, "Data", format="string").text = "-"

        for pid, val in (("pa2", m.red), ("pa3", m.green), ("pa4", m.blue)):
            p = ET.SubElement(pr2, "ParameterValue", parameter=pid, format="float")
            ET.SubElement(p, "Data").text = str(val).rstrip("0").rstrip(".") if isinstance(val, float) else str(val)
            ET.SubElement(p, "Qualifier", name="Variable Type").text = "Dependent"

        pa5 = ET.SubElement(pr2, "ParameterValue", parameter="pa5", format="string")
        ET.SubElement(pa5, "Data").text = "Appearance"

    _append_metadata(matml_doc)
    return root


def _append_metadata(parent: ET.Element) -> None:
    md = ET.SubElement(parent, "Metadata")

    pa0 = ET.SubElement(md, "ParameterDetails", id="pa0")
    ET.SubElement(pa0, "Name").text = "Magnetic Flux Density"
    u0 = ET.SubElement(pa0, "Units", name="Magnetic Flux Density")
    uu0 = ET.SubElement(u0, "Unit")
    ET.SubElement(uu0, "Name").text = "T"

    pa1 = ET.SubElement(md, "ParameterDetails", id="pa1")
    ET.SubElement(pa1, "Name").text = "Magnetic Field Intensity"
    u1 = ET.SubElement(pa1, "Units", name="Magnetic Field Intensity")
    u1a = ET.SubElement(u1, "Unit")
    ET.SubElement(u1a, "Name").text = "A"
    u1b = ET.SubElement(u1, "Unit", power="-1")
    ET.SubElement(u1b, "Name").text = "m"

    for pid, pname in (("pa2", "Red"), ("pa3", "Green"), ("pa4", "Blue"), ("pa5", "Material Property")):
        p = ET.SubElement(md, "ParameterDetails", id=pid)
        ET.SubElement(p, "Name").text = pname
        ET.SubElement(p, "Unitless")

    for prid, pname in (("pr0", "B-H Curve"), ("pr1", "Material Unique Id"), ("pr2", "Color")):
        p = ET.SubElement(md, "PropertyDetails", id=prid)
        ET.SubElement(p, "Unitless")
        ET.SubElement(p, "Name").text = pname


def write_xml(materials: list[MaterialItem], output_path: Path) -> None:
    xml_root = build_xml_tree(materials)
    raw = ET.tostring(xml_root, encoding="utf-8")
    pretty = minidom.parseString(raw).toprettyxml(indent="  ")
    output_path.write_text(pretty, encoding="utf-8")


class MaterialXMLBot:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("ANSYS Electromagnetic Material XML Bot")
        self.root.geometry("1100x720")
        self.materials: list[MaterialItem] = []
        self._build_ui()

    def _build_ui(self) -> None:
        frm = ttk.Frame(self.root, padding=10)
        frm.pack(fill=tk.BOTH, expand=True)

        left = ttk.LabelFrame(frm, text="Manual Material Entry", padding=10)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 8))

        self.name_var = tk.StringVar()
        self.class_var = tk.StringVar(value="Electromagnetic")
        self.guid_var = tk.StringVar(value=str(uuid.uuid4()))
        self.bh_b_var = tk.StringVar(value="0,1")
        self.bh_h_var = tk.StringVar(value="0,1")
        self.red_var = tk.StringVar(value="181")
        self.green_var = tk.StringVar(value="168")
        self.blue_var = tk.StringVar(value="168")

        row = 0
        for label, var in (
            ("Material Name *", self.name_var),
            ("Class", self.class_var),
            ("GUID", self.guid_var),
            ("BH_B (Tesla, comma list)", self.bh_b_var),
            ("BH_H (A/m, comma list)", self.bh_h_var),
            ("Color R", self.red_var),
            ("Color G", self.green_var),
            ("Color B", self.blue_var),
        ):
            ttk.Label(left, text=label).grid(row=row, column=0, sticky="w")
            ttk.Entry(left, textvariable=var, width=64).grid(row=row, column=1, sticky="ew", pady=3)
            row += 1

        left.grid_columnconfigure(1, weight=1)

        btns = ttk.Frame(left)
        btns.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        ttk.Button(btns, text="Add Material to Queue", command=self.add_material).pack(side=tk.LEFT)
        ttk.Button(btns, text="New GUID", command=lambda: self.guid_var.set(str(uuid.uuid4()))).pack(side=tk.LEFT, padx=6)

        right = ttk.LabelFrame(frm, text="Queue / File Operations", padding=10)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.material_list = tk.Listbox(right)
        self.material_list.pack(fill=tk.BOTH, expand=True)

        ttk.Button(right, text="Import Materials from Text File", command=self.import_txt).pack(fill=tk.X, pady=2)
        ttk.Button(right, text="Remove Selected Material", command=self.remove_material).pack(fill=tk.X, pady=2)
        ttk.Button(right, text="Save XML", command=self.save_xml).pack(fill=tk.X, pady=2)
        ttk.Button(right, text="Clear All", command=self.clear_all).pack(fill=tk.X, pady=2)

    def add_material(self) -> None:
        try:
            m = MaterialItem(
                name=self.name_var.get().strip(),
                mat_class=self.class_var.get().strip() or "Electromagnetic",
                guid=self.guid_var.get().strip() or str(uuid.uuid4()),
                bh_b=self.bh_b_var.get().strip(),
                bh_h=self.bh_h_var.get().strip(),
                red=float(self.red_var.get().strip()),
                green=float(self.green_var.get().strip()),
                blue=float(self.blue_var.get().strip()),
            )
            if not m.name:
                raise ValueError("Material name is required.")
            if len(_split_number_list(m.bh_b)) != len(_split_number_list(m.bh_h)):
                raise ValueError("BH_B and BH_H must have the same number of points.")
        except Exception as exc:
            messagebox.showerror("Invalid material", str(exc))
            return

        self.materials.append(m)
        self.material_list.insert(tk.END, m.name)
        self.name_var.set("")
        self.guid_var.set(str(uuid.uuid4()))

    def import_txt(self) -> None:
        path = filedialog.askopenfilename(
            title="Select text material list",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            mats = parse_material_text(Path(path).read_text(encoding="utf-8"))
            self.materials.extend(mats)
            for m in mats:
                self.material_list.insert(tk.END, m.name)
            messagebox.showinfo("Import complete", f"Imported {len(mats)} material(s).")
        except Exception as exc:
            messagebox.showerror("Import failed", str(exc))

    def remove_material(self) -> None:
        sel = self.material_list.curselection()
        if not sel:
            return
        idx = sel[0]
        self.material_list.delete(idx)
        self.materials.pop(idx)

    def clear_all(self) -> None:
        self.materials.clear()
        self.material_list.delete(0, tk.END)

    def save_xml(self) -> None:
        if not self.materials:
            messagebox.showwarning("No materials", "Please add/import at least one material.")
            return
        out = filedialog.asksaveasfilename(
            title="Save ANSYS XML",
            defaultextension=".xml",
            filetypes=[("XML files", "*.xml")],
        )
        if not out:
            return
        write_xml(self.materials, Path(out))
        messagebox.showinfo("Saved", f"XML file saved:\n{out}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build ANSYS electromagnetic EngineeringData XML.")
    parser.add_argument("--from-file", help="Text file with MATERIAL blocks")
    parser.add_argument("--output", help="Output XML file path")
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
