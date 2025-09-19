""" 
    This script creates the cleanest import structure for Fibery. It will:

        Flatten your nested folder structure
        Fix all attachment paths
        Create a single attachments folder
        Generate import instructions
        Make everything ready for Fibery's markdown import

    py restructure_md_space_import_for_fibery_import.py ./confluence_export/3OV ./fibery_ready/3OV
"""

import os
import shutil
import re
from pathlib import Path

def prepare_for_fibery(input_dir, output_dir):
    """Prepare confluence export for Fibery import"""
    
    # Create output directories
    os.makedirs(output_dir, exist_ok=True)
    pages_dir = os.path.join(output_dir, "pages")
    attachments_dir = os.path.join(output_dir, "attachments")
    os.makedirs(pages_dir, exist_ok=True)
    os.makedirs(attachments_dir, exist_ok=True)
    
    # Copy all attachments to single folder
    print("Copying attachments...")
    attachment_count = 0
    for root, dirs, files in os.walk(input_dir):
        if 'attachments' in root:
            for file in files:
                if not file.endswith('.md'):  # Skip markdown files
                    src = os.path.join(root, file)
                    dst = os.path.join(attachments_dir, file)
                    
                    # Handle duplicate filenames
                    if os.path.exists(dst):
                        name, ext = os.path.splitext(file)
                        counter = 1
                        while os.path.exists(dst):
                            new_name = f"{name}_{counter}{ext}"
                            dst = os.path.join(attachments_dir, new_name)
                            counter += 1
                    
                    shutil.copy2(src, dst)
                    attachment_count += 1
    
    print(f"Copied {attachment_count} attachments")
    
    # Process all markdown files
    print("Processing markdown files...")
    page_count = 0
    
    for root, dirs, files in os.walk(input_dir):
        for file in files:
            if file.endswith('.md') and file != 'README.md':
                src_path = os.path.join(root, file)
                
                # Create unique filename based on path
                rel_path = os.path.relpath(src_path, input_dir)
                safe_name = rel_path.replace('\\', '_').replace('/', '_').replace(' ', '_')
                
                # Read and fix content
                with open(src_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                
                # Fix attachment paths - change relative paths to just filenames
                content = re.sub(r'attachments/([^)]+)', r'../attachments/\1', content)
                
                # Add space info to metadata if missing
                if 'space_key:' not in content:
                    # Try to extract space from path
                    if '3OV' in src_path:
                        space_key = '3OV'
                    elif 'GEOV' in src_path:
                        space_key = 'GEOV'
                    else:
                        space_key = 'UNKNOWN'
                    
                    # Add space to existing metadata
                    content = re.sub(r'(---\ntitle: [^\n]+\n)', f'\\1space: {space_key}\n', content)
                
                # Write to pages directory
                dst_path = os.path.join(pages_dir, safe_name)
                with open(dst_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                
                page_count += 1
    
    print(f"Processed {page_count} pages")
    
    # Create index file for Fibery
    index_content = f"""# Confluence Import

## Summary
- **Pages**: {page_count}
- **Attachments**: {attachment_count}

## Structure
- `pages/` - All markdown files (flattened)
- `attachments/` - All images and files

## Import Instructions
1. Zip this entire folder
2. In Fibery: Apps & Integrations -> Import -> Import from Markdown
3. Upload the zip file
4. Choose "Create new database" or select existing one
5. Map fields as needed

## Notes
- Attachment paths have been adjusted for Fibery compatibility
- All pages are flattened to avoid nested folder issues
- Original hierarchy is preserved in file names and metadata
"""
    
    with open(os.path.join(output_dir, "README.md"), 'w') as f:
        f.write(index_content)
    
    print(f"\n✓ Fibery import prepared in: {output_dir}")
    print(f"✓ {page_count} pages in pages/")
    print(f"✓ {attachment_count} attachments in attachments/")
    print(f"✓ Ready to zip and import to Fibery!")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) != 3:
        print("Usage: py restructure_for_fibery_import.py <input_dir> <output_dir>")
        print("Example: py restructure_md_space_import_for_fibery_import.py ./confluence_export/3OV ./fibery_ready/3OV")
        sys.exit(1)
    
    input_dir = sys.argv[1]
    output_dir = sys.argv[2]
    
    prepare_for_fibery(input_dir, output_dir)