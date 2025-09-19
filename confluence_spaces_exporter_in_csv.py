#!/usr/bin/env python3
"""
Enhanced Confluence Space Scraper - Direct CSV Export for Fibery
Scrapes Confluence spaces and outputs structured CSV data with attachments
"""

import requests
from bs4 import BeautifulSoup
from markdownify import markdownify as md
import os
import re
import csv
import time
from urllib.parse import urljoin, urlparse
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ConfluenceCSVScraper:
    def __init__(self, base_url, username, password):
        self.base_url = base_url
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        
    def login_with_api_token(self, api_token):
        """Login using API token"""
        logger.info("Setting up API token authentication...")
        
        self.session.auth = (self.username, api_token)
        
        test_url = f"{self.base_url}/rest/api/space"
        response = self.session.get(test_url)
        
        if response.status_code == 200:
            logger.info("API token authentication successful!")
            return True
        else:
            logger.error(f"API token authentication failed: {response.status_code}")
            return False
    
    def get_available_spaces(self):
        """Get list of all available spaces"""
        logger.info("Fetching available spaces...")
        
        api_url = f"{self.base_url}/rest/api/space"
        params = {
            'limit': 200,
            'expand': 'description.plain,homepage'
        }
        
        all_spaces = []
        start = 0
        
        while True:
            params['start'] = start
            response = self.session.get(api_url, params=params)
            
            if response.status_code != 200:
                logger.error(f"Failed to fetch spaces: {response.status_code}")
                return []
            
            data = response.json()
            spaces = data.get('results', [])
            
            if not spaces:
                break
                
            all_spaces.extend(spaces)
            
            if len(spaces) < params['limit']:
                break
                
            start += params['limit']
        
        logger.info(f"Found {len(all_spaces)} accessible spaces")
        return all_spaces
    
    def get_space_pages(self, space_key):
        """Get all pages in a space with full metadata"""
        logger.info(f"Fetching pages for space: {space_key}")
        
        all_pages = []
        start = 0
        limit = 50
        
        while True:
            api_url = f"{self.base_url}/rest/api/content"
            params = {
                'spaceKey': space_key,
                'type': 'page',
                'status': 'current',
                'expand': 'ancestors,space,version,body.storage,history,metadata.labels',
                'start': start,
                'limit': limit
            }
            
            response = self.session.get(api_url, params=params)
            
            if response.status_code != 200:
                logger.error(f"Failed to fetch pages: {response.status_code}")
                break
                
            data = response.json()
            pages = data.get('results', [])
            
            if not pages:
                break
                
            all_pages.extend(pages)
            
            if len(pages) < limit:
                break
                
            start += limit
            time.sleep(0.5)
            
        logger.info(f"Found {len(all_pages)} pages in space {space_key}")
        return all_pages
    
    def get_page_attachments(self, page_id):
        """Get all attachments for a specific page with metadata"""
        api_url = f"{self.base_url}/rest/api/content/{page_id}/child/attachment"
        params = {
            'expand': 'version,metadata.mediaType,container,_links.download,history',
            'limit': 200
        }
        
        response = self.session.get(api_url, params=params)
        
        if response.status_code != 200:
            logger.error(f"Failed to fetch attachments for page {page_id}: {response.status_code}")
            return []
            
        data = response.json()
        attachments = data.get('results', [])
        
        return attachments
    
    def download_attachment(self, attachment, output_dir):
        """Download a single attachment"""
        try:
            attachment_id = attachment['id']
            filename = attachment['title']
            
            download_urls = [
                attachment.get('_links', {}).get('download'),
                f"{self.base_url}/rest/api/content/{attachment_id}/data",
                f"{self.base_url.replace('/wiki', '')}/wiki/download/attachments/{attachment.get('container', {}).get('id', '')}/{filename}",
                f"{self.base_url.replace('/wiki', '')}/download/attachments/{attachment.get('container', {}).get('id', '')}/{filename}"
            ]
            
            download_urls = [url for url in download_urls if url]
            
            response = None
            successful_url = None
            
            for url in download_urls:
                try:
                    response = self.session.get(url, stream=True)
                    if response.status_code == 200:
                        successful_url = url
                        break
                except Exception as e:
                    continue
            
            if not response or response.status_code != 200:
                logger.warning(f"Could not download attachment {filename}")
                return None
            
            # Create attachments directory
            attachments_dir = os.path.join(output_dir, 'attachments')
            os.makedirs(attachments_dir, exist_ok=True)
            
            # Clean filename for filesystem
            safe_filename = self.clean_filename(filename)
            file_path = os.path.join(attachments_dir, safe_filename)
            
            # Handle duplicates
            counter = 1
            original_path = file_path
            while os.path.exists(file_path):
                name, ext = os.path.splitext(original_path)
                file_path = f"{name}_{counter}{ext}"
                counter += 1
            
            # Save file
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            logger.info(f"Downloaded: {filename}")
            return file_path
            
        except Exception as e:
            logger.error(f"Failed to download attachment {filename}: {e}")
            return None
    
    def clean_filename(self, filename):
        """Clean filename for filesystem compatibility"""
        filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
        filename = re.sub(r'\s+', '_', filename)
        filename = filename.strip('._')
        
        if len(filename) > 100:
            filename = filename[:100]
            
        return filename
    
    def process_content_to_markdown(self, content_html):
        """Convert Confluence storage format to clean markdown"""
        if not content_html:
            return ""
        
        soup = BeautifulSoup(content_html, 'html.parser')
        
        # Handle Confluence macros
        for macro in soup.find_all('ac:structured-macro'):
            macro_name = macro.get('ac:name', '')
            
            if macro_name == 'info':
                title_param = macro.find('ac:parameter', {'ac:name': 'title'})
                body = macro.find('ac:rich-text-body')
                
                title = title_param.get_text() if title_param else "Info"
                content = body.get_text() if body else ""
                
                info_text = f"\n> **{title}**\n> {content}\n"
                macro.replace_with(BeautifulSoup(f"<div>{info_text}</div>", 'html.parser'))
            
            elif macro_name == 'code':
                language_param = macro.find('ac:parameter', {'ac:name': 'language'})
                body = macro.find('ac:plain-text-body')
                
                language = language_param.get_text() if language_param else ""
                code_content = body.get_text() if body else ""
                
                code_block = f"```{language}\n{code_content}\n```"
                macro.replace_with(BeautifulSoup(f"<pre>{code_block}</pre>", 'html.parser'))
            
            elif macro_name == 'toc':
                macro.replace_with(BeautifulSoup("<div>[Table of Contents]</div>", 'html.parser'))
            
            else:
                macro_text = f"[Macro: {macro_name}]"
                body = macro.find('ac:rich-text-body')
                if body:
                    macro_text += f" {body.get_text()}"
                macro.replace_with(BeautifulSoup(f"<div>{macro_text}</div>", 'html.parser'))
        
        # Handle images - keep as placeholders for now
        for img_macro in soup.find_all('ac:image'):
            attachment_elem = img_macro.find('ri:attachment')
            if attachment_elem:
                filename = attachment_elem.get('ri:filename', 'unknown')
                img_macro.replace_with(f"[Image: {filename}]")
            else:
                img_macro.replace_with("[Image: Missing]")
        
        # Handle attachment links
        for attachment_macro in soup.find_all('ac:link'):
            attachment_elem = attachment_macro.find('ri:attachment')
            if attachment_elem:
                filename = attachment_elem.get('ri:filename', 'unknown')
                link_text = attachment_macro.get_text() or filename
                attachment_macro.replace_with(f"[{link_text}]({filename})")
        
        # Remove remaining Confluence-specific elements
        for element in soup.find_all(['ac:parameter', 'ri:attachment', 'ac:plain-text-body']):
            element.decompose()
        
        # Convert to markdown
        markdown_content = md(
            str(soup),
            heading_style="ATX",
            bullets="-",
            strip=['script', 'style'],
            escape_misc=False
        )
        
        # Clean up markdown
        markdown_content = re.sub(r'\n{3,}', '\n\n', markdown_content)
        markdown_content = markdown_content.strip()
        
        return markdown_content
    
    def build_page_lookup(self, pages):
        """Create lookup tables for parent relationships"""
        page_lookup = {page['id']: page for page in pages}
        return page_lookup
    
    def get_parent_page_title(self, page, page_lookup):
        """Get the direct parent page title"""
        ancestors = page.get('ancestors', [])
        if not ancestors:
            return None
        
        # Get the direct parent (last ancestor)
        parent_id = ancestors[-1]['id']
        parent_page = page_lookup.get(parent_id)
        return parent_page['title'] if parent_page else None
    
    def scrape_space_to_csv(self, space_key, output_dir):
        """Scrape space and create CSV files"""
        logger.info(f"Scraping space {space_key} to CSV...")
        
        # Create output directory
        space_output_dir = os.path.join(output_dir, space_key)
        os.makedirs(space_output_dir, exist_ok=True)
        
        # Get all pages
        pages = self.get_space_pages(space_key)
        
        if not pages:
            logger.error(f"No pages found for space {space_key}")
            return []
        
        # Build page lookup
        page_lookup = self.build_page_lookup(pages)
        
        # Prepare pages data
        pages_data = []
        attachments_data = []
        
        logger.info(f"Processing {len(pages)} pages...")
        
        for i, page in enumerate(pages, 1):
            page_id = page['id']
            title = page['title']
            
            logger.info(f"  [{i}/{len(pages)}] Processing: {title}")
            
            # Get content
            body_storage = page.get('body', {}).get('storage', {})
            content_html = body_storage.get('value', '')
            content_markdown = self.process_content_to_markdown(content_html)
            
            # Get metadata
            version = page.get('version', {})
            space = page.get('space', {})
            
            # Get parent page
            parent_title = self.get_parent_page_title(page, page_lookup)
            
            # Build hierarchy path
            ancestors = page.get('ancestors', [])
            hierarchy_path = []
            for ancestor in ancestors:
                ancestor_page = page_lookup.get(ancestor['id'])
                if ancestor_page:
                    hierarchy_path.append(ancestor_page['title'])
            hierarchy_path.append(title)
            full_path = ' > '.join(hierarchy_path)
            
            # Add page data
            pages_data.append({
                'Name': title,
                'Content': content_markdown,
                'Project': space_key,
                'Parent Page': parent_title or '',
                'Confluence ID': page_id,
                'Space Name': space.get('name', ''),
                'Created Date': version.get('when', ''),
                'Created By': version.get('by', {}).get('displayName', ''),
                'Version': version.get('number', 1),
                'Hierarchy Path': full_path,
                'Hierarchy Level': len(ancestors),
                'Page URL': f"{self.base_url}/spaces/{space_key}/pages/{page_id}"
            })
            
            # Get attachments for this page
            attachments = self.get_page_attachments(page_id)
            
            for attachment in attachments:
                # Download attachment
                file_path = self.download_attachment(attachment, space_output_dir)
                
                # Get filename and determine file type FIRST
                filename = attachment['title']
                file_ext = os.path.splitext(filename)[1].lower()
                
                if file_ext in ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp']:
                    file_type = 'Image'
                elif file_ext in ['.pdf']:
                    file_type = 'PDF'
                elif file_ext in ['.docx', '.doc']:
                    file_type = 'Word Document'
                elif file_ext in ['.xlsx', '.xls']:
                    file_type = 'Excel Document'
                elif file_ext in ['.pptx', '.ppt']:
                    file_type = 'PowerPoint'
                elif file_ext in ['.zip', '.rar', '.7z']:
                    file_type = 'Archive'
                else:
                    file_type = 'Other'
                
                # Get attachment metadata
                version = attachment.get('version', {})
                metadata = attachment.get('metadata', {})
                
                # Safely get size - metadata might be a string or dict
                size_bytes = 0
                if isinstance(metadata, dict):
                    media_type = metadata.get('mediaType', {})
                    if isinstance(media_type, dict):
                        size_bytes = media_type.get('size', 0)
                
                # Safely get version info
                upload_date = ''
                uploaded_by = ''
                if isinstance(version, dict):
                    upload_date = version.get('when', '')
                    by_info = version.get('by', {})
                    if isinstance(by_info, dict):
                        uploaded_by = by_info.get('displayName', '')
                
                # Safely get download URL
                download_url = ''
                links = attachment.get('_links', {})
                if isinstance(links, dict):
                    download_url = links.get('download', '')
                
                attachments_data.append({
                    'Filename': filename,
                    'Page Name': title,
                    'Page ID': page_id,
                    'Project': space_key,
                    'File Type': file_type,
                    'Extension': file_ext,
                    'Attachment ID': attachment['id'],
                    'Size (Bytes)': size_bytes,
                    'Uploaded Date': upload_date,
                    'Uploaded By': uploaded_by,
                    'Local File Path': file_path or '',
                    'Download URL': download_url
                })
            
            time.sleep(0.1)  # Rate limiting
        
        # Write pages CSV
        pages_csv_path = os.path.join(space_output_dir, f'{space_key}_pages.csv')
        with open(pages_csv_path, 'w', newline='', encoding='utf-8') as f:
            if pages_data:
                writer = csv.DictWriter(f, fieldnames=pages_data[0].keys())
                writer.writeheader()
                writer.writerows(pages_data)
        
        # Write attachments CSV
        attachments_csv_path = os.path.join(space_output_dir, f'{space_key}_attachments.csv')
        with open(attachments_csv_path, 'w', newline='', encoding='utf-8') as f:
            if attachments_data:
                writer = csv.DictWriter(f, fieldnames=attachments_data[0].keys())
                writer.writeheader()
                writer.writerows(attachments_data)
        
        # Create import instructions
        instructions = f"""# Fibery Import Instructions - {space_key}

## Files Created:
- **{space_key}_pages.csv**: {len(pages_data)} pages with full metadata
- **{space_key}_attachments.csv**: {len(attachments_data)} attachments with metadata
- **attachments/**: Downloaded attachment files

## Import Process:

### 1. Import Pages to Fibery:
1. Go to Apps & Integrations -> Import -> CSV Import
2. Upload `{space_key}_pages.csv`
3. Create/Select database: "Confluence Pages" 
4. Map CSV columns to Fibery fields:
   - Name -> Title (Text)
   - Content -> Content (Rich Text) 
   - Project -> Space (Select/Text)
   - Parent Page -> Parent (Relation to same entity)
   - Confluence ID -> Original ID (Text)
   - Created Date -> Created (Date)
   - Created By -> Author (Text)
   - Hierarchy Path -> Full Path (Text)
   - Hierarchy Level -> Level (Number)

### 2. Import Attachments (Optional):
1. Upload `{space_key}_attachments.csv` 
2. Create database: "Attachments"
3. Link to Pages database via Page ID
4. Upload files from attachments/ folder manually

### 3. Post-Import:
- Fix parent-child relationships if needed
- Upload attachment files to Fibery
- Update image references in content

## Rich Metadata Preserved:
- Full page hierarchy with levels
- Original creation dates and authors  
- Version numbers
- Complete attachment metadata
- Direct parent-child relationships
- Original Confluence URLs

Total: {len(pages_data)} pages, {len(attachments_data)} attachments
"""
        
        instructions_path = os.path.join(space_output_dir, 'IMPORT_INSTRUCTIONS.md')
        with open(instructions_path, 'w', encoding='utf-8') as f:
            f.write(instructions)
        
        logger.info(f"Space {space_key} export complete!")
        logger.info(f"  Pages: {len(pages_data)}")
        logger.info(f"  Attachments: {len(attachments_data)}")
        
        return [pages_csv_path, attachments_csv_path]

