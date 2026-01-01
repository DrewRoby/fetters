"""
Consignment Shop Management - Desktop GUI

A simple, clean Tkinter interface for managing consignment inventory,
consignors, sales, and payouts.
"""

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Optional, Callable

from core import (
    ItemStatus, Address, Item, Consignor, ConsignmentStore
)
from storage import ConsignmentStorage
from printing import TagPrinter, PrinterConfig, TagSize


class App(tk.Tk):
    """Main application window."""
    
    def __init__(self, db_path: str = "consignment.db"):
        super().__init__()
        
        self.title("Consignment Shop Manager")
        self.geometry("1000x650")
        self.minsize(800, 500)
        
        # Load or create store
        self.storage = ConsignmentStorage(db_path)
        self.store = self.storage.load_store()
        
        # Printer configuration
        self.printer_config = PrinterConfig(
            store_name="Consignment Shop",
            preview_only=False,  # Set True for testing without printer
            tag_size=TagSize.MEDIUM
        )
        self.printer = TagPrinter(self.printer_config)
        
        # Configure grid
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        
        # Create notebook (tabs)
        self.notebook = ttk.Notebook(self)
        self.notebook.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        
        # Create tab frames
        self.items_tab = ItemsTab(self.notebook, self)
        self.consignors_tab = ConsignorsTab(self.notebook, self)
        self.sales_tab = SalesTab(self.notebook, self)
        self.payouts_tab = PayoutsTab(self.notebook, self)
        
        self.notebook.add(self.items_tab, text="  Items  ")
        self.notebook.add(self.consignors_tab, text="  Consignors  ")
        self.notebook.add(self.sales_tab, text="  Sales  ")
        self.notebook.add(self.payouts_tab, text="  Payouts  ")
        
        # Status bar
        self.status_var = tk.StringVar(value="Ready")
        self.status_bar = ttk.Label(self, textvariable=self.status_var, relief="sunken")
        self.status_bar.grid(row=1, column=0, sticky="ew", padx=5, pady=(0, 5))
        
        # Bind tab change to refresh
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)
        
        # Save on close
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        
        # Initial refresh
        self.refresh_all()
    
    def _on_tab_changed(self, event):
        """Refresh data when switching tabs."""
        self.refresh_all()
    
    def _on_close(self):
        """Save and close."""
        self.save()
        self.destroy()
    
    def save(self):
        """Persist current store state."""
        self.storage.save_store(self.store)
        self.status_var.set("Saved")
    
    def refresh_all(self):
        """Refresh all tabs."""
        self.items_tab.refresh()
        self.consignors_tab.refresh()
        self.sales_tab.refresh()
        self.payouts_tab.refresh()
    
    def set_status(self, message: str):
        """Update status bar."""
        self.status_var.set(message)


# --- Helper Widgets ---

