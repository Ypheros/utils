#!/usr/bin/env python3
"""
Utility script to generate .pyi stub files from TOML configuration.
Run this to create autocomplete support for your project context.
"""

import sys
import os
from pathlib import Path

# Add utils to path so we can import our functions
sys.path.insert(0, str(Path(__file__).parent))

from utils.core.context import generate_config_stub

def main():
    """Generate stub file from TOML configuration."""
    
    # You can modify these paths as needed
    toml_path = input("Enter path to your TOML config file: ").strip()
    if not toml_path:
        print("❌ No TOML path provided")
        return
    
    # Check if file exists
    if not os.path.exists(toml_path):
        print(f"❌ File not found: {toml_path}")
        return
    
    # Generate stub
    stub_path = input("Enter output path for .pyi file (or press Enter for 'config.pyi'): ").strip()
    if not stub_path:
        stub_path = "config.pyi"
    
    try:
        generate_config_stub(toml_path, stub_path)
        print(f"\n🎉 Success! Now you can:")
        print(f"1. Copy {stub_path} to your Databricks workspace")
        print(f"2. Import: from config import ProjectContext")
        print(f"3. Enjoy full autocomplete! 🚀")
        
    except Exception as e:
        print(f"❌ Error generating stub: {e}")

if __name__ == "__main__":
    main()