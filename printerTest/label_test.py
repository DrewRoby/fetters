# label_printer.py
"""
Cross-platform label printer module for 2-across thermal label printers.
Compatible with Zebra (ZPL) and TSC (TSPL) printers.
Develops on Linux, runs on Windows.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import platform
from typing import Optional, Callable, List, Dict
import json

# Platform-specific imports
WINDOWS_AVAILABLE = False
if platform.system() == 'Windows':
    try:
        import win32print
        import win32ui
        from PIL import Image, ImageDraw, ImageFont, ImageWin
        WINDOWS_AVAILABLE = True
    except ImportError:
        print("Warning: pywin32 or PIL not available. Printer functions disabled.")
else:
    print("Running on non-Windows platform. Printer functions will be simulated.")


class LabelPrinterError(Exception):
    """Custom exception for printer-related errors"""
    pass


class LabelPrinter:
    """
    Core printer functionality - can be used standalone or with GUI.

    Example usage:
        printer = LabelPrinter()
        printer.set_printer("ZDesigner ZD421-203dpi")
        printer.print_labels(["Label 1 text", "Label 2 text"], method="zpl")
    """

    # Label dimensions at 203 DPI
    LABEL_WIDTH_INCHES = 2.375
    LABEL_HEIGHT_INCHES = 3.375
    DPI = 203

    def __init__(self, log_callback: Optional[Callable[[str], None]] = None):
        """
        Initialize the printer.

        Args:
            log_callback: Optional function to call with log messages
        """
        self.current_printer: Optional[str] = None
        self.log_callback = log_callback or print

    def log(self, message: str):
        """Log a message via the callback"""
        self.log_callback(message)

    def get_available_printers(self) -> List[str]:
        """
        Get list of available printers.

        Returns:
            List of printer names
        """
        if not WINDOWS_AVAILABLE:
            self.log("Simulated: Would enumerate Windows printers")
            return ["[SIMULATED] Generic Printer", "[SIMULATED] Zebra ZD421"]

        try:
            printers = [printer[2] for printer in win32print.EnumPrinters(2)]
            return printers
        except Exception as e:
            raise LabelPrinterError(f"Failed to enumerate printers: {e}")

    def set_printer(self, printer_name: str):
        """
        Set the active printer.

        Args:
            printer_name: Name of the printer to use
        """
        available = self.get_available_printers()
        if printer_name not in available:
            raise LabelPrinterError(f"Printer '{printer_name}' not found")

        self.current_printer = printer_name
        self.log(f"Printer set to: {printer_name}")

    def print_labels(self, texts: List[str], method: str = "zpl") -> bool:
        """
        Print labels with the specified text.

        Args:
            texts: List of text strings (one per label)
            method: Print method - "zpl", "tspl", or "windows"

        Returns:
            True if successful

        Raises:
            LabelPrinterError: If printing fails
        """
        if not self.current_printer:
            raise LabelPrinterError("No printer selected")

        if not WINDOWS_AVAILABLE:
            self.log(f"SIMULATED: Would print {len(texts)} label(s) using {method.upper()}")
            for i, text in enumerate(texts, 1):
                self.log(f"  Label {i}: {text}")
            return True

        try:
            if method == "zpl":
                return self._print_zpl(texts)
            elif method == "tspl":
                return self._print_tspl(texts)
            elif method == "windows":
                return self._print_windows(texts)
            else:
                raise LabelPrinterError(f"Unknown print method: {method}")
        except Exception as e:
            raise LabelPrinterError(f"Print failed: {e}")

    def _print_zpl(self, texts: List[str]) -> bool:
        """Print using ZPL (Zebra Programming Language)"""
        width_dots = int(self.LABEL_WIDTH_INCHES * self.DPI)
        height_dots = int(self.LABEL_HEIGHT_INCHES * self.DPI)

        zpl_commands = []
        for i, text in enumerate(texts, 1):
            zpl = f"""^XA
^PW{width_dots}
^LL{height_dots}
^FO50,50^A0N,60,60^FDLabel {i}^FS
^FO50,150^A0N,40,40^FD{text}^FS
^FO50,{height_dots-100}^A0N,30,30^FDPrinted via ZPL^FS
^XZ
"""
            zpl_commands.append(zpl)

        full_zpl = "\n".join(zpl_commands)

        hPrinter = win32print.OpenPrinter(self.current_printer)
        try:
            hJob = win32print.StartDocPrinter(hPrinter, 1, ("Label Print", None, "RAW"))
            win32print.StartPagePrinter(hPrinter)
            win32print.WritePrinter(hPrinter, full_zpl.encode())
            win32print.EndPagePrinter(hPrinter)
            win32print.EndDocPrinter(hPrinter)
            self.log(f"Successfully sent {len(texts)} label(s) via ZPL")
            return True
        finally:
            win32print.ClosePrinter(hPrinter)

    def _print_tspl(self, texts: List[str]) -> bool:
        """Print using TSPL (TSC Programming Language)"""
        tspl_commands = []
        for i, text in enumerate(texts, 1):
            tspl = f"""SIZE {self.LABEL_WIDTH_INCHES},{self.LABEL_HEIGHT_INCHES}
