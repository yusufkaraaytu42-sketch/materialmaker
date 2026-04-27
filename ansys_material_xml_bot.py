#!/usr/bin/env python3
"""GUI/CLI tool to build ANSYS EngineeringData XML material libraries.

Features:
- Manual material entry through a Tkinter form.
- Bulk import from a plain-text file.
- Optional CLI mode for text-file -> XML conversion.
- Save generated XML in EngineeringData format.
"""
from __future__ import annotations

import argparse
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from dataclasses import dataclass, field
from pathlib import Path
import xml.etree.ElementTree as ET
from xml.dom import minidom


@dataclass
class PropertyItem:
    name: str
    value: str
    unit: str = ""
    temperature_c: str = "23"


@dataclass
class MaterialItem:
    name: str
    description: str = ""
    category: str = "User Materials"
    subclass: str = "Imported"
    properties: list[PropertyItem] = field(default_factory=list)


def parse_material_text(raw_text: str) -> list[MaterialItem]:
    """Parse MATERIAL blocks from plain text.

    Supported directives:
      MATERIAL, DESCRIPTION, CLASS, SUBCLASS, PROPERTY, END
    """
    # Some editors/tools copy escaped newlines literally; normalize those.
    text = raw_text.replace("\\r\\n", "\n").replace("\\n", "\n")
    lines = text.splitlines()

    materials: list[MaterialItem] = []
    current: MaterialItem | None = None

    for idx, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue

        upper = line.upper()
        if upper.startswith("MATERIAL:"):
            if current:
                materials.append(current)
            name = line.split(":", 1)[1].strip()
            if not name:
                raise ValueError(f"Line {idx}: MATERIAL name is required.")
            current = MaterialItem(name=name)
        elif current and upper.startswith("DESCRIPTION:"):
            current.description = line.split(":", 1)[1].strip()
        elif current and upper.startswith("CLASS:"):
            current.category = line.split(":", 1)[1].strip() or current.category
        elif current and upper.startswith("SUBCLASS:"):
            current.subclass = line.split(":", 1)[1].strip() or current.subclass
        elif current and upper.startswith("PROPERTY:"):
            payload = line.split(":", 1)[1].strip()
            parts = [x.strip() for x in payload.split("|")]
            if len(parts) < 2 or not parts[0] or not parts[1]:
                raise ValueError(
                    f"Line {idx}: PROPERTY must be 'PROPERTY: Name|Value|Units|TemperatureC'."
                )
            while len(parts) < 4:
                parts.append("")
            current.properties.append(
                PropertyItem(
                    name=parts[0],
                    value=parts[1],
                    unit=parts[2],
                    temperature_c=parts[3] or "23",
                )
            )
        elif current and upper == "END":
            materials.append(current)
            current = None
        elif ":" in line and not current:
            raise ValueError(
                f"Line {idx}: Found '{line}'. Start each block with 'MATERIAL: <name>'."
            )
        else:
            raise ValueError(f"Line {idx}: Unrecognized input '{line}'.")

    if current:
        materials.append(current)

    return materials


def build_xml_tree(materials: list[MaterialItem]) -> ET.Element:
    root = ET.Element("EngineeringData", version="25.2.0.233", versiondate="6/12/2025 11:41:00 AM")
    ET.SubElement(root, "Notes")
    materials_node = ET.SubElement(root, "Materials")
    matml_doc = ET.SubElement(materials_node, "MatML_Doc")

    for m in materials:
        mat_node = ET.SubElement(matml_doc, "Material")
        bulk = ET.SubElement(mat_node, "BulkDetails")

        ET.SubElement(bulk, "Name").text = m.name
        ET.SubElement(bulk, "Description").text = m.description

        cls = ET.SubElement(bulk, "Class")
        ET.SubElement(cls, "Name").text = m.category

        sub = ET.SubElement(bulk, "Subclass")
        ET.SubElement(sub, "Name").text = m.subclass

        for i, p in enumerate(m.properties, start=1):
            prop_tag = f"pr{i}"
            pd = ET.SubElement(bulk, "PropertyData", property=prop_tag)
            ET.SubElement(pd, "Data", format="string").text = "-"
            ET.SubElement(pd, "Qualifier", name="Field Variable Compatible").text = "Temperature"

            prop_name_param = ET.SubElement(pd, "ParameterValue", parameter=f"pa{i*10}", format="string")
            ET.SubElement(prop_name_param, "Data").text = p.name

            dep = ET.SubElement(pd, "ParameterValue", parameter=f"pa{i*10+1}", format="float")
            ET.SubElement(dep, "Data").text = p.value
            ET.SubElement(dep, "Qualifier", name="Variable Type").text = "Dependent"
            if p.unit:
                ET.SubElement(dep, "Qualifier", name="Units").text = p.unit

            indep = ET.SubElement(pd, "ParameterValue", parameter=f"pa{i*10+2}", format="float")
            ET.SubElement(indep, "Data").text = p.temperature_c
            ET.SubElement(indep, "Qualifier", name="Variable Type").text = "Independent"
            ET.SubElement(indep, "Qualifier", name="Field Variable").text = "Temperature"
            ET.SubElement(indep, "Qualifier", name="Field Units").text = "C"

    return root


