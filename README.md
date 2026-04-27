# ANSYS Material XML Bot

A lightweight Python GUI tool that helps you build an ANSYS Mechanical Engineering Data XML file from:

1. **Manual input** (one material at a time), and/or
2. **Batch text file input** (many materials at once).

## Requirements

- Python 3.10+
- Tkinter (included in most standard Python installs)

## Run

```bash
python3 ansys_material_xml_bot.py
```

## What it does

- Prompts for required material fields in the GUI:
  - Material name
  - Description
  - Class
  - Subclass
  - Property rows (name, value, unit, temperature)
- Lets you add each material to an in-memory queue.
- Imports additional materials from a `.txt` file.
- Exports all queued materials to one ANSYS-style XML document that you can upload/import.

## Batch text file format

Use the provided `materials_input_example.txt` as a template.

```text
MATERIAL: Material Name
DESCRIPTION: Optional description
CLASS: Fluids
SUBCLASS: Gases
PROPERTY: Density|1.16|kg m^-3|23
PROPERTY: Dynamic Viscosity|1.832e-05|Pa s|23
END
```

Rules:
- `MATERIAL:` starts a new material block.
- `PROPERTY:` needs at least `name|value`.
- `unit` and `temperature` are optional (`temperature` defaults to 23 C).
- `END` closes the material block.

## Notes

- The tool generates an `EngineeringData` XML structure with `Material/BulkDetails/PropertyData` entries.
- Property IDs (`pr1`, `pr2`, …) and parameter IDs are generated automatically.