class ScrollableTreeview(ttk.Frame):
    """A treeview with scrollbars."""
    
    def __init__(self, parent, columns: list[tuple[str, str, int]], **kwargs):
        """
        Args:
            columns: List of (id, heading, width) tuples
        """
        super().__init__(parent)
        
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        
        # Create treeview
        col_ids = [c[0] for c in columns]
        self.tree = ttk.Treeview(self, columns=col_ids, show="headings", **kwargs)
        
        for col_id, heading, width in columns:
            self.tree.heading(col_id, text=heading)
            self.tree.column(col_id, width=width, minwidth=50)
        
        # Scrollbars
        vsb = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(self, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        # Grid
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
    
    def clear(self):
        """Remove all items."""
        for item in self.tree.get_children():
            self.tree.delete(item)
    
    def insert(self, values: tuple, tags: tuple = ()):
        """Insert a row."""
        self.tree.insert("", "end", values=values, tags=tags)
    
    def get_selected(self) -> Optional[tuple]:
        """Get selected row values."""
        selection = self.tree.selection()
        if selection:
            return self.tree.item(selection[0])["values"]
        return None
    
    def bind_select(self, callback: Callable):
        """Bind selection event."""
        self.tree.bind("<<TreeviewSelect>>", callback)
    
    def bind_double_click(self, callback: Callable):
        """Bind double-click event."""
        self.tree.bind("<Double-1>", callback)


class FormDialog(tk.Toplevel):
    """Base class for form dialogs."""
    
    def __init__(self, parent, title: str):
        super().__init__(parent)
        self.title(title)
        self.transient(parent)
        self.grab_set()
        
        self.result = None
        
        # Center on parent
        self.geometry("+%d+%d" % (parent.winfo_rootx() + 50, parent.winfo_rooty() + 50))
        
        # Main frame with padding
        self.main_frame = ttk.Frame(self, padding="10")
        self.main_frame.pack(fill="both", expand=True)
        
        # Will be filled by subclasses
        self.form_frame = ttk.Frame(self.main_frame)
        self.form_frame.pack(fill="both", expand=True)
        
        # Buttons
        self.button_frame = ttk.Frame(self.main_frame)
        self.button_frame.pack(fill="x", pady=(10, 0))
        
        ttk.Button(self.button_frame, text="Cancel", command=self.cancel).pack(side="right", padx=(5, 0))
        ttk.Button(self.button_frame, text="OK", command=self.ok).pack(side="right")
        
        self.bind("<Return>", lambda e: self.ok())
        self.bind("<Escape>", lambda e: self.cancel())
    
    def ok(self):
        """Override in subclass to validate and set self.result."""
        self.destroy()
    
    def cancel(self):
        self.result = None
        self.destroy()
    
    def add_field(self, label: str, var: tk.Variable, row: int, width: int = 30) -> ttk.Entry:
        """Add a labeled entry field."""
        ttk.Label(self.form_frame, text=label).grid(row=row, column=0, sticky="e", padx=(0, 10), pady=3)
        entry = ttk.Entry(self.form_frame, textvariable=var, width=width)
        entry.grid(row=row, column=1, sticky="w", pady=3)
        return entry
    
    def add_readonly_field(self, label: str, value: str, row: int):
        """Add a read-only display field."""
        ttk.Label(self.form_frame, text=label).grid(row=row, column=0, sticky="e", padx=(0, 10), pady=3)
        ttk.Label(self.form_frame, text=value, font=("TkDefaultFont", 9, "bold")).grid(row=row, column=1, sticky="w", pady=3)


# --- Consignors Tab ---

class ConsignorsTab(ttk.Frame):
    """Manage consignors."""
    
    def __init__(self, parent, app: App):
        super().__init__(parent, padding="10")
        self.app = app
        
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        
        # Toolbar
        toolbar = ttk.Frame(self)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        
        ttk.Button(toolbar, text="+ Add Consignor", command=self.add_consignor).pack(side="left")
        ttk.Button(toolbar, text="Edit", command=self.edit_consignor).pack(side="left", padx=(10, 0))
        ttk.Button(toolbar, text="View Items", command=self.view_items).pack(side="left", padx=(10, 0))
        
        # List
        columns = [
            ("id", "ID", 80),
            ("name", "Name", 200),
            ("phone", "Phone", 120),
            ("balance", "Balance", 100),
            ("split", "Split %", 80),
            ("fee", "Fee", 80),
        ]
        self.list = ScrollableTreeview(self, columns)
        self.list.grid(row=1, column=0, sticky="nsew")
        self.list.bind_double_click(lambda e: self.edit_consignor())
    
    def refresh(self):
        """Reload consignor list."""
        self.list.clear()
        for c in self.app.store.list_consignors():
            self.list.insert((
                c.consignor_id,
                c.name,
                c.phone or "",
                f"${c.balance:.2f}",
                f"{c.split_percent}%",
                f"${c.stocking_fee:.2f}"
            ))
    
    def add_consignor(self):
        dialog = ConsignorDialog(self, self.app.store)
        self.wait_window(dialog)
        if dialog.result:
            self.app.save()
            self.refresh()
            self.app.set_status(f"Added consignor: {dialog.result.name}")
    
    def edit_consignor(self):
        selected = self.list.get_selected()
        if not selected:
            messagebox.showwarning("No Selection", "Please select a consignor to edit.")
            return
        
        consignor_id = selected[0]
        consignor = self.app.store.get_consignor(consignor_id)
        if consignor:
            dialog = ConsignorDialog(self, self.app.store, consignor)
            self.wait_window(dialog)
            if dialog.result:
                self.app.save()
                self.refresh()
                self.app.set_status(f"Updated consignor: {dialog.result.name}")
    
    def view_items(self):
        selected = self.list.get_selected()
        if not selected:
            messagebox.showwarning("No Selection", "Please select a consignor.")
            return
        
        consignor_id = selected[0]
        # Switch to items tab and filter (simplified: just switch)
        self.app.notebook.select(0)  # Items tab
        self.app.set_status(f"Showing items for {selected[1]}")


class ConsignorDialog(FormDialog):
    """Add/Edit consignor dialog."""
    
    def __init__(self, parent, store: ConsignmentStore, consignor: Consignor = None):
        super().__init__(parent, "Edit Consignor" if consignor else "Add Consignor")
        self.store = store
        self.consignor = consignor
        
        # Variables
        self.name_var = tk.StringVar(value=consignor.name if consignor else "")
        self.phone_var = tk.StringVar(value=consignor.phone or "" if consignor else "")
        self.email_var = tk.StringVar(value=consignor.email or "" if consignor else "")
        self.street_var = tk.StringVar(value=consignor.address.street if consignor else "")
        self.city_var = tk.StringVar(value=consignor.address.city if consignor else "")
        self.state_var = tk.StringVar(value=consignor.address.state if consignor else "")
        self.zip_var = tk.StringVar(value=consignor.address.zip_code if consignor else "")
        self.split_var = tk.StringVar(value=str(consignor.split_percent) if consignor else str(store.default_split))
        self.fee_var = tk.StringVar(value=str(consignor.stocking_fee) if consignor else str(store.default_stocking_fee))
        
        # Show ID if editing
        row = 0
        if consignor:
            self.add_readonly_field("ID:", consignor.consignor_id, row)
            row += 1
        
        # Fields
        self.name_entry = self.add_field("Name:", self.name_var, row)
        self.add_field("Phone:", self.phone_var, row + 1)
        self.add_field("Email:", self.email_var, row + 2)
        
        ttk.Separator(self.form_frame, orient="horizontal").grid(row=row+3, column=0, columnspan=2, sticky="ew", pady=10)
        
        self.add_field("Street:", self.street_var, row + 4)
        self.add_field("City:", self.city_var, row + 5)
        self.add_field("State:", self.state_var, row + 6, width=5)
        self.add_field("ZIP:", self.zip_var, row + 7, width=10)
        
        ttk.Separator(self.form_frame, orient="horizontal").grid(row=row+8, column=0, columnspan=2, sticky="ew", pady=10)
        
        self.add_field("Split %:", self.split_var, row + 9, width=8)
        self.add_field("Stocking Fee $:", self.fee_var, row + 10, width=8)
        
        self.name_entry.focus_set()
    
    def ok(self):
        # Validate
        name = self.name_var.get().strip()
        if not name:
            messagebox.showerror("Error", "Name is required.")
            return
        
        try:
            split = Decimal(self.split_var.get())
            fee = Decimal(self.fee_var.get())
        except InvalidOperation:
            messagebox.showerror("Error", "Invalid split or fee value.")
            return
        
        address = Address(
            street=self.street_var.get().strip() or "N/A",
            city=self.city_var.get().strip() or "N/A",
            state=self.state_var.get().strip() or "N/A",
            zip_code=self.zip_var.get().strip() or "N/A"
        )
        
        if self.consignor:
            # Update existing
            self.consignor.name = name
            self.consignor.phone = self.phone_var.get().strip() or None
            self.consignor.email = self.email_var.get().strip() or None
            self.consignor.address = address
            self.consignor.split_percent = split
            self.consignor.stocking_fee = fee
            self.result = self.consignor
        else:
            # Create new
            self.result = self.store.add_consignor(
                name=name,
                address=address,
                phone=self.phone_var.get().strip() or None,
                email=self.email_var.get().strip() or None,
                split_percent=split,
                stocking_fee=fee
            )
        
        self.destroy()


# --- Items Tab ---

class ItemsTab(ttk.Frame):
    """Manage inventory items."""
    
    def __init__(self, parent, app: App):
        super().__init__(parent, padding="10")
        self.app = app
        
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        
        # Toolbar
        toolbar = ttk.Frame(self)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        
        ttk.Button(toolbar, text="+ Add Item", command=self.add_item).pack(side="left")
        ttk.Button(toolbar, text="+ Batch Add", command=self.batch_add_items).pack(side="left", padx=(5, 0))
        
        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=10)
        
        ttk.Button(toolbar, text="View/Edit", command=self.view_item).pack(side="left")
        ttk.Button(toolbar, text="Sell Item", command=self.sell_item).pack(side="left", padx=(5, 0))
        ttk.Button(toolbar, text="Return to Consignor", command=self.return_item).pack(side="left", padx=(5, 0))
        
        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=10)
        
        ttk.Button(toolbar, text="🖨 Print Tag", command=self.print_tag).pack(side="left")
        
        # Filter
        ttk.Label(toolbar, text="    Show:").pack(side="left", padx=(20, 5))
        self.filter_var = tk.StringVar(value="active")
        filter_combo = ttk.Combobox(toolbar, textvariable=self.filter_var, state="readonly", width=12)
        filter_combo["values"] = ("active", "sold", "returned", "expired", "all")
        filter_combo.pack(side="left")
        filter_combo.bind("<<ComboboxSelected>>", lambda e: self.refresh())
        
        # Item ID quick lookup (good for barcode scanners)
        ttk.Label(toolbar, text="    Item ID:").pack(side="left", padx=(20, 5))
        self.lookup_var = tk.StringVar()
        lookup_entry = ttk.Entry(toolbar, textvariable=self.lookup_var, width=12)
        lookup_entry.pack(side="left")
        lookup_entry.bind("<Return>", self.lookup_item)
        
        # List
        columns = [
            ("id", "Item ID", 90),
            ("name", "Name", 200),
            ("consignor", "Consignor", 150),
            ("original", "Original $", 90),
            ("current", "Current $", 90),
            ("status", "Status", 100),
            ("age", "Age", 60),
        ]
        self.list = ScrollableTreeview(self, columns)
        self.list.grid(row=1, column=0, sticky="nsew")
        self.list.bind_double_click(lambda e: self.view_item())
        
        # Configure tag colors
        self.list.tree.tag_configure("expired", background="#ffcccc")
        self.list.tree.tag_configure("expiring", background="#fff3cc")
    
    def refresh(self):
        """Reload item list."""
        self.list.clear()
        filter_status = self.filter_var.get()
        
        for item in self.app.store._items.values():
            # Apply filter
            if filter_status == "active" and item.status != ItemStatus.ACTIVE:
                continue
            elif filter_status == "sold" and item.status != ItemStatus.SOLD:
                continue
            elif filter_status == "returned" and item.status != ItemStatus.RETURNED:
                continue
            elif filter_status == "expired" and item.status != ItemStatus.EXPIRED:
                continue
            
            consignor = self.app.store.get_consignor(item.consignor_id)
            consignor_name = consignor.name if consignor else "Unknown"
            
            # Determine row tag
            tags = ()
            if item.status == ItemStatus.ACTIVE:
                if item.is_expired():
                    tags = ("expired",)
                elif item.days_since_entry() >= 106:  # Within 2 weeks of expiry
                    tags = ("expiring",)
            
            self.list.insert((
                item.item_id,
                item.name,
                consignor_name,
                f"${item.original_price:.2f}",
                f"${item.current_price():.2f}",
                item.price_tier_description(),
                f"{item.days_since_entry()}d"
            ), tags=tags)
    
    def lookup_item(self, event=None):
        """Quick lookup by item ID (for barcode scanner)."""
        item_id = self.lookup_var.get().strip().upper()
        if not item_id:
            return
        
        # Normalize - allow scanning without 'I' prefix
        if not item_id.startswith("I"):
            item_id = f"I{item_id.zfill(6)}"
        
        item = self.app.store.get_item(item_id)
        if item:
            self.view_item_dialog(item)
        else:
            messagebox.showinfo("Not Found", f"No item found with ID: {item_id}")
        
        self.lookup_var.set("")
    
    def add_item(self):
        if not self.app.store.list_consignors():
            messagebox.showwarning("No Consignors", "Please add a consignor first.")
            return
        
        dialog = ItemDialog(self, self.app.store, app=self.app)
        self.wait_window(dialog)
        if dialog.result:
            self.app.save()
            self.refresh()
            self.app.set_status(f"Added item: {dialog.result.name} ({dialog.result.item_id})")
    
    def view_item(self):
        selected = self.list.get_selected()
        if not selected:
            messagebox.showwarning("No Selection", "Please select an item.")
            return
        
        item = self.app.store.get_item(selected[0])
        if item:
            self.view_item_dialog(item)
    
    def view_item_dialog(self, item: Item):
        """Show item detail dialog."""
        dialog = ItemViewDialog(self, self.app.store, item, app=self.app)
        self.wait_window(dialog)
        if dialog.changed:
            self.app.save()
            self.refresh()
    
    def sell_item(self):
        selected = self.list.get_selected()
        if not selected:
            messagebox.showwarning("No Selection", "Please select an item to sell.")
            return
        
        item = self.app.store.get_item(selected[0])
        if not item:
            return
        
        if item.status != ItemStatus.ACTIVE:
            messagebox.showwarning("Cannot Sell", f"Item is {item.status.value}, not active.")
            return
        
        # Confirm sale
        consignor = self.app.store.get_consignor(item.consignor_id)
        current_price = item.current_price()
        
        if messagebox.askyesno("Confirm Sale", 
            f"Sell '{item.name}' for ${current_price:.2f}?\n\n"
            f"Consignor: {consignor.name}\n"
            f"Discount: {item.price_tier_description()}"
        ):
            sale = self.app.store.sell_item(item.item_id)
            self.app.save()
            self.refresh()
            self.app.set_status(
                f"SOLD: {item.name} for ${sale.sale_price:.2f} "
                f"(Consignor gets ${sale.consignor_share:.2f})"
            )
    
    def return_item(self):
        selected = self.list.get_selected()
        if not selected:
            messagebox.showwarning("No Selection", "Please select an item.")
            return
        
        item = self.app.store.get_item(selected[0])
        if not item:
            return
        
        if item.status != ItemStatus.ACTIVE:
            messagebox.showwarning("Cannot Return", f"Item is {item.status.value}, not active.")
            return
        
        if messagebox.askyesno("Confirm Return", 
            f"Return '{item.name}' to consignor?"
        ):
            self.app.store.return_item_to_consignor(item.item_id)
            self.app.save()
            self.refresh()
            self.app.set_status(f"Returned to consignor: {item.name}")
    
    def print_tag(self):
        """Print a tag for the selected item."""
        selected = self.list.get_selected()
        if not selected:
            messagebox.showwarning("No Selection", "Please select an item to print a tag for.")
            return
        
        item = self.app.store.get_item(selected[0])
        if not item:
            return
        
        try:
            result = self.app.printer.print_tag(item)
            if self.app.printer_config.preview_only and result:
                self.app.set_status(f"Tag preview saved: {result}")
                # Optionally open the preview
                import webbrowser
                webbrowser.open(f"file://{result}")
            else:
                self.app.set_status(f"Printed tag for: {item.name}")
        except Exception as e:
            messagebox.showerror("Print Error", f"Failed to print tag: {e}")
    
    def batch_add_items(self):
        """Open batch entry dialog to add multiple items and print tags."""
        if not self.app.store.list_consignors():
            messagebox.showwarning("No Consignors", "Please add a consignor first.")
            return
        
        dialog = BatchItemDialog(self, self.app)
        self.wait_window(dialog)
        
        if dialog.added_items:
            self.app.save()
            self.refresh()
            count = len(dialog.added_items)
            self.app.set_status(f"Added {count} item(s)")


