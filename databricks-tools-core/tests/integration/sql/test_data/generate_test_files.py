"""
Generate test files for volume folder integration tests.

Creates:
- parquet/: Parquet files with sample data
- txt_files/: Simple text files
"""

from pathlib import Path

import pandas as pd

# Get directory of this script
TEST_DATA_DIR = Path(__file__).parent


def generate_parquet_data():
    """Generate parquet files with sample data."""
    parquet_dir = TEST_DATA_DIR / "parquet"
    parquet_dir.mkdir(exist_ok=True)

    # Create sample data
    data = {
        "id": [1, 2, 3, 4, 5],
        "name": ["Alice", "Bob", "Charlie", "Diana", "Eve"],
        "age": [25, 30, 35, 28, 32],
        "salary": [50000.0, 60000.0, 75000.0, 55000.0, 80000.0],
        "department": ["Engineering", "Sales", "Engineering", "Marketing", "Sales"],
    }
    df = pd.DataFrame(data)

    # Save as parquet
    output_path = parquet_dir / "employees.parquet"
    df.to_parquet(output_path, index=False)
    print(f"Created: {output_path}")

    return parquet_dir


def generate_txt_files():
    """Generate text files for file listing tests."""
    txt_dir = TEST_DATA_DIR / "txt_files"
    txt_dir.mkdir(exist_ok=True)

    files = [
        ("readme.txt", "This is a test readme file.\nIt has multiple lines."),
        ("data.txt", "id,name,value\n1,foo,100\n2,bar,200\n3,baz,300"),
        ("notes.txt", "Some random notes for testing."),
    ]

    for filename, content in files:
        file_path = txt_dir / filename
        file_path.write_text(content)
        print(f"Created: {file_path}")

    return txt_dir


if __name__ == "__main__":
    print("Generating test data files...")
    generate_parquet_data()
    generate_txt_files()
    print("Done!")
