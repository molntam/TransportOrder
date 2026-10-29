using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.Drawing.Printing;
using System.IO;
using System.Web.Script.Serialization;

public class PrintLocation { public string building; public string department; public string shipTo; }
public class PrintColumn { public string key; public string label; public float weight; }
public class PrintModel {
    public string kind; public string id; public int revision; public string title; public string at;
    public string preparedBy; public PrintLocation origin; public PrintLocation destination;
    public string status; public PrintColumn[] columns; public string[][] rows; public string[][] summary;
    public string remarks; public string contact; public bool obsolete; public bool qrPlaceholder;
}
public class PrintRequest { public PrintModel document; public string printer; public int copies; public string outputPath; }

public static class TransportOrderPrinter {
    private static readonly JavaScriptSerializer Json = new JavaScriptSerializer { MaxJsonLength = 20000000 };

    public static string Run(string input, string action) {
        if (action == "validate") return Json.Serialize(new { status = "validated" });
        if (action == "list") {
            List<string> names = new List<string>();
            foreach (string name in PrinterSettings.InstalledPrinters) names.Add(name);
            names.Sort(StringComparer.CurrentCultureIgnoreCase);
            PrinterSettings defaults = new PrinterSettings();
            return Json.Serialize(new { supported = true, printers = names, defaultPrinter = defaults.IsValid ? defaults.PrinterName : "" });
        }
        PrintRequest request = Json.Deserialize<PrintRequest>(input);
        if (request == null || request.document == null || request.copies < 1 || request.copies > 5)
            throw new ArgumentException("Invalid print request.");
        if (action == "render") {
            using (Bitmap bitmap = new Bitmap(827, 1169)) {
                bitmap.SetResolution(100, 100);
                using (Graphics graphics = Graphics.FromImage(bitmap)) {
                    graphics.PageUnit = GraphicsUnit.Display;
                    PageLayout layout = new PageLayout(request.document, graphics, new RectangleF(50, 50, 727, 1069));
                    graphics.Clear(Color.White);
                    layout.Draw(graphics, 0, 1, request.copies);
                    bitmap.Save(request.outputPath, ImageFormat.Png);
                    return Json.Serialize(new { status = "rendered", pages = layout.Count, copies = request.copies });
                }
            }
        }
        if (action != "print") throw new ArgumentException("Unknown printer action.");
        using (PrintDocument document = new PrintDocument()) {
            if (!String.IsNullOrWhiteSpace(request.printer)) document.PrinterSettings.PrinterName = request.printer;
            if (!document.PrinterSettings.IsValid) throw new InvalidOperationException("The selected Windows printer is unavailable. Check Settings and the Windows print queue.");
            string printer = document.PrinterSettings.PrinterName;
            string output = null;
            if (printer.IndexOf("Microsoft Print to PDF", StringComparison.OrdinalIgnoreCase) >= 0 || printer.IndexOf("Microsoft XPS Document", StringComparison.OrdinalIgnoreCase) >= 0) {
                output = printer.IndexOf("XPS", StringComparison.OrdinalIgnoreCase) >= 0 ? Path.ChangeExtension(request.outputPath, ".xps") : request.outputPath;
                document.PrinterSettings.PrintToFile = true;
                document.PrinterSettings.PrintFileName = output;
            }
            document.DocumentName = request.document.id + " - revision " + request.document.revision;
            document.PrintController = new StandardPrintController();
            document.PrinterSettings.Copies = 1;
            if (document.PrinterSettings.CanDuplex) document.PrinterSettings.Duplex = Duplex.Simplex;
            document.DefaultPageSettings.Landscape = false;
            document.DefaultPageSettings.Margins = new Margins(50, 50, 50, 50);
            PaperSize a4 = null;
            foreach (PaperSize paper in document.PrinterSettings.PaperSizes) if (paper.Kind == PaperKind.A4) { a4 = paper; break; }
            document.DefaultPageSettings.PaperSize = a4 ?? new PaperSize("A4", 827, 1169);
            PageLayout layout = null;
            int page = 0;
            document.PrintPage += delegate(object sender, PrintPageEventArgs args) {
                args.Graphics.PageUnit = GraphicsUnit.Display;
                args.Graphics.TranslateTransform(-args.PageSettings.HardMarginX, -args.PageSettings.HardMarginY);
                if (layout == null) layout = new PageLayout(request.document, args.Graphics, args.MarginBounds);
                layout.Draw(args.Graphics, page % layout.Count, page / layout.Count + 1, request.copies);
                page++;
                args.HasMorePages = page < layout.Count * request.copies;
            };
            document.Print();
            return Json.Serialize(new { status = "submitted", printer = printer, copies = request.copies, pagesPerCopy = layout == null ? 0 : layout.Count, outputPath = output });
        }
    }