class BatchItemDialog(tk.Toplevel):
    """Dialog for adding multiple items at once with optional tag printing."""
    
    def __init__(self, parent, app: App):
        super().__init__(parent)
        self.title("Batch Add Items")
        self.transient(parent)
        self.grab_set()
        
        self.app = app
        self.store = app.store
        self.added_items: list[Item] = []
        
        # Size and position
        self.geometry("600x500")
        self.geometry("+%d+%d" % (parent.winfo_rootx() + 30, parent.winfo_rooty() + 30))
        
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        
        # --- Consignor Selection ---
        consignor_frame = ttk.LabelFrame(self, text="Consignor", padding="10")
        consignor_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))
        
        self.consignor_var = tk.StringVar()
        self.consignors = {f"{c.consignor_id} - {c.name}": c.consignor_id for c in self.store.list_consignors()}
        consignor_combo = ttk.Combobox(consignor_frame, textvariable=self.consignor_var, state="readonly", width=40)
        consignor_combo["values"] = list(self.consignors.keys())
        if self.consignors:
            consignor_combo.current(0)
        consignor_combo.pack(side="left")
        
        ttk.Label(consignor_frame, text="  (All items in this batch go to this consignor)").pack(side="left")
        
        # --- Entry Form ---
        entry_frame = ttk.LabelFrame(self, text="Add Item", padding="10")
        entry_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=5)
        
        ttk.Label(entry_frame, text="Name:").grid(row=0, column=0, sticky="e", padx=(0, 5))
        self.name_var = tk.StringVar()
        self.name_entry = ttk.Entry(entry_frame, textvariable=self.name_var, width=30)
        self.name_entry.grid(row=0, column=1, sticky="w", padx=(0, 15))
        
        ttk.Label(entry_frame, text="Description:").grid(row=0, column=2, sticky="e", padx=(0, 5))
        self.desc_var = tk.StringVar()
        ttk.Entry(entry_frame, textvariable=self.desc_var, width=25).grid(row=0, column=3, sticky="w", padx=(0, 15))
        
        ttk.Label(entry_frame, text="Price $:").grid(row=0, column=4, sticky="e", padx=(0, 5))
        self.price_var = tk.StringVar()
        price_entry = ttk.Entry(entry_frame, textvariable=self.price_var, width=10)
        price_entry.grid(row=0, column=5, sticky="w", padx=(0, 15))
        
        add_btn = ttk.Button(entry_frame, text="Add to Batch", command=self.add_to_batch)
        add_btn.grid(row=0, column=6)
        
        # Bind Enter key to add
        self.name_entry.bind("<Return>", lambda e: self.add_to_batch())
        price_entry.bind("<Return>", lambda e: self.add_to_batch())
        
        # --- Batch List ---
        list_frame = ttk.LabelFrame(self, text="Items in Batch", padding="10")
        list_frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=5)
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)
        
        columns = [
            ("name", "Item Name", 200),
            ("description", "Description", 180),
            ("price", "Price", 80),
        ]
        self.batch_list = ScrollableTreeview(list_frame, columns, height=10)
        self.batch_list.grid(row=0, column=0, sticky="nsew")
        
        # Remove button
        ttk.Button(list_frame, text="Remove Selected", command=self.remove_from_batch).grid(row=1, column=0, sticky="w", pady=(5, 0))
        
        # --- Bottom Buttons ---
        button_frame = ttk.Frame(self, padding="10")
        button_frame.grid(row=3, column=0, sticky="ew")
        
        self.print_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(button_frame, text="Print tags for all items", variable=self.print_var).pack(side="left")
        
        ttk.Button(button_frame, text="Cancel", command=self.cancel).pack(side="right", padx=(5, 0))
        ttk.Button(button_frame, text="Save All", command=self.save_all).pack(side="right")
        
        # Track pending items (before save)
        self.pending_items: list[dict] = []
        
        self.name_entry.focus_set()
        
        self.bind("<Escape>", lambda e: self.cancel())
    
    def add_to_batch(self):
        """Add current entry to the batch list."""
        name = self.name_var.get().strip()
        if not name:
            messagebox.showerror("Error", "Item name is required.")
            self.name_entry.focus_set()
            return
        
        try:
            price = Decimal(self.price_var.get())
            if price <= 0:
                raise ValueError()
        except (InvalidOperation, ValueError):
            messagebox.showerror("Error", "Please enter a valid price.")
            return
        
        # Add to pending list
        item_data = {
            'name': name,
            'description': self.desc_var.get().strip(),
            'price': price
        }
        self.pending_items.append(item_data)
        
        # Add to display list
        self.batch_list.insert((name, item_data['description'], f"${price:.2f}"))
        
        # Clear entry fields for next item
        self.name_var.set("")
        self.desc_var.set("")
        self.price_var.set("")
        self.name_entry.focus_set()
    
    def remove_from_batch(self):
        """Remove selected item from batch."""
        selection = self.batch_list.tree.selection()
        if not selection:
            return
        
        # Get index and remove from both lists
        idx = self.batch_list.tree.index(selection[0])
        self.batch_list.tree.delete(selection[0])
        if idx < len(self.pending_items):
            del self.pending_items[idx]
    
    def save_all(self):
        """Save all items in batch to the store."""
        if not self.pending_items:
            messagebox.showwarning("Empty Batch", "No items to save. Add some items first.")
            return
        
        consignor_key = self.consignor_var.get()
        if not consignor_key or consignor_key not in self.consignors:
            messagebox.showerror("Error", "Please select a consignor.")
            return
        
        consignor_id = self.consignors[consignor_key]
        
        # Create all items
        for item_data in self.pending_items:
            item = self.store.add_item(
                consignor_id=consignor_id,
                name=item_data['name'],
                description=item_data['description'],
                price=item_data['price']
            )
            self.added_items.append(item)
        
        # Print tags if requested
        if self.print_var.get() and self.added_items:
            try:
                result = self.app.printer.print_tags(self.added_items)
                if self.app.printer_config.preview_only and result:
                    import webbrowser
                    webbrowser.open(f"file://{result}")
                    messagebox.showinfo("Tags Generated", 
                        f"Created {len(self.added_items)} item(s).\n"
                        f"Tag preview opened in browser.")
                else:
                    messagebox.showinfo("Complete", 
                        f"Created {len(self.added_items)} item(s) and sent tags to printer.")
            except Exception as e:
                messagebox.showwarning("Print Error", 
                    f"Items saved, but printing failed: {e}")
        else:
            messagebox.showinfo("Complete", f"Created {len(self.added_items)} item(s).")
        
        self.destroy()
    
    def cancel(self):
        """Close without saving."""
        if self.pending_items:
            if not messagebox.askyesno("Confirm Cancel", 
                f"Discard {len(self.pending_items)} unsaved item(s)?"):
                return
        self.destroy()


