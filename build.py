#!/usr/bin/env python3
"""
Build script for Lacteos Buenos Aires product catalog.
Reads all Excel/ODS files from the portfolio folder and generates data.json
"""

import pandas as pd
import json
import os
import re
from pathlib import Path

PORTFOLIO_DIR = Path("portfolio")
OUTPUT_FILE = Path("site/data.json")


def extract_brand_from_filename(filename: str) -> str:
    """Extract brand name from filename, removing year and extension."""
    # Remove extension
    name = Path(filename).stem
    # Remove year pattern (25, 26, 2025, 2026, etc.)
    name = re.sub(r'\s*\d{2,4}$', '', name)
    return name.strip()


def find_header_row(df: pd.DataFrame) -> int:
    """Find the row containing column headers (CÓDIGO, PRODUCTO, etc.)."""
    for idx, row in df.iterrows():
        row_str = ' '.join(str(v).upper() for v in row.values if pd.notna(v))
        if 'CÓDIGO' in row_str or 'CODIGO' in row_str:
            return idx
    return 0


def clean_price(value) -> float:
    """Convert price value to float."""
    if pd.isna(value):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    # Remove currency symbols and convert
    cleaned = re.sub(r'[^\d.,]', '', str(value))
    cleaned = cleaned.replace(',', '.')
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def process_excel_file(filepath: Path) -> list:
    """Process a single Excel/ODS file and return list of products."""
    print(f"  Processing: {filepath.name}")

    # First read without header to find header row
    try:
        df_raw = pd.read_excel(filepath, header=None)
    except Exception as e:
        print(f"    Error reading file: {e}")
        return []

    # Find the header row
    header_row = find_header_row(df_raw)

    # Re-read with correct header
    try:
        df = pd.read_excel(filepath, header=header_row)
    except Exception as e:
        print(f"    Error re-reading file: {e}")
        return []

    # Normalize column names
    df.columns = [str(col).strip().upper() for col in df.columns]

    # Find the relevant columns
    code_col = None
    name_col = None
    unit_col = None
    price_col = None

    for col in df.columns:
        col_upper = col.upper()
        if 'CÓDIGO' in col_upper or 'CODIGO' in col_upper:
            code_col = col
        elif 'PRODUCTO' in col_upper or 'NOMBRE' in col_upper:
            name_col = col
        elif 'UNIDAD' in col_upper:
            unit_col = col
        elif 'FINAL' in col_upper or 'P. FINAL' in col_upper:
            price_col = col

    # If no final price column, look for PRECIO
    if price_col is None:
        for col in df.columns:
            if 'PRECIO' in col.upper():
                price_col = col
                break

    if not all([code_col, name_col]):
        print(f"    Could not find required columns. Found: {list(df.columns)}")
        return []

    products = []
    brand = extract_brand_from_filename(filepath.name)

    for _, row in df.iterrows():
        code = row.get(code_col)
        name = row.get(name_col)

        # Skip rows without valid code or name
        if pd.isna(code) or pd.isna(name):
            continue
        if not str(code).strip() or not str(name).strip():
            continue
        # Skip header-like rows
        if str(code).upper() in ['CÓDIGO', 'CODIGO']:
            continue

        product = {
            'code': str(code).strip(),
            'name': str(name).strip(),
            'unit': str(row.get(unit_col, '')).strip() if unit_col and pd.notna(row.get(unit_col)) else '',
            'price': clean_price(row.get(price_col)) if price_col else 0.0,
            'brand': brand
        }

        # Only add products with actual names
        if product['name'] and len(product['name']) > 2:
            products.append(product)

    print(f"    Found {len(products)} products")
    return products