def select_spaces(scraper):
    """Interactive space selection"""
    print("\n" + "="*50)
    print("CONFLUENCE TO CSV EXPORT")
    print("="*50)
    
    spaces = scraper.get_available_spaces()
    
    if not spaces:
        print("No spaces found!")
        return []
    
    print(f"\nFound {len(spaces)} accessible spaces:\n")
    print(f"{'#':<3} {'Key':<15} {'Name':<40}")
    print("-" * 65)
    
    for i, space in enumerate(spaces, 1):
        space_key = space['key']
        space_name = space['name'][:38] + "..." if len(space['name']) > 40 else space['name']
        print(f"{i:<3} {space_key:<15} {space_name:<40}")
    
    print("\nSELECT SPACES TO EXPORT:")
    print("  • Enter space keys: '3OV GEOV'")  
    print("  • Enter numbers: '1 3'")
    print("  • Type 'all' for everything")
    
    while True:
        selection = input("\nYour selection: ").strip()
        
        if not selection:
            continue
        
        if selection.lower() == 'all':
            selected_spaces = [space['key'] for space in spaces]
            break
        
        parts = selection.split()
        
        if all(part.isdigit() for part in parts):
            try:
                indices = [int(part) for part in parts]
                invalid_indices = [i for i in indices if i < 1 or i > len(spaces)]
                if invalid_indices:
                    print(f"Invalid numbers: {invalid_indices}")
                    continue
                selected_spaces = [spaces[i-1]['key'] for i in indices]
                break
            except ValueError:
                continue
        else:
            keys = [key.strip().upper() for key in parts]
            space_keys = [space['key'] for space in spaces]
            
            invalid_keys = [key for key in keys if key not in space_keys]
            if invalid_keys:
                print(f"Invalid space keys: {', '.join(invalid_keys)}")
                continue
            
            selected_spaces = keys
            break
    
    print(f"\nSelected {len(selected_spaces)} spaces:")
    for key in selected_spaces:
        space = next((s for s in spaces if s['key'] == key), {'name': 'Unknown'})
        print(f"  • {key} - {space['name']}")
    
    confirm = input(f"\nExport these spaces to CSV? (y/N): ").strip().lower()
    
    return selected_spaces if confirm in ['y', 'yes'] else []