class ItemDialog(FormDialog):
    """Add new item dialog."""
    
    def __init__(self, parent, store: ConsignmentStore, app: App = None):
        super().__init__(parent, "Add Item")
        self.store = store
        self.app = app
        
        # Variables
        self.consignor_var = tk.StringVar()
        self.name_var = tk.StringVar()
        self.desc_var = tk.StringVar()
        self.price_var = tk.StringVar()
        self.print_var = tk.BooleanVar(value=True)  # Default to printing
        
        # Consignor dropdown
        ttk.Label(self.form_frame, text="Consignor:").grid(row=0, column=0, sticky="e", padx=(0, 10), pady=3)
        self.consignor_combo = ttk.Combobox(self.form_frame, textvariable=self.consignor_var, state="readonly", width=30)
        self.consignors = {f"{c.consignor_id} - {c.name}": c.consignor_id for c in store.list_consignors()}
        self.consignor_combo["values"] = list(self.consignors.keys())
        if self.consignors:
            self.consignor_combo.current(0)
        self.consignor_combo.grid(row=0, column=1, sticky="w", pady=3)
        
        self.name_entry = self.add_field("Item Name:", self.name_var, 1)
        self.add_field("Description:", self.desc_var, 2, width=40)
        self.add_field("Price $:", self.price_var, 3, width=10)
        
        # Print tag checkbox
        ttk.Checkbutton(self.form_frame, text="Print tag after adding", 
                        variable=self.print_var).grid(row=4, column=1, sticky="w", pady=(10, 0))
        
        self.name_entry.focus_set()
    
    def ok(self):
        name = self.name_var.get().strip()
        if not name:
            messagebox.showerror("Error", "Item name is required.")
            return
        
        try:
            price = Decimal(self.price_var.get())
            if price <= 0:
                raise ValueError()
        except (InvalidOperation, ValueError):
            messagebox.showerror("Error", "Please enter a valid price.")
            return
        
        consignor_key = self.consignor_var.get()
        if not consignor_key or consignor_key not in self.consignors:
            messagebox.showerror("Error", "Please select a consignor.")
            return
        
        consignor_id = self.consignors[consignor_key]
        
        self.result = self.store.add_item(
            consignor_id=consignor_id,
            name=name,
            description=self.desc_var.get().strip(),
            price=price
        )
        
        # Print tag if requested and we have app reference
        if self.print_var.get() and self.app:
            try:
                result = self.app.printer.print_tag(self.result)
                if self.app.printer_config.preview_only and result:
                    import webbrowser
                    webbrowser.open(f"file://{result}")
            except Exception as e:
                messagebox.showwarning("Print Error", f"Item saved, but printing failed: {e}")
        
        self.destroy()


