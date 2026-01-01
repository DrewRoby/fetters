"""
Tag printing module for consignment items.

Supports printing price tags with item details, pricing, and optional barcodes.
Configurable for different printer types and tag sizes.
"""

import os
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Optional

from core import Item, Consignor, ConsignmentStore


class TagSize(Enum):
    """Standard tag sizes."""
    SMALL = "small"      # 1.5" x 1" - price only
    MEDIUM = "medium"    # 2" x 1.25" - price + basic info  
    LARGE = "large"      # 2.5" x 1.5" - full details


@dataclass
class TagLayout:
    """Tag layout configuration."""
    width_inches: float
    height_inches: float
    font_size_title: int
    font_size_price: int
    font_size_detail: int
    show_description: bool
    show_consignor_id: bool
    show_entry_date: bool
    show_item_id: bool
    
    @classmethod
    def for_size(cls, size: TagSize) -> 'TagLayout':
        """Get standard layout for a tag size."""
        layouts = {
            TagSize.SMALL: cls(
                width_inches=1.5,
                height_inches=1.0,
                font_size_title=8,
                font_size_price=14,
                font_size_detail=6,
                show_description=False,
                show_consignor_id=False,
                show_entry_date=False,
                show_item_id=True
            ),
            TagSize.MEDIUM: cls(
                width_inches=2.0,
                height_inches=1.25,
                font_size_title=10,
                font_size_price=16,
                font_size_detail=7,
                show_description=False,
                show_consignor_id=True,
                show_entry_date=True,
                show_item_id=True
            ),
            TagSize.LARGE: cls(
                width_inches=2.5,
                height_inches=1.5,
                font_size_title=11,
                font_size_price=18,
                font_size_detail=8,
                show_description=True,
                show_consignor_id=True,
                show_entry_date=True,
                show_item_id=True
            ),
        }
        return layouts[size]


@dataclass 
class PrinterConfig:
    """Printer configuration."""
    printer_name: Optional[str] = None  # None = system default
    tag_size: TagSize = TagSize.MEDIUM
    copies_per_tag: int = 1
    preview_only: bool = False  # If True, just generate file, don't print
    output_dir: Optional[str] = None  # Where to save preview files
    
    # Store branding
    store_name: str = "Consignment Shop"
    store_tagline: str = ""


class TagContent:
    """Represents the content of a single tag."""
    
    def __init__(
        self,
        item_id: str,
        item_name: str,
        price: Decimal,
        description: str = "",
        consignor_id: str = "",
        entry_date: Optional[date] = None
    ):
        self.item_id = item_id
        self.item_name = item_name
        self.price = price
        self.description = description
        self.consignor_id = consignor_id
        self.entry_date = entry_date
    
    @classmethod
    def from_item(cls, item: Item) -> 'TagContent':
        """Create tag content from an Item object."""
        return cls(
            item_id=item.item_id,
            item_name=item.name,
            price=item.original_price,  # Tags show original price
            description=item.description,
            consignor_id=item.consignor_id,
            entry_date=item.entry_date
        )


