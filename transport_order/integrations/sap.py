import csv
import io
import re
import zipfile
from decimal import Decimal, InvalidOperation
from xml.etree import ElementTree as ET


class InputError(ValueError):
    pass


HEADERS = {
    "shipto": {
        "hu": ("handlingunit", "hu", "hunr", "hunumber"),
        "dn": ("erpdocument", "erp", "dn"),
        "document": ("outbounddeliveryorder", "document", "doc"),
        "shipTo": ("shipto", "building"),
        "condition": ("shippingcondition", "shipcond"),
        "externalId": ("externaldeliveryid", "scrap"),
        "bin": ("storagebin",),
        "changedOn": ("changedon", "date"),
        "changedAt": ("changedat", "time"),
    },
    "quantities": {
        "document": ("document", "doc", "outbounddeliveryorder"),
        "hu": ("handlingunit", "hu", "hunr", "hunumber"),
        "qty": ("quantity", "qty", "quantiy"),
    },
}
REQUIRED = {"shipto": ("hu", "dn", "document", "shipTo", "condition", "externalId"),
            "quantities": ("hu", "document", "qty")}


def identifier(value):
    value = str(value or "").strip().lstrip("\ufeff")
    if value.startswith("'"):
        value = value[1:]
    if re.fullmatch(r"\d+\.0", value):
        value = value[:-2]
    if re.fullmatch(r"[+-]?\d+(?:[.,]\d+)?[eE][+-]?\d+", value):
        raise InputError("An identifier is in scientific notation. Copy it as text from SAP.")
    return value


def quantity(value, decimal_mark="."):
    text = str(value).strip().replace("\u00a0", "").replace(" ", "")
    if not text or not re.fullmatch(r"[+\-]?[0-9.,]+", text):
        raise InputError(f"Invalid quantity: {value!s}")
    if decimal_mark == ",":
        if text.count(",") > 1 or not re.fullmatch(r"[+\-]?(?:\d+|\d{1,3}(?:\.\d{3})+)(?:,\d+)?", text):
            raise InputError(f"Quantity does not match decimal comma format: {value}")
        text = text.replace(".", "").replace(",", ".")
    else:
        if text.count(".") > 1 or not re.fullmatch(r"[+\-]?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?", text):
            raise InputError(f"Quantity does not match decimal point format: {value}")
        text = text.replace(",", "")
    try:
        result = Decimal(text)
    except InvalidOperation as exc:
        raise InputError(f"Invalid quantity: {value}") from exc
    if not result.is_finite() or result < 0 or result > Decimal("1e15"):
        raise InputError("Quantities must be between zero and 1,000,000,000,000,000.")
    return format(result, "f")


def read_xlsx(content):
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as book:
            if sum(info.file_size for info in book.infolist()) > 40_000_000:
                raise InputError("The uncompressed workbook is too large (40 MB maximum).")
            shared = []
            if "xl/sharedStrings.xml" in book.namelist():
                root = ET.fromstring(book.read("xl/sharedStrings.xml"))
                shared = ["".join(node.itertext()) for node in root.findall("m:si", ns)]
            wb = ET.fromstring(book.read("xl/workbook.xml"))
            sheet = wb.find("m:sheets/m:sheet", ns)
            rel_id = sheet.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
            rels = ET.fromstring(book.read("xl/_rels/workbook.xml.rels"))
            target = next(r.get("Target") for r in rels if r.get("Id") == rel_id)
            path = target.lstrip("/") if target.startswith("/") else "xl/" + target
            root = ET.fromstring(book.read(path))
            rows = []
            for row in root.findall("m:sheetData/m:row", ns):
                cells = {}
                for cell in row.findall("m:c", ns):
                    col = re.match(r"[A-Z]+", cell.get("r", "A1"))[0]
                    index = 0
                    for c in col:
                        index = index * 26 + ord(c) - 64
                    if index > 100:
                        raise InputError("SAP inputs are limited to 100 columns.")
                    if cell.find("m:f", ns) is not None:
                        raise InputError("Import a values-only SAP export, without formulas.")
                    value = cell.findtext("m:v", "", ns)
                    if cell.get("t") == "s":
                        value = shared[int(value)]
                    elif cell.get("t") == "inlineStr":
                        value = "".join(cell.find("m:is", ns).itertext())
                    cells[index - 1] = value
                rows.append([cells.get(i, "") for i in range(max(cells, default=-1) + 1)])
            return rows
    except (zipfile.BadZipFile, ET.ParseError, KeyError, ValueError, IndexError, StopIteration, AttributeError) as exc:
        if isinstance(exc, InputError):
            raise
        raise InputError("Could not read this XLSX file. Use a standard SAP export or paste the table.") from exc


