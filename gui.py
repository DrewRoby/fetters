"""
Consignment Shop Management - Desktop GUI

A simple, clean Tkinter interface for managing consignment inventory,
accounts, sales, and payouts.
"""

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Optional, Callable

from core import (
    ItemStatus, Address, Item, Account, ConsignmentStore
)
from storage import ConsignmentStorage


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
        
        # Configure grid
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        
        # Create notebook (tabs)
        self.notebook = ttk.Notebook(self)
        self.notebook.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        
        # Create tab frames
        self.items_tab = ItemsTab(self.notebook, self)
        self.accounts_tab = AccountsTab(self.notebook, self)
        self.sales_tab = SalesTab(self.notebook, self)
        self.payouts_tab = PayoutsTab(self.notebook, self)
        
        self.notebook.add(self.items_tab, text="  Items  ")
        self.notebook.add(self.accounts_tab, text="  Accounts  ")
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
        self.accounts_tab.refresh()
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
        
        # Grab focus after window is fully constructed
        # Use after_idle to ensure window is viewable
        self.after_idle(self._grab_focus)
    
    def _grab_focus(self):
        """Grab focus after window is ready."""
        try:
            self.grab_set()
        except tk.TclError:
            # If grab fails, just continue without it
            pass
    
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


# --- Accounts Tab ---

class AccountsTab(ttk.Frame):
    """Manage accounts."""
    
    def __init__(self, parent, app: App):
        super().__init__(parent, padding="10")
        self.app = app
        
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        
        # Toolbar
        toolbar = ttk.Frame(self)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        
        ttk.Button(toolbar, text="+ Add Account", command=self.add_account).pack(side="left")
        ttk.Button(toolbar, text="View", command=self.view_account).pack(side="left", padx=(10, 0))
        
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
        self.list.bind_double_click(lambda e: self.view_account())
    
    def refresh(self):
        """Reload account list."""
        self.list.clear()
        for c in self.app.store.list_accounts():
            self.list.insert((
                c.account_id,
                c.full_name,
                c.phone or "",
                f"${c.balance:.2f}",
                f"{c.split_percent}%",
                f"${c.stocking_fee:.2f}"
            ))
    
    def add_account(self):
        dialog = AccountDialog(self, self.app.store)
        self.wait_window(dialog)
        if dialog.result:
            self.app.save()
            self.refresh()
            self.app.set_status(f"Added account: {dialog.result.full_name}")
    
    def view_account(self):
        """Open account detail window."""
        selected = self.list.get_selected()
        if not selected:
            messagebox.showwarning("No Selection", "Please select an account.")
            return
        
        account_id = selected[0]
        account = self.app.store.get_account(account_id)
        if account:
            # Create a non-modal detail window
            detail_window = AccountDetailWindow(self.app, account)


class AccountDialog(FormDialog):
    """Add/Edit account dialog."""
    
    def __init__(self, parent, store: ConsignmentStore, account: Account = None):
        super().__init__(parent, "Edit Account" if account else "Add Account")
        self.store = store
        self.account = account
        
        # Variables
        self.first_name_var = tk.StringVar(value=account.first_name if account else "")
        self.last_name_var = tk.StringVar(value=account.last_name if account else "")
        self.phone_var = tk.StringVar(value=account.phone or "" if account else "")
        self.email_var = tk.StringVar(value=account.email or "" if account else "")
        self.street_var = tk.StringVar(value=account.address.street if account else "")
        self.city_var = tk.StringVar(value=account.address.city if account else "")
        self.state_var = tk.StringVar(value=account.address.state if account else "")
        self.zip_var = tk.StringVar(value=account.address.zip_code if account else "")
        self.split_var = tk.StringVar(value=str(account.split_percent) if account else str(store.default_split))
        self.fee_var = tk.StringVar(value=str(account.stocking_fee) if account else str(store.default_stocking_fee))
        
        # Show ID if editing
        row = 0
        if account:
            self.add_readonly_field("ID:", account.account_id, row)
            row += 1
        
        # Fields
        self.first_name_entry = self.add_field("First Name:", self.first_name_var, row, width=20)
        self.last_name_entry = self.add_field("Last Name:", self.last_name_var, row + 1, width=20)
        self.add_field("Phone:", self.phone_var, row + 2)
        self.add_field("Email:", self.email_var, row + 3)
        
        ttk.Separator(self.form_frame, orient="horizontal").grid(row=row+4, column=0, columnspan=2, sticky="ew", pady=10)
        
        self.add_field("Street:", self.street_var, row + 5)
        self.add_field("City:", self.city_var, row + 6)
        self.add_field("State:", self.state_var, row + 7, width=5)
        self.add_field("ZIP:", self.zip_var, row + 8, width=10)
        
        ttk.Separator(self.form_frame, orient="horizontal").grid(row=row+9, column=0, columnspan=2, sticky="ew", pady=10)
        
        self.add_field("Split %:", self.split_var, row + 10, width=8)
        self.add_field("Stocking Fee $:", self.fee_var, row + 11, width=8)
        
        self.first_name_entry.focus_set()
    
    def ok(self):
        # Validate
        first_name = self.first_name_var.get().strip()
        last_name = self.last_name_var.get().strip()
        
        if not first_name or not last_name:
            messagebox.showerror("Error", "First and last name are required.")
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
        
        if self.account:
            # Update existing
            self.account.first_name = first_name
            self.account.last_name = last_name
            self.account.phone = self.phone_var.get().strip() or None
            self.account.email = self.email_var.get().strip() or None
            self.account.address = address
            self.account.split_percent = split
            self.account.stocking_fee = fee
            self.result = self.account
        else:
            # Create new
            self.result = self.store.add_account(
                first_name=first_name,
                last_name=last_name,
                address=address,
                phone=self.phone_var.get().strip() or None,
                email=self.email_var.get().strip() or None,
                split_percent=split,
                stocking_fee=fee
            )
        
        self.destroy()