class ItemViewDialog(FormDialog):
    """View item details dialog."""
    
    def __init__(self, parent, store: ConsignmentStore, item: Item, app: App = None):
        super().__init__(parent, f"Item: {item.item_id}")
        self.store = store
        self.item = item
        self.app = app
        self.changed = False
        
        consignor = store.get_consignor(item.consignor_id)
        
        # Item info
        self.add_readonly_field("Item ID:", item.item_id, 0)
        self.add_readonly_field("Name:", item.name, 1)
        self.add_readonly_field("Description:", item.description or "(none)", 2)
        self.add_readonly_field("Consignor:", f"{consignor.name} ({item.consignor_id})" if consignor else "Unknown", 3)
        
        ttk.Separator(self.form_frame, orient="horizontal").grid(row=4, column=0, columnspan=2, sticky="ew", pady=10)
        
        self.add_readonly_field("Original Price:", f"${item.original_price:.2f}", 5)
        self.add_readonly_field("Current Price:", f"${item.current_price():.2f}", 6)
        self.add_readonly_field("Status:", item.price_tier_description(), 7)
        self.add_readonly_field("Entry Date:", str(item.entry_date), 8)
        self.add_readonly_field("Days in Store:", str(item.days_since_entry()), 9)
        
        # If sold, show sale info
        if item.sale_record:
            ttk.Separator(self.form_frame, orient="horizontal").grid(row=10, column=0, columnspan=2, sticky="ew", pady=10)
            self.add_readonly_field("Sale Date:", str(item.sale_record.sale_date), 11)
            self.add_readonly_field("Sale Price:", f"${item.sale_record.sale_price:.2f}", 12)
            self.add_readonly_field("Consignor Share:", f"${item.sale_record.consignor_share:.2f}", 13)
            self.add_readonly_field("Store Share:", f"${item.sale_record.store_share:.2f}", 14)
        
        # Add Print Tag button if we have app reference and item is active
        if app and item.status == ItemStatus.ACTIVE:
            ttk.Separator(self.form_frame, orient="horizontal").grid(row=15, column=0, columnspan=2, sticky="ew", pady=10)
            print_btn = ttk.Button(self.form_frame, text="🖨 Print Tag", command=self.print_tag)
            print_btn.grid(row=16, column=0, columnspan=2, pady=5)
    
    def print_tag(self):
        """Print a tag for this item."""
        if not self.app:
            return
        try:
            result = self.app.printer.print_tag(self.item)
            if self.app.printer_config.preview_only and result:
                import webbrowser
                webbrowser.open(f"file://{result}")
                messagebox.showinfo("Tag Preview", "Tag preview opened in browser.")
            else:
                messagebox.showinfo("Printed", f"Tag printed for: {self.item.name}")
        except Exception as e:
            messagebox.showerror("Print Error", f"Failed to print: {e}")
    
    def ok(self):
        self.destroy()


