"""
Tests for the tag printing module.
"""

import unittest
import tempfile
import os
from datetime import date
from decimal import Decimal
from pathlib import Path

from core import Item, ItemStatus
from printing import (
    TagSize, TagLayout, PrinterConfig, TagContent, TagPrinter,
    print_item_tag, print_item_tags
)


class TestTagLayout(unittest.TestCase):
    """Test tag layout configurations."""
    
    def test_small_layout(self):
        layout = TagLayout.for_size(TagSize.SMALL)
        self.assertEqual(layout.width_inches, 1.5)
        self.assertEqual(layout.height_inches, 1.0)
        self.assertFalse(layout.show_description)
        self.assertTrue(layout.show_item_id)
    
    def test_medium_layout(self):
        layout = TagLayout.for_size(TagSize.MEDIUM)
        self.assertEqual(layout.width_inches, 2.0)
        self.assertTrue(layout.show_consignor_id)
        self.assertTrue(layout.show_entry_date)
    
    def test_large_layout(self):
        layout = TagLayout.for_size(TagSize.LARGE)
        self.assertEqual(layout.width_inches, 2.5)
        self.assertTrue(layout.show_description)


class TestTagContent(unittest.TestCase):
    """Test tag content creation."""
    
    def test_from_item(self):
        item = Item(
            item_id="I000001",
            consignor_id="C1001",
            name="Vintage Lamp",
            description="Art deco brass lamp",
            original_price=Decimal("75.00"),
            entry_date=date.today(),
            status_date=date.today()
        )
        
        content = TagContent.from_item(item)
        
        self.assertEqual(content.item_id, "I000001")
        self.assertEqual(content.item_name, "Vintage Lamp")
        self.assertEqual(content.price, Decimal("75.00"))
        self.assertEqual(content.description, "Art deco brass lamp")
    
    def test_manual_creation(self):
        content = TagContent(
            item_id="I000002",
            item_name="Test Item",
            price=Decimal("50.00")
        )
        
        self.assertEqual(content.item_name, "Test Item")
        self.assertEqual(content.description, "")


class TestPrinterConfig(unittest.TestCase):
    """Test printer configuration."""
    
    def test_default_config(self):
        config = PrinterConfig()
        
        self.assertIsNone(config.printer_name)
        self.assertEqual(config.tag_size, TagSize.MEDIUM)
        self.assertEqual(config.copies_per_tag, 1)
        self.assertFalse(config.preview_only)
        self.assertEqual(config.store_name, "Consignment Shop")
    
    def test_custom_config(self):
        config = PrinterConfig(
            printer_name="Label Printer",
            tag_size=TagSize.LARGE,
            copies_per_tag=2,
            store_name="My Shop"
        )
        
        self.assertEqual(config.printer_name, "Label Printer")
        self.assertEqual(config.tag_size, TagSize.LARGE)
        self.assertEqual(config.copies_per_tag, 2)