def main():
    print("Confluence to CSV Direct Exporter")
    print("Creates structured CSV files optimized for Fibery import")
    print()
    
    # Get configuration
    default_base = "https://cradlebuas.atlassian.net/wiki"
    #base_url = input(f"Confluence URL (default: {default_base}): ").strip() or default_base
    base_url = input(f"Confluence base URL (this defaults to what works with CRADLE BUas ->: {default_base} (just press enter if you want this)): ").strip() or default_base
    
    print("\nAPI Token Required:")
    print("https://id.atlassian.com/manage-profile/security/api-tokens")
    
    username = input("\nEmail: ").strip()
    api_token = input("API Token: ").strip()
    
    if not username or not api_token:
        print("Email and API token required!")
        return
    
    # Initialize scraper
    scraper = ConfluenceCSVScraper(base_url, username, "")
    
    # Authenticate
    if not scraper.login_with_api_token(api_token):
        print("Authentication failed!")
        return
    
    # Select spaces
    selected_spaces = select_spaces(scraper)
    if not selected_spaces:
        return
    
    # Get output directory
    default_output = "confluence_csv_export"
    output_dir = input(f"\nOutput directory (default: {default_output}): ").strip() or default_output
    
    os.makedirs(output_dir, exist_ok=True)
    
    print(f"\nExporting to: {os.path.abspath(output_dir)}")
    print("="*60)
    
    # Export each space
    total_files = 0
    successful_spaces = []
    
    for i, space_key in enumerate(selected_spaces, 1):
        try:
            print(f"\n[{i}/{len(selected_spaces)}] Exporting space: {space_key}")
            files = scraper.scrape_space_to_csv(space_key, output_dir)
            
            if files:
                total_files += len(files)
                successful_spaces.append(space_key)
                print(f"✓ {space_key}: CSV files created")
            else:
                print(f"✗ {space_key}: Export failed")
                
        except Exception as e:
            logger.error(f"Failed to export space {space_key}: {e}")
            print(f"✗ {space_key}: Error - {str(e)}")
    
    # Summary
    print("\n" + "="*60)
    print("EXPORT COMPLETE")
    print("="*60)
    print(f"Successful spaces: {', '.join(successful_spaces)}")
    print(f"CSV files created: {total_files}")
    print(f"\nFiles saved to: {os.path.abspath(output_dir)}")
    print("\nReady for Fibery CSV import!")
    print("Follow the IMPORT_INSTRUCTIONS.md in each space folder.")

if __name__ == "__main__":
    main()