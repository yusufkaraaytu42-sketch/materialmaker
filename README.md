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

## Optional CLI mode (no GUI)

If you already have a text file with materials, you can generate XML directly:

```bash
python3 ansys_material_xml_bot.py --from-file materials_input_example.txt --output materials.xml
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

If you see an error like `SyntaxError: unexpected token ':'` on a line such as
`MATERIAL: Aluminum 6061-T6`, that means the text file is being interpreted as code by the wrong tool.
Use this file as **input data** for this bot (GUI import or `--from-file` CLI mode), not as a Python script.

## Notes

- The tool generates an `EngineeringData` XML structure with `Material/BulkDetails/PropertyData` entries.
- Property IDs (`pr1`, `pr2`, …) and parameter IDs are generated automatically.