def write_xml(materials: list[MaterialItem], output_path: Path) -> None:
    xml_root = build_xml_tree(materials)
    raw = ET.tostring(xml_root, encoding="utf-8")
    pretty = minidom.parseString(raw).toprettyxml(indent="  ")
    output_path.write_text(pretty, encoding="utf-8")


class MaterialXMLBot:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("ANSYS Material XML Bot")
        self.root.geometry("1050x700")

        self.materials: list[MaterialItem] = []
        self.current_properties: list[PropertyItem] = []

        self._build_ui()

    def _build_ui(self) -> None:
        frm = ttk.Frame(self.root, padding=10)
        frm.pack(fill=tk.BOTH, expand=True)

        # Left side: manual input
        left = ttk.LabelFrame(frm, text="Manual Material Entry", padding=10)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 8))

        ttk.Label(left, text="Material Name *").grid(row=0, column=0, sticky="w")
        self.name_var = tk.StringVar()
        ttk.Entry(left, textvariable=self.name_var, width=44).grid(row=0, column=1, sticky="ew", pady=2)

        ttk.Label(left, text="Description").grid(row=1, column=0, sticky="w")
        self.description_var = tk.StringVar()
        ttk.Entry(left, textvariable=self.description_var, width=44).grid(row=1, column=1, sticky="ew", pady=2)

        ttk.Label(left, text="Class").grid(row=2, column=0, sticky="w")
        self.class_var = tk.StringVar(value="User Materials")
        ttk.Entry(left, textvariable=self.class_var, width=44).grid(row=2, column=1, sticky="ew", pady=2)

        ttk.Label(left, text="Subclass").grid(row=3, column=0, sticky="w")
        self.subclass_var = tk.StringVar(value="Imported")
        ttk.Entry(left, textvariable=self.subclass_var, width=44).grid(row=3, column=1, sticky="ew", pady=2)

        prop_box = ttk.LabelFrame(left, text="Add Property", padding=8)
        prop_box.grid(row=4, column=0, columnspan=2, sticky="nsew", pady=(8, 4))
        left.grid_columnconfigure(1, weight=1)

        self.prop_name = tk.StringVar()
        self.prop_value = tk.StringVar()
        self.prop_unit = tk.StringVar()
        self.prop_temp = tk.StringVar(value="23")

        ttk.Label(prop_box, text="Name *").grid(row=0, column=0, sticky="w")
        ttk.Entry(prop_box, textvariable=self.prop_name, width=26).grid(row=0, column=1, sticky="ew", pady=2)

        ttk.Label(prop_box, text="Value *").grid(row=1, column=0, sticky="w")
        ttk.Entry(prop_box, textvariable=self.prop_value, width=26).grid(row=1, column=1, sticky="ew", pady=2)

        ttk.Label(prop_box, text="Unit").grid(row=2, column=0, sticky="w")
        ttk.Entry(prop_box, textvariable=self.prop_unit, width=26).grid(row=2, column=1, sticky="ew", pady=2)

        ttk.Label(prop_box, text="Temperature (C)").grid(row=3, column=0, sticky="w")
        ttk.Entry(prop_box, textvariable=self.prop_temp, width=26).grid(row=3, column=1, sticky="ew", pady=2)

        ttk.Button(prop_box, text="Add Property", command=self.add_property).grid(row=4, column=0, columnspan=2, pady=(6, 2), sticky="ew")

        self.property_list = tk.Listbox(left, height=9)
        self.property_list.grid(row=5, column=0, columnspan=2, sticky="nsew", pady=4)
        left.grid_rowconfigure(5, weight=1)

        btns = ttk.Frame(left)
        btns.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        ttk.Button(btns, text="Remove Selected Property", command=self.remove_property).pack(side=tk.LEFT)
        ttk.Button(btns, text="Add Material to Queue", command=self.add_material).pack(side=tk.RIGHT)

        # Right side: queue + operations
        right = ttk.LabelFrame(frm, text="Material Queue / Output", padding=10)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.material_list = tk.Listbox(right)
        self.material_list.pack(fill=tk.BOTH, expand=True)

        ops = ttk.Frame(right)
        ops.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(ops, text="Import Materials from Text File", command=self.import_txt).pack(fill=tk.X, pady=2)
        ttk.Button(ops, text="Remove Selected Material", command=self.remove_material).pack(fill=tk.X, pady=2)
        ttk.Button(ops, text="Save XML", command=self.save_xml).pack(fill=tk.X, pady=2)
        ttk.Button(ops, text="Clear All", command=self.clear_all).pack(fill=tk.X, pady=2)

        help_text = (
            "Text import format:\n"
            "MATERIAL: Name\n"
            "DESCRIPTION: optional text\n"
            "CLASS: Fluids\n"
            "SUBCLASS: Gases\n"
            "PROPERTY: Density|1.16|kg m^-3|23\n"
            "PROPERTY: Thermal Conductivity|0.02582|W m^-1 C^-1|23\n"
            "END\n\n"
            "Use one MATERIAL block per material."
        )
        ttk.Label(right, text=help_text, justify=tk.LEFT).pack(fill=tk.X, pady=(10, 0))

    def add_property(self) -> None:
        name = self.prop_name.get().strip()
        value = self.prop_value.get().strip()
        unit = self.prop_unit.get().strip()
        temp = self.prop_temp.get().strip() or "23"
        if not name or not value:
            messagebox.showwarning("Missing data", "Property name and value are required.")
            return
        item = PropertyItem(name=name, value=value, unit=unit, temperature_c=temp)
        self.current_properties.append(item)
        self.property_list.insert(tk.END, f"{name} = {value} {unit} @ {temp}C")
        self.prop_name.set("")
        self.prop_value.set("")
        self.prop_unit.set("")

    def remove_property(self) -> None:
        sel = self.property_list.curselection()
        if not sel:
            return
        idx = sel[0]
        self.property_list.delete(idx)
        self.current_properties.pop(idx)

    def add_material(self) -> None:
        name = self.name_var.get().strip()
        if not name:
            messagebox.showwarning("Missing data", "Material name is required.")
            return
        mat = MaterialItem(
            name=name,
            description=self.description_var.get().strip(),
            category=self.class_var.get().strip() or "User Materials",
            subclass=self.subclass_var.get().strip() or "Imported",
            properties=list(self.current_properties),
        )
        self.materials.append(mat)
        self.material_list.insert(tk.END, f"{mat.name} ({len(mat.properties)} properties)")

        self.name_var.set("")
        self.description_var.set("")
        self.class_var.set("User Materials")
        self.subclass_var.set("Imported")
        self.current_properties.clear()
        self.property_list.delete(0, tk.END)

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
        self.current_properties.clear()
        self.property_list.delete(0, tk.END)

    def import_txt(self) -> None:
        path = filedialog.askopenfilename(
            title="Select text material list",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if not path:
            return

        try:
            parsed = parse_material_text(Path(path).read_text(encoding="utf-8"))
            self.materials.extend(parsed)
            for m in parsed:
                self.material_list.insert(tk.END, f"{m.name} ({len(m.properties)} properties)")

            messagebox.showinfo("Import complete", f"Imported {len(parsed)} material(s).")
        except Exception as exc:
            messagebox.showerror("Import failed", str(exc))

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
    parser = argparse.ArgumentParser(description="Build ANSYS EngineeringData XML from GUI or text input.")
    parser.add_argument("--from-file", dest="from_file", help="Text file with MATERIAL blocks.")
    parser.add_argument("--output", dest="output", help="Output XML path (required with --from-file).")
    args = parser.parse_args()

    if args.from_file:
        if not args.output:
            raise SystemExit("Error: --output is required when using --from-file.")
        text = Path(args.from_file).read_text(encoding="utf-8")
        mats = parse_material_text(text)
        write_xml(mats, Path(args.output))
        print(f"Wrote {len(mats)} material(s) to {args.output}")
        return

    root = tk.Tk()
    MaterialXMLBot(root)
    root.mainloop()


if __name__ == "__main__":
    main()