def categorize_product(product_name: str) -> str:
    """Attempt to categorize a product based on its name."""
    name_upper = product_name.upper()

    # Order matters - more specific categories first
    categories = {
        'Café y Chocolate': [
            'CAFE', 'CAFÉ', 'NESCAFE', 'LUKAFE', 'COFFEE',
            'COCOA', 'CACAO', 'CHOCOLATE', 'LUKER', 'COBERTURA',
            'MILO', 'CAPPUCCINO', 'MOKACCINO'
        ],
        'Lácteos': [
            'LECHE', 'QUESO', 'YOGUR', 'YOGURT', 'CREMA DE LECHE',
            'MANTEQUILLA', 'KUMIS', 'AREQUIPE', 'KLIM', 'CONDENSADA',
            'MARGARINA', 'MARG.', 'LACTEA', 'LECHERA'
        ],
        'Bebidas': [
            'JUGO', 'NECTAR', 'REFRESCO', 'GASEOSA', 'TANG',
            'CLIGHT', 'BEBIDA', 'WATER', 'AGUA', 'LIMONADA',
            'NARANJADA', 'TE ', 'TEA', 'TISANA'
        ],
        'Congelados': [
            'CONGELAD', 'FROZEN', 'HELADO', 'HIELO', 'PAPA FRIT',
            'PAPAS A LA', 'NUGGET', 'APANADO', 'PRECOCID'
        ],
        'Enlatados y Conservas': [
            'ATUN', 'ATÚN', 'SARDINA', 'ENLATAD', 'CONSERVA',
            'ACEITUNA', 'CEREZA', 'MARASCHINO', 'ALCAPARRA',
            'PEPINILLO', 'ENCURTIDO', 'CERNIDO', 'PULPA'
        ],
        'Salsas y Condimentos': [
            'SALSA', 'MAYONESA', 'MOSTAZA', 'KETCHUP', 'VINAGRE',
            'CALDO', 'SAZON', 'SAZÓN', 'PIMIENTA', 'ESPECIAS',
            'ADOBO', 'CURRY', 'COMINO', 'BBQ'
        ],
        'Aceites y Grasas': [
            'ACEITE', 'OLIVA', 'GIRASOL', 'VEGETAL', 'CANOLA',
            'MANTECA', 'GRASA'
        ],
        'Panadería y Repostería': [
            'HARINA', 'H.RICAMASA', 'LEVADURA', 'LEVAPAN',
            'TORTA', 'PONQUE', 'PREMEZCLA', 'POLVO HORNEAR',
            'GELATINA', 'GEL SIN SABOR', 'FLAN', 'NATILLA'
        ],
        'Dulces y Confitería': [
            'DULCE', 'CARAMELO', 'GALLETA', 'BOCADILLO',
            'MERMELADA', 'MIEL', 'AZUCAR', 'AZÚCAR', 'PANELA',
            'GUAYABA', 'AREQUIPE', 'MANJAR', 'OBLEAS', 'COCO ARTESANAL',
            'OREO', 'CHIPS AHOY', 'CLUB SOCIAL', 'FESTIVAL', 'NUCITA'
        ],
        'Cereales y Granos': [
            'CEREAL', 'AVENA', 'ZUCARITAS', 'CORN FLAKES', 'KELLOGG',
            'GRANOLA', 'ARROZ', 'LENTEJA', 'FRIJOL', 'GARBANZO',
            'CHOCAPIC', 'FITNESS'
        ],
        'Carnes y Embutidos': [
            'CARNE', 'POLLO', 'CERDO', 'RES', 'JAMON', 'JAMÓN',
            'SALCHICHA', 'CHORIZO', 'TOCINETA', 'BACON', 'MORTADELA',
            'SALAMI', 'HAMBURGUESA'
        ],
        'Frutas y Verduras': [
            'FRUTA', 'VERDURA', 'SETA', 'CHAMPIÑON', 'CHAMPIÑÓN',
            'HONGO', 'PIÑA', 'MANGO', 'FRESA', 'MORA', 'DURAZNO',
            'TOMATE', 'CEBOLLA', 'MAIZ', 'MAÍZ', 'ARVEJA'
        ],
        'Limpieza y Hogar': [
            'DETERGENTE', 'DET.', 'JABON', 'JABÓN', 'LIMPIA',
            'LAVALOZA', 'DESINFECT', 'CLORO', 'BLANQUEADOR',
            'SUAVIZANTE', 'GRANDIOSO', 'POPOURRI', 'LAVANDA', 'FASSI'
        ],
        'Empaques y Desechables': [
            'EMPAQUE', 'PAPEL', 'WRAP', 'CONTENEDOR', 'VASO',
            'PLATO', 'CUCHARA', 'TENEDOR', 'SERVILLETA', 'BOLSA',
            'ALUMINIO', 'FILM', 'STRETCH', 'DESECHABLE'
        ],
    }

    for category, keywords in categories.items():
        for keyword in keywords:
            if keyword in name_upper:
                return category

    return 'Otros'


def main():
    """Main function to process all files and generate JSON."""
    print("Lacteos Buenos Aires - Building product catalog...")
    print("=" * 50)

    # Create site directory if it doesn't exist
    OUTPUT_FILE.parent.mkdir(exist_ok=True)

    # Find all Excel files
    excel_files = list(PORTFOLIO_DIR.glob("*.xlsx")) + \
                  list(PORTFOLIO_DIR.glob("*.xls")) + \
                  list(PORTFOLIO_DIR.glob("*.ods"))

    print(f"Found {len(excel_files)} portfolio files\n")

    all_products = []
    brands = set()

    for filepath in sorted(excel_files):
        products = process_excel_file(filepath)
        for p in products:
            p['category'] = categorize_product(p['name'])
            brands.add(p['brand'])
        all_products.extend(products)

    # Sort products by brand, then by name
    all_products.sort(key=lambda x: (x['brand'], x['name']))

    # Get unique categories
    categories = sorted(set(p['category'] for p in all_products))

    # Create output data
    output = {
        'products': all_products,
        'brands': sorted(brands),
        'categories': categories,
        'total_products': len(all_products)
    }

    # Write JSON file
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 50)
    print(f"Generated {OUTPUT_FILE}")
    print(f"Total products: {len(all_products)}")
    print(f"Brands: {len(brands)}")
    print(f"Categories: {len(categories)}")
    print("\nTo update the catalog, modify your Excel files and run:")
    print("  python3 build.py")


if __name__ == "__main__":
    main()