# --- Sales Tab ---

class SalesTab(ttk.Frame):
    """View sales history."""
    
    def __init__(self, parent, app: App):
        super().__init__(parent, padding="10")
        self.app = app
        
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        
        # Header
        header = ttk.Frame(self)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        ttk.Label(header, text="Sales History", font=("TkDefaultFont", 12, "bold")).pack(side="left")
        
        # Quick sale by ID (barcode scanner friendly)
        ttk.Label(header, text="    Quick Sell ID:").pack(side="left", padx=(30, 5))
        self.quick_sell_var = tk.StringVar()
        quick_entry = ttk.Entry(header, textvariable=self.quick_sell_var, width=12)
        quick_entry.pack(side="left")
        quick_entry.bind("<Return>", self.quick_sell)
        
        # List
        columns = [
            ("item_id", "Item ID", 90),
            ("name", "Item Name", 180),
            ("consignor", "Consignor", 150),
            ("sale_date", "Sale Date", 100),
            ("original", "Original", 80),
            ("sale_price", "Sale Price", 90),
            ("consignor_share", "To Consignor", 100),
            ("store_share", "To Store", 90),
        ]
        self.list = ScrollableTreeview(self, columns)
        self.list.grid(row=1, column=0, sticky="nsew")
        
        # Totals
        self.totals_var = tk.StringVar()
        ttk.Label(self, textvariable=self.totals_var, font=("TkDefaultFont", 10)).grid(row=2, column=0, sticky="w", pady=(10, 0))
    
    def refresh(self):
        """Reload sales list."""
        self.list.clear()
        total_sales = Decimal("0")
        total_consignor = Decimal("0")
        total_store = Decimal("0")
        
        for item in self.app.store._items.values():
            if item.sale_record:
                sale = item.sale_record
                consignor = self.app.store.get_consignor(item.consignor_id)
                
                self.list.insert((
                    item.item_id,
                    item.name,
                    consignor.name if consignor else "Unknown",
                    str(sale.sale_date),
                    f"${sale.original_price:.2f}",
                    f"${sale.sale_price:.2f}",
                    f"${sale.consignor_share:.2f}",
                    f"${sale.store_share:.2f}",
                ))
                
                total_sales += sale.sale_price
                total_consignor += sale.consignor_share
                total_store += sale.store_share
        
        self.totals_var.set(
            f"Total Sales: ${total_sales:.2f}  |  "
            f"To Consignors: ${total_consignor:.2f}  |  "
            f"To Store: ${total_store:.2f}"
        )
    
    def quick_sell(self, event=None):
        """Quick sell by item ID (barcode scanner)."""
        item_id = self.quick_sell_var.get().strip().upper()
        if not item_id:
            return
        
        # Normalize
        if not item_id.startswith("I"):
            item_id = f"I{item_id.zfill(6)}"
        
        item = self.app.store.get_item(item_id)
        if not item:
            messagebox.showinfo("Not Found", f"No item found: {item_id}")
            self.quick_sell_var.set("")
            return
        
        if item.status != ItemStatus.ACTIVE:
            messagebox.showwarning("Cannot Sell", f"Item is {item.status.value}")
            self.quick_sell_var.set("")
            return
        
        consignor = self.app.store.get_consignor(item.consignor_id)
        current_price = item.current_price()
        
        if messagebox.askyesno("Confirm Sale",
            f"Sell '{item.name}' for ${current_price:.2f}?\n\n"
            f"Consignor: {consignor.name if consignor else 'Unknown'}"
        ):
            sale = self.app.store.sell_item(item.item_id)
            self.app.save()
            self.refresh()
            self.app.set_status(f"SOLD: {item.name} for ${sale.sale_price:.2f}")
        
        self.quick_sell_var.set("")


