import tkinter as tk
from tkinter import ttk, messagebox
import win32print
import win32ui
from PIL import Image, ImageDraw, ImageFont, ImageWin

class LabelPrinterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Label Printer Test")
        self.root.geometry("500x400")
        
        # Main frame
        main_frame = ttk.Frame(root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Printer selection
        ttk.Label(main_frame, text="Select Printer:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.printer_var = tk.StringVar()
        self.printer_combo = ttk.Combobox(main_frame, textvariable=self.printer_var, width=40)
        self.printer_combo.grid(row=0, column=1, pady=5, padx=5)
        
        ttk.Button(main_frame, text="Refresh", command=self.refresh_printers).grid(row=0, column=2, pady=5)
        
        # Test text input
        ttk.Label(main_frame, text="Test Text for Labels:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.text_entry = ttk.Entry(main_frame, width=43)
        self.text_entry.grid(row=1, column=1, columnspan=2, pady=5, padx=5)
        self.text_entry.insert(0, "TEST LABEL")
        
        # Print method selection
        ttk.Label(main_frame, text="Print Method:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.method_var = tk.StringVar(value="zpl")
        method_frame = ttk.Frame(main_frame)
        method_frame.grid(row=2, column=1, sticky=tk.W, pady=5)
        ttk.Radiobutton(method_frame, text="ZPL (Zebra)", variable=self.method_var, value="zpl").pack(side=tk.LEFT)
        ttk.Radiobutton(method_frame, text="TSPL (TSC)", variable=self.method_var, value="tspl").pack(side=tk.LEFT, padx=10)
        ttk.Radiobutton(method_frame, text="Windows Driver", variable=self.method_var, value="windows").pack(side=tk.LEFT)
        
        # Print button
        ttk.Button(main_frame, text="Print Test Labels", command=self.print_test, 
                   style="Accent.TButton").grid(row=3, column=0, columnspan=3, pady=20)
        
        # Status/Info text
        ttk.Label(main_frame, text="Status:").grid(row=4, column=0, sticky=tk.NW, pady=5)
        self.status_text = tk.Text(main_frame, height=10, width=50, wrap=tk.WORD)
        self.status_text.grid(row=4, column=1, columnspan=2, pady=5, padx=5)
        
        # Scrollbar for status
        scrollbar = ttk.Scrollbar(main_frame, orient=tk.VERTICAL, command=self.status_text.yview)
        scrollbar.grid(row=4, column=3, sticky=(tk.N, tk.S))
        self.status_text.config(yscrollcommand=scrollbar.set)
        
        # Initialize
        self.refresh_printers()
        self.log("Application started. Select a printer and click 'Print Test Labels'.")
    
    def log(self, message):
        self.status_text.insert(tk.END, message + "\n")
        self.status_text.see(tk.END)
        self.root.update()
    
    def refresh_printers(self):
        try:
            printers = [printer[2] for printer in win32print.EnumPrinters(2)]
            self.printer_combo['values'] = printers
            if printers:
                self.printer_combo.current(0)
                self.log(f"Found {len(printers)} printer(s)")
            else:
                self.log("No printers found!")
        except Exception as e:
            self.log(f"Error refreshing printers: {e}")
    
    def print_zpl(self, printer_name, text):
        """Print using ZPL (Zebra Programming Language)"""
        # Label size: 2.375" x 3.375" at 203 DPI = 482 x 685 dots
        # For 2-across, each label is the full width
        zpl = f"""^XA
^PW482
^LL685

^FO50,50^A0N,60,60^FDLabel 1^FS
^FO50,150^A0N,40,40^FD{text}^FS
^FO50,550^A0N,30,30^FDTest Print^FS

^XZ

^XA
^PW482
^LL685

^FO50,50^A0N,60,60^FDLabel 2^FS
^FO50,150^A0N,40,40^FD{text}^FS
^FO50,550^A0N,30,30^FDTest Print^FS

^XZ
"""
        
        hPrinter = win32print.OpenPrinter(printer_name)
        try:
            hJob = win32print.StartDocPrinter(hPrinter, 1, ("Test Label", None, "RAW"))
            win32print.StartPagePrinter(hPrinter)
            win32print.WritePrinter(hPrinter, zpl.encode())
            win32print.EndPagePrinter(hPrinter)
            win32print.EndDocPrinter(hPrinter)
            self.log("ZPL commands sent successfully")
        except Exception as e:
            raise e
        finally:
            win32print.ClosePrinter(hPrinter)
    
    def print_tspl(self, printer_name, text):
        """Print using TSPL (TSC Programming Language)"""
        # Label size: 2.375" x 3.375" at 203 DPI
        tspl = f"""SIZE 2.375,3.375
GAP 0.12,0
DIRECTION 1
REFERENCE 0,0
CLS

TEXT 50,50,"3",0,1,1,"Label 1"
TEXT 50,150,"2",0,1,1,"{text}"
TEXT 50,550,"1",0,1,1,"Test Print"
PRINT 1,1

CLS
TEXT 50,50,"3",0,1,1,"Label 2"
TEXT 50,150,"2",0,1,1,"{text}"
TEXT 50,550,"1",0,1,1,"Test Print"
PRINT 1,1
"""
        
        hPrinter = win32print.OpenPrinter(printer_name)
        try:
            hJob = win32print.StartDocPrinter(hPrinter, 1, ("Test Label", None, "RAW"))
            win32print.StartPagePrinter(hPrinter)
            win32print.WritePrinter(hPrinter, tspl.encode())
            win32print.EndPagePrinter(hPrinter)
            win32print.EndDocPrinter(hPrinter)
            self.log("TSPL commands sent successfully")
        except Exception as e:
            raise e
        finally:
            win32print.ClosePrinter(hPrinter)
    
    def print_windows(self, printer_name, text):
        """Print using Windows print driver"""
        # Create labels as images
        dpi = 203
        width = int(2.375 * dpi)
        height = int(3.375 * dpi)
        
        for label_num in range(1, 3):
            # Create image
            img = Image.new('RGB', (width, height), 'white')
            draw = ImageDraw.Draw(img)
            
            try:
                font_large = ImageFont.truetype("arial.ttf", 50)
                font_medium = ImageFont.truetype("arial.ttf", 35)
                font_small = ImageFont.truetype("arial.ttf", 25)
            except:
                font_large = ImageFont.load_default()
                font_medium = ImageFont.load_default()
                font_small = ImageFont.load_default()
            
            # Draw text
            draw.text((50, 50), f"Label {label_num}", fill='black', font=font_large)
            draw.text((50, 150), text, fill='black', font=font_medium)
            draw.text((50, height-100), "Test Print", fill='black', font=font_small)
            
            # Print via Windows
            hDC = win32ui.CreateDC()
            hDC.CreatePrinterDC(printer_name)
            hDC.StartDoc("Test Label")
            hDC.StartPage()
            
            dib = ImageWin.Dib(img)
            dib.draw(hDC.GetHandleOutput(), (0, 0, width, height))
            
            hDC.EndPage()
            hDC.EndDoc()
            hDC.DeleteDC()
        
        self.log("Printed via Windows driver")
    
    def print_test(self):
        printer_name = self.printer_var.get()
        text = self.text_entry.get()
        method = self.method_var.get()
        
        if not printer_name:
            messagebox.showerror("Error", "Please select a printer")
            return
        
        self.log(f"\n--- Starting print job ---")
        self.log(f"Printer: {printer_name}")
        self.log(f"Method: {method.upper()}")
        self.log(f"Text: {text}")
        
        try:
            if method == "zpl":
                self.print_zpl(printer_name, text)
            elif method == "tspl":
                self.print_tspl(printer_name, text)
            elif method == "windows":
                self.print_windows(printer_name, text)
            
            self.log("Print job completed successfully!")
            messagebox.showinfo("Success", "Test labels sent to printer!")
        except Exception as e:
            self.log(f"ERROR: {e}")
            messagebox.showerror("Print Error", f"Failed to print:\n{e}")

if __name__ == "__main__":
    root = tk.Tk()
    app = LabelPrinterApp(root)
    root.mainloop()