class AccountDetailWindow(tk.Toplevel):
    """Detail window showing account info and their items."""
    
    def __init__(self, app: App, account: Account):
        super().__init__(app)
        self.app = app
        self.account = account
        
        self.title(f"Account: {account.full_name}")
        self.geometry("900x650")
        
        # Make it stay on top initially but not modal
        self.transient(app)
        
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        
        # --- Info Section ---
        info_frame = ttk.LabelFrame(self, text="Account Information", padding="10")
        info_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))
        
        # Left column
        left_frame = ttk.Frame(info_frame)
        left_frame.grid(row=0, column=0, sticky="w", padx=(0, 30))
        
        ttk.Label(left_frame, text="Name:", font=("TkDefaultFont", 9, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(left_frame, text=account.full_name).grid(row=0, column=1, sticky="w", padx=(10, 0))
        
        ttk.Label(left_frame, text="ID:", font=("TkDefaultFont", 9, "bold")).grid(row=1, column=0, sticky="w", pady=(5, 0))
        ttk.Label(left_frame, text=account.account_id).grid(row=1, column=1, sticky="w", padx=(10, 0), pady=(5, 0))
        
        # Middle column
        mid_frame = ttk.Frame(info_frame)
        mid_frame.grid(row=0, column=1, sticky="w", padx=(0, 30))
        
        ttk.Label(mid_frame, text="Phone:", font=("TkDefaultFont", 9, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(mid_frame, text=account.phone or "N/A").grid(row=0, column=1, sticky="w", padx=(10, 0))
        
        ttk.Label(mid_frame, text="Email:", font=("TkDefaultFont", 9, "bold")).grid(row=1, column=0, sticky="w", pady=(5, 0))
        ttk.Label(mid_frame, text=account.email or "N/A").grid(row=1, column=1, sticky="w", padx=(10, 0), pady=(5, 0))
        
        # Right column
        right_frame = ttk.Frame(info_frame)
        right_frame.grid(row=0, column=2, sticky="w")
        
        ttk.Label(right_frame, text="Balance:", font=("TkDefaultFont", 9, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(right_frame, text=f"${account.balance:.2f}", font=("TkDefaultFont", 10)).grid(row=0, column=1, sticky="w", padx=(10, 0))
        
        ttk.Label(right_frame, text="Split:", font=("TkDefaultFont", 9, "bold")).grid(row=1, column=0, sticky="w", pady=(5, 0))
        ttk.Label(right_frame, text=f"{account.split_percent}% / ${account.stocking_fee:.2f} fee").grid(row=1, column=1, sticky="w", padx=(10, 0), pady=(5, 0))
        
        # Edit button
        ttk.Button(info_frame, text="Edit Info", command=self.edit_account).grid(row=0, column=3, sticky="e", padx=(20, 0))
        
        # --- Items Section ---
        items_frame = ttk.LabelFrame(self, text="Items", padding="10")
        items_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=5)
        
        # Toolbar with filter and action buttons
        toolbar = ttk.Frame(items_frame)
        toolbar.pack(fill="x", pady=(0, 10))
        
        # Left side - Add Item button
        ttk.Button(toolbar, text="+ Add Item", command=self.add_item).pack(side="left")
        
        # Filter in the middle
        ttk.Label(toolbar, text="    Show:").pack(side="left", padx=(20, 5))
        self.filter_var = tk.StringVar(value="active")
        filter_combo = ttk.Combobox(toolbar, textvariable=self.filter_var, state="readonly", width=12)
        filter_combo["values"] = ("active", "sold", "returned", "expired", "all")
        filter_combo.pack(side="left")
        filter_combo.bind("<<ComboboxSelected>>", lambda e: self.refresh_items())
        
        # Action buttons on the right
        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=10)
        ttk.Button(toolbar, text="Sell Item", command=self.sell_item).pack(side="left", padx=(0, 5))
        ttk.Button(toolbar, text="Return Item", command=self.return_item).pack(side="left", padx=(0, 5))
        
        # Items list
        columns = [
            ("id", "Item ID", 90),
            ("name", "Name", 200),
            ("original", "Original $", 90),
            ("current", "Current $", 90),
            ("status", "Status", 100),
            ("entry_date", "Entry Date", 100),
        ]
        self.items_list = ScrollableTreeview(items_frame, columns, height=15)
        self.items_list.pack(fill="both", expand=True)
        
        # Configure tag colors
        self.items_list.tree.tag_configure("expired", background="#ffcccc")
        self.items_list.tree.tag_configure("expiring", background="#fff3cc")
        
        # Refresh items
        self.refresh_items()
    
    def refresh_items(self):
        """Reload items list for this account."""
        self.items_list.clear()
        filter_status = self.filter_var.get()
        
        # Get items for this account, sorted by entry date
        items = self.app.store.get_items_by_account(self.account.account_id)
        items.sort(key=lambda x: x.entry_date)
        
        for item in items:
            # Apply filter
            if filter_status == "active" and item.status != ItemStatus.ACTIVE:
                continue
            elif filter_status == "sold" and item.status != ItemStatus.SOLD:
                continue
            elif filter_status == "returned" and item.status != ItemStatus.RETURNED:
                continue
            elif filter_status == "expired" and item.status != ItemStatus.EXPIRED:
                continue
            
            # Determine row tag
            tags = ()
            if item.status == ItemStatus.ACTIVE:
                if item.is_expired():
                    tags = ("expired",)
                elif item.days_since_entry() >= 106:  # Within 2 weeks of expiry
                    tags = ("expiring",)
            
            self.items_list.insert((
                item.item_id,
                item.name,
                f"${item.original_price:.2f}",
                f"${item.current_price():.2f}",
                item.price_tier_description(),
                str(item.entry_date)
            ), tags=tags)
    
    def edit_account(self):
        """Open edit dialog for this account."""
        dialog = AccountDialog(self, self.app.store, self.account)
        self.wait_window(dialog)
        if dialog.result:
            self.app.save()
            self.app.refresh_all()
            # Update window title
            self.title(f"Account: {self.account.full_name}")
            self.app.set_status(f"Updated account: {self.account.full_name}")
    
    def add_item(self):
        """Add an item for this account."""
        dialog = ItemDialog(self, self.app.store, preselect_account_id=self.account.account_id)
        self.wait_window(dialog)
        if dialog.result:
            self.app.save()
            self.refresh_items()
            self.app.refresh_all()
            self.app.set_status(f"Added item: {dialog.result.name} ({dialog.result.item_id})")
    
    def sell_item(self):
        """Sell selected item."""
        selected = self.items_list.get_selected()
        if not selected:
            messagebox.showwarning("No Selection", "Please select an item to sell.")
            return
        
        item_id = selected[0]
        item = self.app.store.get_item(item_id)
        if not item:
            return
        
        if item.status != ItemStatus.ACTIVE:
            messagebox.showwarning("Cannot Sell", f"Item is {item.status.value}, not active.")
            return
        
        current_price = item.current_price()
        
        if messagebox.askyesno("Confirm Sale", 
            f"Sell '{item.name}' for ${current_price:.2f}?\n\n"
            f"Account: {self.account.full_name}\n"
            f"Discount: {item.price_tier_description()}"
        ):
            sale = self.app.store.sell_item(item.item_id)
            self.app.save()
            self.refresh_items()
            self.app.refresh_all()
            self.app.set_status(
                f"SOLD: {item.name} for ${sale.sale_price:.2f} "
                f"(Account gets ${sale.account_share:.2f})"
            )
    
    def return_item(self):
        """Return selected item to account."""
        selected = self.items_list.get_selected()
        if not selected:
            messagebox.showwarning("No Selection", "Please select an item.")
            return
        
        item_id = selected[0]
        item = self.app.store.get_item(item_id)
        if not item:
            return
        
        if item.status != ItemStatus.ACTIVE:
            messagebox.showwarning("Cannot Return", f"Item is {item.status.value}, not active.")
            return
        
        if messagebox.askyesno("Confirm Return", 
            f"Return '{item.name}' to account?"
        ):
            self.app.store.return_item_to_account(item.item_id)
            self.app.save()
            self.refresh_items()
            self.app.refresh_all()
            self.app.set_status(f"Returned to account: {item.name}")


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
        ttk.Button(toolbar, text="View/Edit", command=self.view_item).pack(side="left", padx=(10, 0))
        ttk.Button(toolbar, text="Sell Item", command=self.sell_item).pack(side="left", padx=(10, 0))
        ttk.Button(toolbar, text="Return to Account", command=self.return_item).pack(side="left", padx=(10, 0))
        
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
            ("account", "Account", 150),
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
            
            account = self.app.store.get_account(item.account_id)
            account_name = account.full_name if account else "Unknown"
            
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
                account_name,
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
        if not self.app.store.list_accounts():
            messagebox.showwarning("No Accounts", "Please add an account first.")
            return
        
        dialog = ItemDialog(self, self.app.store)
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
        dialog = ItemViewDialog(self, self.app.store, item)
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
        account = self.app.store.get_account(item.account_id)
        current_price = item.current_price()
        
        if messagebox.askyesno("Confirm Sale", 
            f"Sell '{item.name}' for ${current_price:.2f}?\n\n"
            f"Account: {account.full_name if account else 'Unknown'}\n"
            f"Discount: {item.price_tier_description()}"
        ):
            sale = self.app.store.sell_item(item.item_id)
            self.app.save()
            self.refresh()
            self.app.set_status(
                f"SOLD: {item.name} for ${sale.sale_price:.2f} "
                f"(Account gets ${sale.account_share:.2f})"
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
            f"Return '{item.name}' to account?"
        ):
            self.app.store.return_item_to_account(item.item_id)
            self.app.save()
            self.refresh()
            self.app.set_status(f"Returned to account: {item.name}")


class ItemDialog(FormDialog):
    """Add new item dialog."""
    
    def __init__(self, parent, store: ConsignmentStore, preselect_account_id: str = None):
        super().__init__(parent, "Add Item")
        self.store = store
        self.preselect_account_id = preselect_account_id
        
        # Variables
        self.account_var = tk.StringVar()
        self.name_var = tk.StringVar()
        self.desc_var = tk.StringVar()
        self.price_var = tk.StringVar()
        
        # Account dropdown
        ttk.Label(self.form_frame, text="Account:").grid(row=0, column=0, sticky="e", padx=(0, 10), pady=3)
        self.account_combo = ttk.Combobox(self.form_frame, textvariable=self.account_var, state="readonly", width=30)
        self.accounts = {f"{c.account_id} - {c.full_name}": c.account_id for c in store.list_accounts()}
        self.account_combo["values"] = list(self.accounts.keys())
        
        # Pre-select if provided
        if preselect_account_id:
            for key, value in self.accounts.items():
                if value == preselect_account_id:
                    self.account_combo.set(key)
                    break
        elif self.accounts:
            self.account_combo.current(0)
        
        self.account_combo.grid(row=0, column=1, sticky="w", pady=3)
        
        self.name_entry = self.add_field("Item Name:", self.name_var, 1)
        self.add_field("Description:", self.desc_var, 2, width=40)
        self.add_field("Price $:", self.price_var, 3, width=10)
        
        self.name_entry.focus_set()
    
    def ok(self):
        name = self.name_var.get().strip()
        if not name:
            messagebox.showerror("Error", "Item name is required.")
            return
        
        try:
            price = Decimal(self.price_var.get())
            if price <= 0:
                raise ValueError("Price must be positive")
            # Sanity check: max price of $100,000 (adjust as needed for your store)
            if price > Decimal("100000.00"):
                messagebox.showerror("Error", "Price cannot exceed $100,000.00")
                return
        except (InvalidOperation, ValueError):
            messagebox.showerror("Error", "Please enter a valid price (maximum $100,000).")
            return
        
        account_key = self.account_var.get()
        if not account_key or account_key not in self.accounts:
            messagebox.showerror("Error", "Please select an account.")
            return
        
        account_id = self.accounts[account_key]
        
        self.result = self.store.add_item(
            account_id=account_id,
            name=name,
            description=self.desc_var.get().strip(),
            price=price
        )
        
        self.destroy()


class ItemViewDialog(FormDialog):
    """View item details dialog."""
    
    def __init__(self, parent, store: ConsignmentStore, item: Item):
        super().__init__(parent, f"Item: {item.item_id}")
        self.store = store
        self.item = item
        self.changed = False
        
        account = store.get_account(item.account_id)
        
        # Item info
        self.add_readonly_field("Item ID:", item.item_id, 0)
        self.add_readonly_field("Name:", item.name, 1)
        self.add_readonly_field("Description:", item.description or "(none)", 2)
        self.add_readonly_field("Account:", 
                                f"{account.full_name} ({item.account_id})" if account else "Unknown", 3)
        
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
            self.add_readonly_field("Account Share:", f"${item.sale_record.account_share:.2f}", 13)
            self.add_readonly_field("Store Share:", f"${item.sale_record.store_share:.2f}", 14)
    
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
            ("account", "Account", 150),
            ("sale_date", "Sale Date", 100),
            ("original", "Original", 80),
            ("sale_price", "Sale Price", 90),
            ("account_share", "To Account", 100),
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
        total_account = Decimal("0")
        total_store = Decimal("0")
        
        for item in self.app.store._items.values():
            if item.sale_record:
                sale = item.sale_record
                account = self.app.store.get_account(item.account_id)
                
                self.list.insert((
                    item.item_id,
                    item.name,
                    account.full_name if account else "Unknown",
                    str(sale.sale_date),
                    f"${sale.original_price:.2f}",
                    f"${sale.sale_price:.2f}",
                    f"${sale.account_share:.2f}",
                    f"${sale.store_share:.2f}",
                ))
                
                total_sales += sale.sale_price
                total_account += sale.account_share
                total_store += sale.store_share
        
        self.totals_var.set(
            f"Total Sales: ${total_sales:.2f}  |  "
            f"To Accounts: ${total_account:.2f}  |  "
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
        
        account = self.app.store.get_account(item.account_id)
        current_price = item.current_price()
        
        if messagebox.askyesno("Confirm Sale",
            f"Sell '{item.name}' for ${current_price:.2f}?\n\n"
            f"Account: {account.full_name if account else 'Unknown'}"
        ):
            sale = self.app.store.sell_item(item.item_id)
            self.app.save()
            self.refresh()
            self.app.set_status(f"SOLD: {item.name} for ${sale.sale_price:.2f}")
        
        self.quick_sell_var.set("")


# --- Payouts Tab ---

class PayoutsTab(ttk.Frame):
    """Manage account payouts."""
    
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
            ("name", "Account", 200),
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
            ("account", "Account", 180),
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
        for c in self.app.store.list_accounts():
            if c.balance > 0:
                self.balance_list.insert((
                    c.account_id,
                    c.full_name,
                    f"${c.balance:.2f}"
                ))
        
        # History
        self.history_list.clear()
        for p in self.app.store._payouts:
            account = self.app.store.get_account(p.account_id)
            self.history_list.insert((
                p.payout_id,
                account.full_name if account else "Unknown",
                str(p.payout_date),
                f"${p.amount:.2f}",
                p.check_number or ""
            ))
    
    def process_payout(self):
        selected = self.balance_list.get_selected()
        if not selected:
            messagebox.showwarning("No Selection", "Please select an account to pay.")
            return
        
        account_id = selected[0]
        account = self.app.store.get_account(account_id)
        if not account or account.balance <= 0:
            messagebox.showinfo("No Balance", "This account has no balance due.")
            return
        
        # Get check number
        check_num = simpledialog.askstring(
            "Check Number",
            f"Paying ${account.balance:.2f} to {account.full_name}\n\nEnter check number (optional):",
            parent=self
        )
        
        if check_num is None:  # Cancelled
            return
        
        payout = self.app.store.process_payout(account_id, check_number=check_num or None)
        if payout:
            self.app.save()
            self.refresh()
            self.app.set_status(f"Payout processed: ${payout.amount:.2f} to {account.full_name}")


# --- Main Entry Point ---

def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()