# --- Payouts Tab ---

class PayoutsTab(ttk.Frame):
    """Manage consignor payouts."""
    
    def __init__(self, parent, app: App):
        super().__init__(parent, padding="10")
        self.app = app
        
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self.rowconfigure(3, weight=1)
        
        # Balances section
        ttk.Label(self, text="Outstanding Balances", font=("TkDefaultFont", 11, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 5))
        
        balance_columns = [
            ("id", "ID", 80),
            ("name", "Consignor", 200),
            ("balance", "Balance Due", 120),
        ]
        self.balance_list = ScrollableTreeview(self, balance_columns, height=8)
        self.balance_list.grid(row=1, column=0, sticky="nsew")
        
        # Payout button
        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=2, column=0, sticky="w", pady=10)
        ttk.Button(btn_frame, text="Process Payout", command=self.process_payout).pack(side="left")
        
        # History section
        ttk.Label(self, text="Payout History", font=("TkDefaultFont", 11, "bold")).grid(row=3, column=0, sticky="nw", pady=(10, 5))
        
        history_columns = [
            ("id", "Payout ID", 90),
            ("consignor", "Consignor", 180),
            ("date", "Date", 100),
            ("amount", "Amount", 100),
            ("check", "Check #", 100),
        ]
        self.history_list = ScrollableTreeview(self, history_columns, height=8)
        self.history_list.grid(row=4, column=0, sticky="nsew")
    
    def refresh(self):
        """Reload payout info."""
        # Balances
        self.balance_list.clear()
        for c in self.app.store.list_consignors():
            if c.balance > 0:
                self.balance_list.insert((
                    c.consignor_id,
                    c.name,
                    f"${c.balance:.2f}"
                ))
        
        # History
        self.history_list.clear()
        for p in self.app.store._payouts:
            consignor = self.app.store.get_consignor(p.consignor_id)
            self.history_list.insert((
                p.payout_id,
                consignor.name if consignor else "Unknown",
                str(p.payout_date),
                f"${p.amount:.2f}",
                p.check_number or ""
            ))
    
    def process_payout(self):
        selected = self.balance_list.get_selected()
        if not selected:
            messagebox.showwarning("No Selection", "Please select a consignor to pay.")
            return
        
        consignor_id = selected[0]
        consignor = self.app.store.get_consignor(consignor_id)
        if not consignor or consignor.balance <= 0:
            messagebox.showinfo("No Balance", "This consignor has no balance due.")
            return
        
        # Get check number
        check_num = simpledialog.askstring(
            "Check Number",
            f"Paying ${consignor.balance:.2f} to {consignor.name}\n\nEnter check number (optional):",
            parent=self
        )
        
        if check_num is None:  # Cancelled
            return
        
        payout = self.app.store.process_payout(consignor_id, check_number=check_num or None)
        if payout:
            self.app.save()
            self.refresh()
            self.app.set_status(f"Payout processed: ${payout.amount:.2f} to {consignor.name}")


# --- Main Entry Point ---

def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
