"""
Categories and Attributes utility module.

Provides functions for working with item categories and their attributes.
"""

import sqlite3
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class Category:
    """A category for items."""
    category_id: int
    name: str
    description: Optional[str] = None


@dataclass
class Attribute:
    """An attribute definition for a category."""
    attribute_id: int
    category_id: int
    name: str
    attribute_type: str  # 'text', 'choice', 'number'
    display_order: int = 0
    choices: List[str] = None  # Available choices if type is 'choice'
    
    def __post_init__(self):
        if self.choices is None:
            self.choices = []


class CategoryManager:
    """
    Manages categories and attributes.
    
    Usage:
        manager = CategoryManager("consignment.db")
        
        # Get all categories
        categories = manager.get_all_categories()
        
        # Get attributes for a category
        attributes = manager.get_category_attributes(category_id)
        
        # Get/set item attributes
        values = manager.get_item_attributes(item_id)
        manager.set_item_attribute(item_id, attribute_id, "value")
    """
    
    def __init__(self, db_path: str = "consignment.db"):
        self.db_path = db_path
    
    def _get_connection(self):
        """Get database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def get_all_categories(self) -> List[Category]:
        """Get all categories, sorted by name."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT category_id, name, description 
            FROM categories 
            ORDER BY name
        """)
        
        categories = [
            Category(
                category_id=row['category_id'],
                name=row['name'],
                description=row['description']
            )
            for row in cursor.fetchall()
        ]
        
        conn.close()
        return categories
    
    def get_category(self, category_id: int) -> Optional[Category]:
        """Get a specific category."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT category_id, name, description 
            FROM categories 
            WHERE category_id = ?
        """, (category_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return Category(
                category_id=row['category_id'],
                name=row['name'],
                description=row['description']
            )
        return None
    
    def get_category_by_name(self, name: str) -> Optional[Category]:
        """Get a category by name."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT category_id, name, description 
            FROM categories 
            WHERE name = ?
        """, (name,))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return Category(
                category_id=row['category_id'],
                name=row['name'],
                description=row['description']
            )
        return None
    
    def get_category_attributes(self, category_id: int) -> List[Attribute]:
        """Get all attributes for a category, with their choices if applicable."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Get attributes
        cursor.execute("""
            SELECT attribute_id, category_id, name, attribute_type, display_order
            FROM attributes
            WHERE category_id = ?
            ORDER BY display_order, name
        """, (category_id,))
        
        attributes = []
        for row in cursor.fetchall():
            attr = Attribute(
                attribute_id=row['attribute_id'],
                category_id=row['category_id'],
                name=row['name'],
                attribute_type=row['attribute_type'],
                display_order=row['display_order']
            )
            
            # Get choices if this is a choice attribute
            if attr.attribute_type == 'choice':
                cursor.execute("""
                    SELECT value 
                    FROM attribute_choices 
                    WHERE attribute_id = ?
                    ORDER BY display_order, value
                """, (attr.attribute_id,))
                attr.choices = [r['value'] for r in cursor.fetchall()]
            
            attributes.append(attr)
        
        conn.close()
        return attributes
    
    def get_item_attributes(self, item_id: str) -> Dict[int, str]:
        """
        Get all attribute values for an item.
        
        Returns dict mapping attribute_id -> value
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT attribute_id, value 
            FROM item_attributes 
            WHERE item_id = ?
        """, (item_id,))
        
        result = {row['attribute_id']: row['value'] for row in cursor.fetchall()}
        conn.close()
        return result
    
    def get_item_attributes_detailed(self, item_id: str) -> List[Dict[str, Any]]:
        """
        Get detailed attribute info for an item.
        
        Returns list of dicts with attribute metadata and values.
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                a.attribute_id,
                a.name,
                a.attribute_type,
                ia.value
            FROM item_attributes ia
            JOIN attributes a ON ia.attribute_id = a.attribute_id
            WHERE ia.item_id = ?
            ORDER BY a.display_order, a.name
        """, (item_id,))
        
        results = [
            {
                'attribute_id': row['attribute_id'],
                'name': row['name'],
                'type': row['attribute_type'],
                'value': row['value']
            }
            for row in cursor.fetchall()
        ]
        
        conn.close()
        return results
    
    def set_item_attribute(self, item_id: str, attribute_id: int, value: str):
        """Set an attribute value for an item."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        now = datetime.now(timezone.utc).isoformat()
        
        cursor.execute("""
            INSERT OR REPLACE INTO item_attributes 
            (item_id, attribute_id, value, modified_at, sync_status)
            VALUES (?, ?, ?, ?, 'pending')
        """, (item_id, attribute_id, value, now))
        
        conn.commit()
        conn.close()
    
    def set_item_attributes(self, item_id: str, attributes: Dict[int, str]):
        """
        Set multiple attribute values for an item.
        
        Args:
            item_id: The item ID
            attributes: Dict mapping attribute_id -> value
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        now = datetime.now(timezone.utc).isoformat()
        
        for attribute_id, value in attributes.items():
            if value:  # Only set non-empty values
                cursor.execute("""
                    INSERT OR REPLACE INTO item_attributes 
                    (item_id, attribute_id, value, modified_at, sync_status)
                    VALUES (?, ?, ?, ?, 'pending')
                """, (item_id, attribute_id, value, now))
        
        conn.commit()
        conn.close()
    
    def clear_item_attributes(self, item_id: str):
        """Remove all attributes for an item."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM item_attributes WHERE item_id = ?", (item_id,))
        
        conn.commit()
        conn.close()
    
    def add_category(self, name: str, description: str = None) -> Category:
        """Add a new category."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        now = datetime.now(timezone.utc).isoformat()
        
        cursor.execute("""
            INSERT INTO categories (name, description, created_at, modified_at, sync_status)
            VALUES (?, ?, ?, ?, 'pending')
        """, (name, description, now, now))
        
        category_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return Category(category_id=category_id, name=name, description=description)
    
    def add_attribute(
        self, 
        category_id: int, 
        name: str, 
        attribute_type: str,
        choices: List[str] = None
    ) -> Attribute:
        """
        Add a new attribute to a category.
        
        Args:
            category_id: Category to add to
            name: Attribute name
            attribute_type: 'text', 'choice', or 'number'
            choices: List of choice values (only for type='choice')
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        now = datetime.now(timezone.utc).isoformat()
        
        # Get max display order
        cursor.execute("""
            SELECT COALESCE(MAX(display_order), -1) + 1
            FROM attributes
            WHERE category_id = ?
        """, (category_id,))
        display_order = cursor.fetchone()[0]
        
        # Insert attribute
        cursor.execute("""
            INSERT INTO attributes 
            (category_id, name, attribute_type, display_order, created_at, modified_at, sync_status)
            VALUES (?, ?, ?, ?, ?, ?, 'pending')
        """, (category_id, name, attribute_type, display_order, now, now))
        
        attribute_id = cursor.lastrowid
        
        # Insert choices if provided
        if choices and attribute_type == 'choice':
            for idx, choice in enumerate(choices):
                cursor.execute("""
                    INSERT INTO attribute_choices (attribute_id, value, display_order)
                    VALUES (?, ?, ?)
                """, (attribute_id, choice, idx))
        
        conn.commit()
        conn.close()
        
        return Attribute(
            attribute_id=attribute_id,
            category_id=category_id,
            name=name,
            attribute_type=attribute_type,
            display_order=display_order,
            choices=choices or []
        )


# Convenience functions

def get_categories(db_path: str = "consignment.db") -> List[Category]:
    """Quick function to get all categories."""
    manager = CategoryManager(db_path)
    return manager.get_all_categories()


def get_category_attributes(category_id: int, db_path: str = "consignment.db") -> List[Attribute]:
    """Quick function to get attributes for a category."""
    manager = CategoryManager(db_path)
    return manager.get_category_attributes(category_id)