    private class Mark {
        public RectangleF rectangle; public string text; public float size; public bool bold;
        public bool box; public bool fill; public bool dashed; public bool centered; public Color color;
    }

    private class PageLayout {
        private readonly PrintModel model;
        private readonly Graphics measure;
        private readonly RectangleF bounds;
        private readonly List<List<Mark>> pages = new List<List<Mark>>();
        private List<Mark> current;
        private float y;
        private float Bottom { get { return bounds.Bottom - 28; } }
        public int Count { get { return pages.Count; } }
        private static readonly Color Navy = Color.FromArgb(0, 0, 102);

        public PageLayout(PrintModel model, Graphics graphics, RectangleF bounds) {
            this.model = model; this.measure = graphics; this.bounds = bounds;
            NewPage();
            if (model.obsolete) TextBlock("SUPERSEDED DOCUMENT - check the current revision before use.", 11, true);
            Addresses();
            TextBlock(model.status, 10, true);
            if (model.summary != null && model.summary.Length > 0) {
                Table("Delivery summary", new PrintColumn[] {
                    new PrintColumn { label = "DN", weight = 1.4f },
                    new PrintColumn { label = "HUs", weight = .6f },
                    new PrintColumn { label = "Quantity total (source units)", weight = 2f }
                }, model.summary);
            }
            Table("Handling units & deliveries", model.columns, model.rows);
            if (!String.IsNullOrWhiteSpace(model.remarks)) { TextBlock("Remarks", 12, true); TextBlock(model.remarks, 10.5f, false); }
            if (!String.IsNullOrWhiteSpace(model.contact)) TextBlock(model.contact, 9.5f, false);
            if (model.qrPlaceholder) {
                Ensure(108);
                Box(bounds.Left, y + 8, 90, 90, false, true);
                Text("QR CODE", bounds.Left + 5, y + 26, 80, 20, 11, true, true, Navy);
                Text("Tracking to be", bounds.Left + 5, y + 50, 80, 15, 8.5f, false, true, Color.Black);
                Text("connected", bounds.Left + 5, y + 65, 80, 15, 8.5f, false, true, Color.Black);
                y += 108;
            }
            Ensure(62); y += 15;
            TextBlock("Received / transported by: ____________________", 10, false);
            TextBlock("Name + signature: __________________________", 10, false);
        }

        private void NewPage() {
            current = new List<Mark>(); pages.Add(current);
            Text(model.title, bounds.Left, bounds.Top, bounds.Width * .58f, 34, 20, true, false, Navy);
            Text(model.id + " / Rev " + model.revision, bounds.Left, bounds.Top + 36, bounds.Width, 18, 10, true, false, Color.Black);
            Text(model.at, bounds.Left, bounds.Top + 55, bounds.Width, 16, 9, false, false, Color.DimGray);
            y = bounds.Top + 79;
        }

        private void Ensure(float height) { if (y + height > Bottom) NewPage(); }

        private void Text(string text, float x, float top, float width, float height, float size, bool bold, bool centered, Color color) {
            current.Add(new Mark { text = text ?? "", rectangle = new RectangleF(x, top, width, height), size = size, bold = bold, centered = centered, color = color });
        }

        private void Box(float x, float top, float width, float height, bool fill, bool dashed) {
            current.Add(new Mark { box = true, fill = fill, dashed = dashed, rectangle = new RectangleF(x, top, width, height) });
        }

        private List<string> Wrap(string value, float width, float size, bool bold) {
            List<string> output = new List<string>();
            using (Font font = new Font("Segoe UI", size, bold ? FontStyle.Bold : FontStyle.Regular)) {
                foreach (string paragraph in (value ?? "").Replace("\r", "").Split('\n')) {
                    string rest = paragraph;
                    if (rest.Length == 0) output.Add("");
                    while (rest.Length > 0) {
                        int low = 1, high = rest.Length, fit = 1;
                        while (low <= high) {
                            int mid = (low + high) / 2;
                            if (measure.MeasureString(rest.Substring(0, mid), font).Width <= width) { fit = mid; low = mid + 1; }
                            else high = mid - 1;
                        }
                        if (fit < rest.Length) {
                            int space = rest.LastIndexOf(' ', fit - 1, fit);
                            if (space > fit / 2) fit = space + 1;
                        }
                        output.Add(rest.Substring(0, fit).TrimEnd()); rest = rest.Substring(fit).TrimStart();
                    }
                }
            }
            return output;
        }

        private void TextBlock(string value, float size, bool bold) {
            float height = size * 1.9f;
            foreach (string line in Wrap(value, bounds.Width - 4, size, bold)) {
                Ensure(height); Text(line, bounds.Left, y, bounds.Width, height, size, bold, false, bold ? Navy : Color.Black); y += height;
            }
            y += 5;
        }