GAP 0.12,0
DIRECTION 1
REFERENCE 0,0
CLS
TEXT 50,50,"3",0,1,1,"Label {i}"
TEXT 50,150,"2",0,1,1,"{text}"
TEXT 50,550,"1",0,1,1,"Printed via TSPL"
PRINT 1,1
"""
            tspl_commands.append(tspl)

        full_tspl = "\n".join(tspl_commands)

        hPrinter = win32print.OpenPrinter(self.current_printer)
        try:
            hJob = win32print.StartDocPrinter(hPrinter, 1, ("Label Print", None, "RAW"))
            win32print.StartPagePrinter(hPrinter)
            win32print.WritePrinter(hPrinter, full_tspl.encode())
            win32print.EndPagePrinter(hPrinter)
            win32print.EndDocPrinter(hPrinter)
            self.log(f"Successfully sent {len(texts)} label(s) via TSPL")
            return True
        finally:
            win32print.ClosePrinter(hPrinter)

    def _print_windows(self, texts: List[str]) -> bool:
        """Print using Windows print driver"""
        width_dots = int(self.LABEL_WIDTH_INCHES * self.DPI)
        height_dots = int(self.LABEL_HEIGHT_INCHES * self.DPI)

        for i, text in enumerate(texts, 1):
            img = Image.new('RGB', (width_dots, height_dots), 'white')
            draw = ImageDraw.Draw(img)

            try:
                font_large = ImageFont.truetype("arial.ttf", 50)
                font_medium = ImageFont.truetype("arial.ttf", 35)
                font_small = ImageFont.truetype("arial.ttf", 25)
            except:
                font_large = ImageFont.load_default()
                font_medium = ImageFont.load_default()
                font_small = ImageFont.load_default()

            draw.text((50, 50), f"Label {i}", fill='black', font=font_large)
            draw.text((50, 150), text, fill='black', font=font_medium)
            draw.text((50, height_dots-100), "Printed via Windows", fill='black', font=font_small)

            hDC = win32ui.CreateDC()
            hDC.CreatePrinterDC(self.current_printer)
            hDC.StartDoc("Label Print")
            hDC.StartPage()

            dib = ImageWin.Dib(img)
            dib.draw(hDC.GetHandleOutput(), (0, 0, width_dots, height_dots))

            hDC.EndPage()
            hDC.EndDoc()
            hDC.DeleteDC()

        self.log(f"Successfully printed {len(texts)} label(s) via Windows driver")
        return True


class LabelPrinterGUI:
    """
    GUI interface for the label printer.
    Can be embedded in a larger application or run standalone.
    """

    def __init__(self, parent: Optional[tk.Widget] = None, printer: Optional[LabelPrinter] = None):
        """
        Initialize the GUI.

        Args:
            parent: Parent widget (None for standalone window)
            printer: LabelPrinter instance (creates new one if None)
        """
        if parent is None:
            self.root = tk.Tk()
            self.root.title("Label Printer")
            self.is_standalone = True
        else:
            self.root = parent
            self.is_standalone = False

        self.printer = printer or LabelPrinter(log_callback=self.log)
        self.setup_ui()

    def setup_ui(self):
        """Create the user interface"""
        # Main frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # Printer selection
        ttk.Label(main_frame, text="Select Printer:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.printer_var = tk.StringVar()
        self.printer_combo = ttk.Combobox(main_frame, textvariable=self.printer_var, width=40)
        self.printer_combo.grid(row=0, column=1, pady=5, padx=5)
        self.printer_combo.bind('<<ComboboxSelected>>', self.on_printer_selected)

        ttk.Button(main_frame, text="Refresh", command=self.refresh_printers).grid(row=0, column=2, pady=5)

        # Test text input
        ttk.Label(main_frame, text="Test Text:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.text_entry = ttk.Entry(main_frame, width=43)
        self.text_entry.grid(row=1, column=1, columnspan=2, pady=5, padx=5)
        self.text_entry.insert(0, "TEST LABEL")

        # Number of labels
        ttk.Label(main_frame, text="Number of Labels:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.num_labels_var = tk.IntVar(value=2)
        num_labels_spin = ttk.Spinbox(main_frame, from_=1, to=10, textvariable=self.num_labels_var, width=10)
        num_labels_spin.grid(row=2, column=1, sticky=tk.W, pady=5, padx=5)

        # Print method selection
        ttk.Label(main_frame, text="Print Method:").grid(row=3, column=0, sticky=tk.W, pady=5)
        self.method_var = tk.StringVar(value="zpl")
        method_frame = ttk.Frame(main_frame)
        method_frame.grid(row=3, column=1, sticky=tk.W, pady=5)
        ttk.Radiobutton(method_frame, text="ZPL (Zebra)", variable=self.method_var, value="zpl").pack(side=tk.LEFT)
        ttk.Radiobutton(method_frame, text="TSPL (TSC)", variable=self.method_var, value="tspl").pack(side=tk.LEFT, padx=10)
        ttk.Radiobutton(method_frame, text="Windows Driver", variable=self.method_var, value="windows").pack(side=tk.LEFT)

        # Print button
        ttk.Button(main_frame, text="Print Test Labels", command=self.print_test).grid(
            row=4, column=0, columnspan=3, pady=20
        )

        # Status/Info text
        ttk.Label(main_frame, text="Status:").grid(row=5, column=0, sticky=tk.NW, pady=5)
        self.status_text = tk.Text(main_frame, height=10, width=50, wrap=tk.WORD)
        self.status_text.grid(row=5, column=1, columnspan=2, pady=5, padx=5)

        # Scrollbar for status
        scrollbar = ttk.Scrollbar(main_frame, orient=tk.VERTICAL, command=self.status_text.yview)
        scrollbar.grid(row=5, column=3, sticky=(tk.N, tk.S))
        self.status_text.config(yscrollcommand=scrollbar.set)

        # Initialize
        self.refresh_printers()
        self.log("Label Printer initialized")
        if not WINDOWS_AVAILABLE:
            self.log("WARNING: Running in simulation mode (non-Windows platform)")

    def log(self, message: str):
        """Add a message to the status log"""
        self.status_text.insert(tk.END, message + "\n")
        self.status_text.see(tk.END)
        if self.is_standalone:
            self.root.update()

    def refresh_printers(self):
        """Refresh the list of available printers"""
        try:
            printers = self.printer.get_available_printers()
            self.printer_combo['values'] = printers
            if printers:
                self.printer_combo.current(0)
                self.printer.set_printer(printers[0])
                self.log(f"Found {len(printers)} printer(s)")
        except LabelPrinterError as e:
            self.log(f"Error: {e}")

    def on_printer_selected(self, event=None):
        """Handle printer selection change"""
        printer_name = self.printer_var.get()
        if printer_name:
            try:
                self.printer.set_printer(printer_name)
            except LabelPrinterError as e:
                self.log(f"Error: {e}")

    def print_test(self):
        """Print test labels"""
        text = self.text_entry.get()
        num_labels = self.num_labels_var.get()
        method = self.method_var.get()

        self.log(f"\n--- Starting print job ---")
        self.log(f"Method: {method.upper()}")
        self.log(f"Labels: {num_labels}")

        try:
            texts = [text] * num_labels
            self.printer.print_labels(texts, method=method)
            self.log("Print job completed!")
            if WINDOWS_AVAILABLE:
                messagebox.showinfo("Success", f"Sent {num_labels} label(s) to printer!")
        except LabelPrinterError as e:
            self.log(f"ERROR: {e}")
            if WINDOWS_AVAILABLE:
                messagebox.showerror("Print Error", str(e))

    def run(self):
        """Run the GUI (only for standalone mode)"""
        if self.is_standalone:
            self.root.mainloop()


# API functions for easy integration
def create_printer(log_callback: Optional[Callable[[str], None]] = None) -> LabelPrinter:
    """
    Create a LabelPrinter instance.

    Args:
        log_callback: Optional function to receive log messages

    Returns:
        LabelPrinter instance
    """
    return LabelPrinter(log_callback=log_callback)


def create_printer_gui(parent: Optional[tk.Widget] = None,
                       printer: Optional[LabelPrinter] = None) -> LabelPrinterGUI:
    """
    Create a printer GUI.

    Args:
        parent: Parent widget (None for standalone window)
        printer: LabelPrinter instance to use

    Returns:
        LabelPrinterGUI instance
    """
    return LabelPrinterGUI(parent=parent, printer=printer)


# Standalone execution
if __name__ == "__main__":
    gui = create_printer_gui()
    gui.run()