class TestTagPrinter(unittest.TestCase):
    """Test tag printing functionality."""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.config = PrinterConfig(
            preview_only=True,  # Don't actually print
            output_dir=self.temp_dir,
            store_name="Test Shop"
        )
        self.printer = TagPrinter(self.config)
        
        self.item = Item(
            item_id="I000001",
            consignor_id="C1001",
            name="Test Item",
            description="A test item description",
            original_price=Decimal("99.99"),
            entry_date=date.today(),
            status_date=date.today()
        )
    
    def tearDown(self):
        # Clean up temp files
        for f in Path(self.temp_dir).glob("*"):
            f.unlink()
        os.rmdir(self.temp_dir)
    
    def test_print_single_tag(self):
        """Should generate HTML file for single tag."""
        result = self.printer.print_tag(self.item)
        
        self.assertIsNotNone(result)
        self.assertTrue(os.path.exists(result))
        
        # Check content
        with open(result) as f:
            html = f.read()
        
        self.assertIn("Test Shop", html)
        self.assertIn("Test Item", html)
        self.assertIn("$99.99", html)
        self.assertIn("I000001", html)
    
    def test_print_multiple_tags(self):
        """Should generate HTML file with multiple tags."""
        item2 = Item(
            item_id="I000002",
            consignor_id="C1001",
            name="Second Item",
            description="Another item",
            original_price=Decimal("50.00"),
            entry_date=date.today(),
            status_date=date.today()
        )
        
        result = self.printer.print_tags([self.item, item2])
        
        self.assertIsNotNone(result)
        
        with open(result) as f:
            html = f.read()
        
        self.assertIn("Test Item", html)
        self.assertIn("Second Item", html)
        self.assertIn("$99.99", html)
        self.assertIn("$50.00", html)
    
    def test_print_empty_list(self):
        """Empty list should return None."""
        result = self.printer.print_tags([])
        self.assertIsNone(result)
    
    def test_copies_per_tag(self):
        """Should generate correct number of copies."""
        config = PrinterConfig(
            preview_only=True,
            output_dir=self.temp_dir,
            copies_per_tag=3
        )
        printer = TagPrinter(config)
        
        result = printer.print_tag(self.item)
        
        with open(result) as f:
            html = f.read()
        
        # Should have 3 copies of the item
        count = html.count("I000001")
        self.assertEqual(count, 3)
    
    def test_tag_sizes(self):
        """Should generate different sizes correctly."""
        for size in TagSize:
            config = PrinterConfig(
                preview_only=True,
                output_dir=self.temp_dir,
                tag_size=size
            )
            printer = TagPrinter(config)
            
            result = printer.print_tag(self.item)
            self.assertIsNotNone(result)
            
            with open(result) as f:
                html = f.read()
            
            # All sizes should have the price
            self.assertIn("$99.99", html)
    
    def test_description_shown_in_large(self):
        """Large tags should show description."""
        config = PrinterConfig(
            preview_only=True,
            output_dir=self.temp_dir,
            tag_size=TagSize.LARGE
        )
        printer = TagPrinter(config)
        
        result = printer.print_tag(self.item)
        
        with open(result) as f:
            html = f.read()
        
        self.assertIn("A test item description", html)
    
    def test_description_hidden_in_small(self):
        """Small tags should not show description."""
        config = PrinterConfig(
            preview_only=True,
            output_dir=self.temp_dir,
            tag_size=TagSize.SMALL
        )
        printer = TagPrinter(config)
        
        result = printer.print_tag(self.item)
        
        with open(result) as f:
            html = f.read()
        
        # Description class shouldn't contain actual description text
        # (it might still have the div but it should be empty)
        self.assertNotIn("A test item description", html)


class TestConvenienceFunctions(unittest.TestCase):
    """Test convenience printing functions."""
    
    def setUp(self):
        self.item = Item(
            item_id="I000001",
            consignor_id="C1001",
            name="Quick Print Item",
            description="",
            original_price=Decimal("25.00"),
            entry_date=date.today(),
            status_date=date.today()
        )
    
    def test_print_item_tag_preview(self):
        """Quick print function should work in preview mode."""
        result = print_item_tag(self.item, preview=True)
        
        self.assertIsNotNone(result)
        self.assertTrue(os.path.exists(result))
        
        # Clean up
        os.remove(result)
    
    def test_print_item_tags_preview(self):
        """Quick batch print should work in preview mode."""
        item2 = Item(
            item_id="I000002",
            consignor_id="C1001",
            name="Another Item",
            description="",
            original_price=Decimal("30.00"),
            entry_date=date.today(),
            status_date=date.today()
        )
        
        result = print_item_tags([self.item, item2], preview=True)
        
        self.assertIsNotNone(result)
        self.assertTrue(os.path.exists(result))
        
        with open(result) as f:
            html = f.read()
        
        self.assertIn("Quick Print Item", html)
        self.assertIn("Another Item", html)
        
        # Clean up
        os.remove(result)
    
    def test_custom_store_name(self):
        """Should use custom store name."""
        result = print_item_tag(
            self.item, 
            store_name="Jane's Consignment", 
            preview=True
        )
        
        with open(result) as f:
            html = f.read()
        
        self.assertIn("Jane's Consignment", html)
        
        # Clean up
        os.remove(result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