        private void Addresses() {
            float width = (bounds.Width - 18) / 2;
            PrintLocation[] locations = new PrintLocation[] { model.origin, model.destination };
            List<string>[] lines = new List<string>[2];
            for (int i = 0; i < 2; i++) lines[i] = Wrap(locations[i].building + "\n" + locations[i].department + "\n" + locations[i].shipTo, width - 18, 10, false);
            float height = Math.Max(lines[0].Count, lines[1].Count) * 19 + 38;
            Ensure(height);
            for (int i = 0; i < 2; i++) {
                float x = bounds.Left + i * (width + 18);
                Box(x, y, width, height, false, false);
                Text(i == 0 ? "FROM" : "TO", x + 9, y + 8, width - 18, 18, 9, true, false, Navy);
                for (int j = 0; j < lines[i].Count; j++) Text(lines[i][j], x + 9, y + 28 + j * 19, width - 18, 19, 10, false, false, Color.Black);
            }
            y += height + 15;
            TextBlock("Prepared by: " + model.preparedBy, 9, false);
        }

        private void Table(string title, PrintColumn[] columns, string[][] rows) {
            if (rows == null || rows.Length == 0) return;
            float total = 0; foreach (PrintColumn c in columns) total += c.weight;
            float[] widths = new float[columns.Length];
            for (int i = 0; i < columns.Length; i++) widths[i] = bounds.Width * columns[i].weight / total;
            TextBlock(title, 12, true);
            Header(columns, widths);
            foreach (string[] row in rows) {
                List<string>[] cells = new List<string>[columns.Length];
                int length = 1;
                for (int i = 0; i < cells.Length; i++) { cells[i] = Wrap(i < row.Length ? row[i] : "", widths[i] - 12, 10, false); length = Math.Max(length, cells[i].Count); }
                int start = 0;
                while (start < length) {
                    int capacity = (int)((Bottom - y - 10) / 19);
                    if (capacity < 1) { NewPage(); TextBlock(title + " (continued)", 12, true); Header(columns, widths); capacity = (int)((Bottom - y - 10) / 19); }
                    int count = Math.Min(length - start, capacity);
                    float height = count * 19 + 10, x = bounds.Left;
                    for (int i = 0; i < cells.Length; i++) {
                        Box(x, y, widths[i], height, false, false);
                        for (int j = 0; j < count && start + j < cells[i].Count; j++) Text(cells[i][start + j], x + 6, y + 5 + j * 19, widths[i] - 12, 19, 10, false, false, Color.Black);
                        x += widths[i];
                    }
                    y += height; start += count;
                }
            }
            y += 18;
        }

        private void Header(PrintColumn[] columns, float[] widths) {
            List<string>[] lines = new List<string>[columns.Length]; int length = 1;
            for (int i = 0; i < columns.Length; i++) { lines[i] = Wrap(columns[i].label, widths[i] - 12, 9, true); length = Math.Max(length, lines[i].Count); }
            float height = length * 17 + 10;
            Ensure(height + 29); float x = bounds.Left;
            for (int i = 0; i < columns.Length; i++) {
                Box(x, y, widths[i], height, true, false);
                for (int j = 0; j < lines[i].Count; j++) Text(lines[i][j], x + 6, y + 5 + j * 17, widths[i] - 12, 17, 9, true, false, Navy);
                x += widths[i];
            }
            y += height;
        }

        public void Draw(Graphics graphics, int page, int copy, int copies) {
            foreach (Mark mark in pages[page]) {
                if (mark.box) {
                    if (mark.fill) using (Brush fill = new SolidBrush(Color.FromArgb(237, 240, 250))) graphics.FillRectangle(fill, mark.rectangle);
                    using (Pen pen = new Pen(Color.FromArgb(160, 173, 195), .7f)) {
                        if (mark.dashed) pen.DashStyle = DashStyle.Dash;
                        graphics.DrawRectangle(pen, mark.rectangle.X, mark.rectangle.Y, mark.rectangle.Width, mark.rectangle.Height);
                    }
                } else using (Font font = new Font("Segoe UI", mark.size, mark.bold ? FontStyle.Bold : FontStyle.Regular))
                using (Brush brush = new SolidBrush(mark.color))
                using (StringFormat format = new StringFormat()) {
                    format.FormatFlags = StringFormatFlags.NoWrap;
                    if (mark.centered) format.Alignment = StringAlignment.Center;
                    graphics.DrawString(mark.text, font, brush, mark.rectangle, format);
                }
            }
            using (Font font = new Font("Segoe UI", 8.5f))
                graphics.DrawString(model.id + " / Rev " + model.revision + " - Page " + (page + 1) + " of " + Count + " - Copy " + copy + " of " + copies, font, Brushes.DimGray, bounds.Left, bounds.Bottom - 12);
        }
    }
}