class TagPrinter:
    """
    Handles tag generation and printing.
    
    Usage:
        printer = TagPrinter(config)
        
        # Single tag
        printer.print_tag(item)
        
        # Multiple tags
        printer.print_tags([item1, item2, item3])
        
        # Preview without printing
        config.preview_only = True
        path = printer.print_tag(item)  # Returns path to generated file
    """
    
    def __init__(self, config: Optional[PrinterConfig] = None):
        self.config = config or PrinterConfig()
        self.layout = TagLayout.for_size(self.config.tag_size)
    
    def print_tag(self, item: Item) -> Optional[str]:
        """
        Print a tag for a single item.
        
        Returns:
            Path to generated file if preview_only, else None
        """
        return self.print_tags([item])
    
    def print_tags(self, items: list[Item]) -> Optional[str]:
        """
        Print tags for multiple items.
        
        Returns:
            Path to generated file if preview_only, else None
        """
        if not items:
            return None
        
        contents = [TagContent.from_item(item) for item in items]
        return self._print_contents(contents)
    
    def _print_contents(self, contents: list[TagContent]) -> Optional[str]:
        """Generate and print tag contents."""
        # Generate the printable document
        html_content = self._generate_html(contents)
        
        # Save to file
        if self.config.output_dir:
            output_dir = Path(self.config.output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = output_dir / f"tags_{date.today().isoformat()}.html"
        else:
            # Use temp file
            fd, output_path = tempfile.mkstemp(suffix=".html", prefix="tags_")
            os.close(fd)
            output_path = Path(output_path)
        
        output_path.write_text(html_content)
        
        if self.config.preview_only:
            return str(output_path)
        
        # Send to printer
        self._send_to_printer(str(output_path))
        return str(output_path)
    
    def _generate_html(self, contents: list[TagContent]) -> str:
        """Generate HTML document with tags for printing."""
        layout = self.layout
        config = self.config
        
        # Calculate tag dimensions in points (72 points per inch)
        width_pt = layout.width_inches * 72
        height_pt = layout.height_inches * 72
        
        tags_html = []
        for content in contents:
            for _ in range(config.copies_per_tag):
                tag = self._generate_single_tag_html(content)
                tags_html.append(tag)
        
        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Price Tags</title>
    <style>
        @page {{
            size: auto;
            margin: 0.25in;
        }}
        
        body {{
            font-family: Arial, Helvetica, sans-serif;
            margin: 0;
            padding: 10px;
        }}
        
        .tags-container {{
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
        }}
        
        .tag {{
            width: {width_pt}pt;
            height: {height_pt}pt;
            border: 1px solid #000;
            padding: 5pt;
            box-sizing: border-box;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            page-break-inside: avoid;
            overflow: hidden;
        }}
        
        .tag-header {{
            text-align: center;
            border-bottom: 1px solid #ccc;
            padding-bottom: 3pt;
            margin-bottom: 3pt;
        }}
        
        .store-name {{
            font-size: 7pt;
            font-weight: bold;
            color: #333;
            margin: 0;
        }}
        
        .item-name {{
            font-size: {layout.font_size_title}pt;
            font-weight: bold;
            margin: 2pt 0;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }}
        
        .description {{
            font-size: {layout.font_size_detail}pt;
            color: #555;
            margin: 2pt 0;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }}
        
        .price {{
            font-size: {layout.font_size_price}pt;
            font-weight: bold;
            text-align: center;
            margin: 3pt 0;
        }}
        
        .tag-footer {{
            display: flex;
            justify-content: space-between;
            font-size: {layout.font_size_detail}pt;
            color: #666;
            border-top: 1px solid #ccc;
            padding-top: 3pt;
            margin-top: 3pt;
        }}
        
        .item-id {{
            font-family: monospace;
            font-weight: bold;
        }}
        
        @media print {{
            body {{
                padding: 0;
            }}
            .tag {{
                border: 1px solid #000;
            }}
        }}
    </style>
</head>
<body>
    <div class="tags-container">
        {''.join(tags_html)}
    </div>
</body>
</html>"""
        return html
    
    def _generate_single_tag_html(self, content: TagContent) -> str:
        """Generate HTML for a single tag."""
        layout = self.layout
        config = self.config
        
        # Build optional sections
        description_html = ""
        if layout.show_description and content.description:
            desc = content.description[:50]  # Truncate long descriptions
            description_html = f'<div class="description">{desc}</div>'
        
        # Footer items
        footer_left = ""
        footer_right = ""
        
        if layout.show_item_id:
            footer_left = f'<span class="item-id">{content.item_id}</span>'
        
        footer_parts = []
        if layout.show_consignor_id:
            footer_parts.append(content.consignor_id)
        if layout.show_entry_date and content.entry_date:
            footer_parts.append(content.entry_date.strftime("%m/%d"))
        footer_right = " ".join(footer_parts)
        
        return f"""
        <div class="tag">
            <div class="tag-header">
                <div class="store-name">{config.store_name}</div>
                <div class="item-name">{content.item_name}</div>
                {description_html}
            </div>
            <div class="price">${content.price:.2f}</div>
            <div class="tag-footer">
                <span>{footer_left}</span>
                <span>{footer_right}</span>
            </div>
        </div>"""
    
    def _send_to_printer(self, file_path: str):
        """Send file to printer using system commands."""
        system = os.name
        
        try:
            if system == 'nt':  # Windows
                if self.config.printer_name:
                    # Print to specific printer
                    os.startfile(file_path, "print")
                else:
                    # Default printer
                    os.startfile(file_path, "print")
            
            elif system == 'posix':  # macOS / Linux
                if self.config.printer_name:
                    subprocess.run([
                        "lp", "-d", self.config.printer_name, file_path
                    ], check=True)
                else:
                    subprocess.run(["lp", file_path], check=True)
        
        except Exception as e:
            raise PrinterError(f"Failed to print: {e}")
    
    def get_available_printers(self) -> list[str]:
        """Get list of available printers on the system."""
        printers = []
        
        try:
            if os.name == 'nt':  # Windows
                import winreg
                key = winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows NT\CurrentVersion\Devices"
                )
                i = 0
                while True:
                    try:
                        printer_name = winreg.EnumValue(key, i)[0]
                        printers.append(printer_name)
                        i += 1
                    except OSError:
                        break
                winreg.CloseKey(key)
            
            elif os.name == 'posix':  # macOS / Linux
                result = subprocess.run(
                    ["lpstat", "-p"], 
                    capture_output=True, 
                    text=True
                )
                for line in result.stdout.split('\n'):
                    if line.startswith('printer '):
                        parts = line.split()
                        if len(parts) >= 2:
                            printers.append(parts[1])
        
        except Exception:
            pass  # Return empty list on error
        
        return printers


class PrinterError(Exception):
    """Raised when printing fails."""
    pass


# --- Convenience Functions ---

def print_item_tag(
    item: Item,
    store_name: str = "Consignment Shop",
    preview: bool = False
) -> Optional[str]:
    """
    Quick function to print a single item tag.
    
    Args:
        item: The item to print
        store_name: Name to show on tag
        preview: If True, just generate file without printing
    
    Returns:
        Path to generated file if preview=True
    """
    config = PrinterConfig(
        store_name=store_name,
        preview_only=preview
    )
    printer = TagPrinter(config)
    return printer.print_tag(item)


def print_item_tags(
    items: list[Item],
    store_name: str = "Consignment Shop",
    preview: bool = False
) -> Optional[str]:
    """
    Quick function to print multiple item tags.
    
    Args:
        items: List of items to print
        store_name: Name to show on tags
        preview: If True, just generate file without printing
    
    Returns:
        Path to generated file if preview=True
    """
    config = PrinterConfig(
        store_name=store_name,
        preview_only=preview
    )
    printer = TagPrinter(config)
    return printer.print_tags(items)