def read_text(text):
    text = text.lstrip("\ufeff")
    nonempty = [line for line in text.splitlines() if line.strip()]
    if not nonempty:
        raise InputError("Paste a table including its header row.")
    delimiter = "\t" if "\t" in text else ";" if ";" in nonempty[0] else "|" if "|" in nonempty[0] else ","
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    rows = []
    for row in reader:
        if delimiter == "|":
            if row and not row[0].strip():
                row = row[1:]
            if row and not row[-1].strip():
                row = row[:-1]
        if any(c.strip() for c in row) and not all(re.fullmatch(r"[-+ =]*", c) for c in row):
            rows.append(row)
    return rows


def parse_table(kind, text="", content=None, decimal_mark="."):
    if kind not in HEADERS:
        raise InputError("Unknown SAP table type.")
    if decimal_mark not in (".", ","):
        raise InputError("Choose a decimal point or comma.")
    rows = read_xlsx(content) if content is not None else read_text(text)
    if not rows or len(rows) > 50_001:
        raise InputError("Use a header and between 1 and 50,000 data rows.")
    labels = [re.sub(r"[^a-z0-9]", "", str(c).lower()) for c in rows[0]]
    mapping = {}
    for field, aliases in HEADERS[kind].items():
        matches = [i for i, label in enumerate(labels) if label in aliases]
        if len(matches) > 1:
            raise InputError(f"Multiple columns match {field}. Keep one column for this field.")
        if matches:
            mapping[field] = matches[0]
    missing = [HEADERS[kind][f][0] for f in REQUIRED[kind] if f not in mapping]
    if missing:
        raise InputError("Missing columns: " + ", ".join(missing) + ". Include the original SAP headers.")
    result, errors, warnings, seen = [], [], [], set()
    for number, row in enumerate(rows[1:], 2):
        if not any(str(c).strip() for c in row):
            continue
        if [re.sub(r"[^a-z0-9]", "", str(c).lower()) for c in row] == labels:
            warnings.append(f"Row {number}: repeated header skipped.")
            continue
        try:
            entry = {field: identifier(row[i] if i < len(row) else "") for field, i in mapping.items()}
            entry["row"] = number
            if not entry["hu"] or not entry.get("document"):
                raise InputError("HU and document are required.")
            if kind == "quantities":
                entry["qty"] = quantity(entry["qty"], "." if content is not None else decimal_mark)
                key = (entry["hu"], entry["document"], entry["qty"])
                if key in seen:
                    warnings.append(f"Row {number}: identical quantity record retained; it may be another item. Check the source.")
            else:
                if not entry["dn"] or not entry["shipTo"]:
                    raise InputError("ERP Document and Ship-To are required.")
                entry["condition"] = entry["condition"].upper()
                key = tuple((k, v) for k, v in entry.items() if k != "row")
                if key in seen:
                    warnings.append(f"Row {number}: identical Ship-to record skipped.")
                    continue
            seen.add(key)
            result.append(entry)
        except InputError as exc:
            errors.append({"row": number, "message": str(exc)})
    if not result and not errors:
        raise InputError("No data rows were found.")
    if kind == "shipto":
        by_hu = {}
        for entry in result:
            by_hu.setdefault(entry["hu"], set()).add(tuple(entry.get(k, "") for k in ("document", "dn", "shipTo", "condition", "externalId")))
        for hu, values in by_hu.items():
            if len(values) > 1:
                errors.append({"hu": hu, "message": "Conflicting records for this HU. Correct the source before applying."})
    return {"kind": kind, "rows": result, "count": len(result),
            "uniqueHus": len({r["hu"] for r in result}), "errors": errors,
            "warnings": warnings, "headers": rows[0]}


class SapPasteProvider:
    id = "sap"
    label = "SAP tables"
    available = True
    description = "Paste or import Ship-to and Quantities exports."
    parse = staticmethod(parse_table)
