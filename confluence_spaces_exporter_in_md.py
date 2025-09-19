#!/usr/bin/env python3
"""
Enhanced Confluence Space Scraper - Export spaces to Markdown with attachments and images
Scrapes Confluence spaces, downloads attachments, and preserves images and tables
"""

import requests
from bs4 import BeautifulSoup
from markdownify import markdownify as md
import os
import re
import json
import time
from urllib.parse import urljoin, urlparse
import logging
from pathlib import Path
import base64

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class EnhancedConfluenceScraper:
    def __init__(self, base_url, username, password):
        self.base_url = base_url
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        
    def login_with_api_token(self, api_token):
        """Login using API token (recommended for Confluence Cloud)"""
        logger.info("Setting up API token authentication...")
        
        # Set up basic auth with email and API token
        self.session.auth = (self.username, api_token)
        
        # Test authentication by trying to access a simple API endpoint
        test_url = f"{self.base_url}/rest/api/space"
        response = self.session.get(test_url)
        
        if response.status_code == 200:
            logger.info("API token authentication successful!")
            return True
        else:
            logger.error(f"API token authentication failed: {response.status_code}")
            return False
    
    def get_available_spaces(self):
        """Get list of all available spaces the user has access to"""
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
        """Get all pages in a space using the REST API"""
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
                'expand': 'ancestors,space,version,body.storage',
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
            time.sleep(0.5)  # Be nice to the server
            
        logger.info(f"Found {len(all_pages)} pages in space {space_key}")
        return all_pages
    
    def get_page_attachments(self, page_id):
        """Get all attachments for a specific page"""
        api_url = f"{self.base_url}/rest/api/content/{page_id}/child/attachment"
        params = {
            'expand': 'version,metadata.mediaType,container,_links.download',
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
            
            # Try multiple download URL formats for Confluence Cloud
            download_urls = [
                # Format 1: Direct download link from _links
                attachment.get('_links', {}).get('download'),
                # Format 2: Standard attachment data endpoint
                f"{self.base_url}/rest/api/content/{attachment_id}/data",
                # Format 3: Alternative download format
                f"{self.base_url.replace('/wiki', '')}/wiki/download/attachments/{attachment.get('container', {}).get('id', '')}/{filename}",
                # Format 4: Confluence Cloud specific format
                f"{self.base_url.replace('/wiki', '')}/download/attachments/{attachment.get('container', {}).get('id', '')}/{filename}"
            ]
            
            # Remove None values
            download_urls = [url for url in download_urls if url]
            
            response = None
            successful_url = None
            
            # Try each URL until one works
            for url in download_urls:
                try:
                    response = self.session.get(url, stream=True)
                    if response.status_code == 200:
                        successful_url = url
                        break
                except Exception as e:
                    continue
            
            if not response or response.status_code != 200:
                logger.warning(f"Could not download attachment {filename} - all URLs failed")
                return None
            
            # Create attachments directory
            attachments_dir = os.path.join(output_dir, 'attachments')
            os.makedirs(attachments_dir, exist_ok=True)
            
            # Clean filename for filesystem
            safe_filename = self.clean_filename(filename)
            file_path = os.path.join(attachments_dir, safe_filename)
            
            # Save file
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            logger.info(f"Downloaded attachment: {filename}")
            return file_path
            
        except Exception as e:
            logger.error(f"Failed to download attachment {filename}: {e}")
            return None
    
    def clean_filename(self, filename):
        """Clean filename for filesystem compatibility"""
        # Remove/replace invalid characters
        filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
        filename = re.sub(r'\s+', '_', filename)
        filename = filename.strip('._')
        
        # Limit length
        if len(filename) > 100:
            filename = filename[:100]
            
        return filename
    
    def process_confluence_content(self, content_html, page_id, output_dir, attachments_map):
        """Process Confluence-specific content elements"""
        if not content_html:
            return ""
        
        soup = BeautifulSoup(content_html, 'html.parser')
        
        # Handle Confluence image macros
        for img_macro in soup.find_all('ac:image'):
            attachment_elem = img_macro.find('ri:attachment')
            if attachment_elem:
                filename = attachment_elem.get('ri:filename')
                if filename and filename in attachments_map:
                    # Replace with markdown image syntax
                    rel_path = f"attachments/{filename}"
                    img_tag = soup.new_tag('img', src=rel_path, alt=filename)
                    img_macro.replace_with(img_tag)
                else:
                    # Keep as text reference if file not found
                    img_macro.replace_with(f"[Image: {filename}]" if filename else "[Image: Missing]")
        
        # Handle attachment macros
        for attachment_macro in soup.find_all('ac:link'):
            attachment_elem = attachment_macro.find('ri:attachment')
            if attachment_elem:
                filename = attachment_elem.get('ri:filename')
                if filename and filename in attachments_map:
                    # Replace with markdown link
                    rel_path = f"attachments/{filename}"
                    link_text = attachment_macro.get_text() or filename
                    link_tag = soup.new_tag('a', href=rel_path)
                    link_tag.string = link_text
                    attachment_macro.replace_with(link_tag)
        
        # Handle structured macros (info boxes, code blocks, etc.)
        for macro in soup.find_all('ac:structured-macro'):
            macro_name = macro.get('ac:name', '')
            
            if macro_name == 'info':
                # Convert info macros to markdown
                title_param = macro.find('ac:parameter', {'ac:name': 'title'})
                body = macro.find('ac:rich-text-body')
                
                title = title_param.get_text() if title_param else "Info"
                content = body.get_text() if body else ""
                
                info_text = f"\n> **{title}**\n> {content}\n"
                macro.replace_with(BeautifulSoup(f"<div>{info_text}</div>", 'html.parser'))
            
            elif macro_name == 'code':
                # Convert code macros
                language_param = macro.find('ac:parameter', {'ac:name': 'language'})
                body = macro.find('ac:plain-text-body')
                
                language = language_param.get_text() if language_param else ""
                code_content = body.get_text() if body else ""
                
                code_block = f"```{language}\n{code_content}\n```"
                macro.replace_with(BeautifulSoup(f"<pre>{code_block}</pre>", 'html.parser'))
            
            elif macro_name == 'toc':
                # Table of contents
                macro.replace_with(BeautifulSoup("<div>[Table of Contents]</div>", 'html.parser'))
            
            else:
                # Generic macro handling
                macro_text = f"[Macro: {macro_name}]"
                body = macro.find('ac:rich-text-body')
                if body:
                    macro_text += f" {body.get_text()}"
                macro.replace_with(BeautifulSoup(f"<div>{macro_text}</div>", 'html.parser'))
        
        # Remove remaining Confluence-specific elements
        for element in soup.find_all(['ac:parameter', 'ri:attachment', 'ac:plain-text-body']):
            element.decompose()
        
        # Convert relative links to absolute
        for link in soup.find_all('a', href=True):
            href = link['href']
            if href.startswith('/'):
                link['href'] = urljoin(self.base_url, href)
        
        return str(soup)
    
    def extract_page_content(self, page_data, output_dir, attachments_map):
        """Extract and clean page content with enhanced processing"""
        title = page_data['title']
        page_id = page_data['id']
        
        # Get content from storage format (raw HTML)
        body_storage = page_data.get('body', {}).get('storage', {})
        content_html = body_storage.get('value', '')
        
        if not content_html:
            logger.warning(f"No content found for page: {title}")
            return title, ""
        
        # Process Confluence-specific content
        processed_html = self.process_confluence_content(content_html, page_id, output_dir, attachments_map)
        
        # Convert to markdown with better table handling
        markdown_content = md(
            processed_html,
            heading_style="ATX",
            bullets="-",
            strip=['script', 'style'],
            escape_misc=False   # Don't escape common characters
        )
        
        # Clean up markdown
        markdown_content = re.sub(r'\n{3,}', '\n\n', markdown_content)
        markdown_content = re.sub(r'\\n', '\n', markdown_content)  # Fix double escapes
        markdown_content = markdown_content.strip()
        
        return title, markdown_content
    
    def build_hierarchy(self, pages):
        """Build page hierarchy based on ancestors"""
        hierarchy = {}
        page_lookup = {page['id']: page for page in pages}
        
        for page in pages:
            page_id = page['id']
            ancestors = page.get('ancestors', [])
            
            # Build path from ancestors
            path = []
            for ancestor in ancestors:
                if ancestor['id'] in page_lookup:
                    path.append(ancestor['title'])
            
            path.append(page['title'])
            hierarchy[page_id] = {
                'page': page,
                'path': path,
                'level': len(ancestors)
            }
            
        return hierarchy
    
    def save_page(self, page_data, output_dir, path, attachments_map):
        """Save individual page as markdown with metadata"""
        title, content = self.extract_page_content(page_data, output_dir, attachments_map)
        
        # Create directory structure
        if len(path) > 1:
            dir_path = os.path.join(output_dir, *[self.clean_filename(p) for p in path[:-1]])
            os.makedirs(dir_path, exist_ok=True)
            file_path = os.path.join(dir_path, f"{self.clean_filename(path[-1])}.md")
        else:
            file_path = os.path.join(output_dir, f"{self.clean_filename(title)}.md")
        
        # Add metadata header
        metadata = f"""---
title: {title}
confluence_id: {page_data['id']}
space_key: {page_data['space']['key']}
created: {page_data['version']['when']}
path: {' > '.join(path)}
---

"""
        
        full_content = metadata + content
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(full_content)
            
        logger.info(f"Saved page: {title}")
        return file_path
    
    def scrape_space(self, space_key, output_dir):
        """Scrape entire space with attachments"""
        logger.info(f"Scraping space: {space_key}")
        
        # Create output directory
        space_output_dir = os.path.join(output_dir, space_key)
        os.makedirs(space_output_dir, exist_ok=True)
        
        # Get all pages
        pages = self.get_space_pages(space_key)
        
        if not pages:
            logger.error(f"No pages found for space {space_key}")
            return []
        
        # Download all attachments first
        logger.info(f"Downloading attachments for {len(pages)} pages...")
        all_attachments = {}
        total_attachments = 0
        
        for i, page in enumerate(pages, 1):
            page_id = page['id']
            page_title = page['title']
            attachments = self.get_page_attachments(page_id)
            
            if attachments:
                logger.info(f"  [{i}/{len(pages)}] {page_title}: {len(attachments)} attachments")
                for attachment in attachments:
                    filename = attachment['title']
                    file_path = self.download_attachment(attachment, space_output_dir)
                    if file_path:
                        all_attachments[filename] = file_path
                        total_attachments += 1
            
            time.sleep(0.2)  # Rate limiting
        
        logger.info(f"Downloaded {total_attachments} attachments total")
        
        # Build hierarchy
        logger.info(f"Building page hierarchy...")
        hierarchy = self.build_hierarchy(pages)
        
        # Save all pages
        logger.info(f"Converting and saving {len(pages)} pages to markdown...")
        saved_files = []
        
        # Sort by hierarchy level and title
        sorted_pages = sorted(hierarchy.values(), key=lambda x: (x['level'], x['path']))
        
        for i, item in enumerate(sorted_pages, 1):
            page = item['page']
            path = item['path']
            
            # Save page
            try:
                logger.info(f"  [{i}/{len(pages)}] Saving: {page['title']}")
                file_path = self.save_page(page, space_output_dir, path, all_attachments)
                saved_files.append(file_path)
                time.sleep(0.1)  # Reduced rate limiting for page processing
            except Exception as e:
                logger.error(f"Failed to save page {page['title']}: {e}")
        
        # Save index file
        index_content = f"# {space_key} Space Export\n\n"
        index_content += f"Exported {len(pages)} pages and {total_attachments} attachments\n\n"
        
        if all_attachments:
            index_content += "## Attachments:\n\n"
            for filename in sorted(all_attachments.keys()):
                index_content += f"- [{filename}](./attachments/{filename})\n"
            index_content += "\n"
        
        index_content += "## Page Hierarchy:\n\n"
        
        for item in sorted_pages:
            page = item['page']
            path = item['path']
            level = item['level']
            
            # Add to index
            indent = "  " * level
            page_link = '/'.join([self.clean_filename(p) for p in path])
            index_content += f"{indent}- [{page['title']}](./{page_link}.md)\n"
        
        # Save index
        with open(os.path.join(space_output_dir, "README.md"), 'w', encoding='utf-8') as f:
            f.write(index_content)
        
        # Create attachments summary
        if all_attachments:
            att_summary = "# Attachments Summary\n\n"
            for filename, filepath in all_attachments.items():
                file_size = os.path.getsize(filepath) if os.path.exists(filepath) else 0
                att_summary += f"- **{filename}** ({file_size:,} bytes)\n"
            
            with open(os.path.join(space_output_dir, "attachments", "README.md"), 'w', encoding='utf-8') as f:
                f.write(att_summary)
        
        logger.info(f"Space {space_key} complete! Saved {len(saved_files)} pages and {total_attachments} attachments")
        return saved_files

def select_spaces(scraper):
    """Interactive space selection"""
    print("\n" + "="*50)
    print("SPACE SELECTION")
    print("="*50)
    
    # Get available spaces
    spaces = scraper.get_available_spaces()
    
    if not spaces:
        print("No spaces found or accessible!")
        return []
    
    # Display spaces in a nice table
    print(f"\nFound {len(spaces)} accessible spaces:\n")
    print(f"{'#':<3} {'Key':<15} {'Name':<40}")
    print("-" * 65)
    
    for i, space in enumerate(spaces, 1):
        space_key = space['key']
        space_name = space['name'][:38] + "..." if len(space['name']) > 40 else space['name']
        print(f"{i:<3} {space_key:<15} {space_name:<40}")
    
    print("\n" + "="*65)
    
    # Get user selection
    print("\nSELECT SPACES TO EXPORT:")
    print("Options:")
    print("  • Enter space keys separated by spaces (e.g., '3OV GEOV CI')")
    print("  • Enter numbers separated by spaces (e.g., '1 3 5')")
    print("  • Type 'all' to export all spaces")
    
    while True:
        selection = input("\nYour selection: ").strip()
        
        if not selection:
            print("Please enter a selection")
            continue
        
        selected_spaces = []
        
        if selection.lower() == 'all':
            selected_spaces = [space['key'] for space in spaces]
            break
        
        # Split by spaces
        parts = selection.split()
        
        # Check if all parts are numbers
        if all(part.isdigit() for part in parts):
            # Number selection
            try:
                indices = [int(part) for part in parts]
                
                # Validate indices
                invalid_indices = [i for i in indices if i < 1 or i > len(spaces)]
                if invalid_indices:
                    print(f"Invalid numbers: {invalid_indices}")
                    print(f"Valid range: 1-{len(spaces)}")
                    continue
                
                selected_spaces = [spaces[i-1]['key'] for i in indices]
                break
                
            except ValueError:
                print("Invalid number format")
                continue
        else:
            # Assume space keys
            keys = [key.strip().upper() for key in parts]
            space_keys = [space['key'] for space in spaces]
            
            invalid_keys = [key for key in keys if key not in space_keys]
            if invalid_keys:
                print(f"Invalid space keys: {', '.join(invalid_keys)}")
                print(f"Available keys: {', '.join(space_keys[:10])}{'...' if len(space_keys) > 10 else ''}")
                continue
            
            selected_spaces = keys
            break
    
    # Confirm selection
    print(f"\nSelected {len(selected_spaces)} spaces:")
    for key in selected_spaces:
        space = next((s for s in spaces if s['key'] == key), {'name': 'Unknown'})
        print(f"  • {key} - {space['name']}")
    
    confirm = input(f"\nProceed with exporting these {len(selected_spaces)} spaces? (y/N): ").strip().lower()
    
    if confirm in ['y', 'yes']:
        return selected_spaces
    else:
        print("Export cancelled")
        return []

def main():
    print("Enhanced Confluence Space Scraper")
    print("Downloads pages, attachments, images, and preserves formatting")
    print()
    
    # Get base URL
    default_base = "https://cradlebuas.atlassian.net/wiki"
    base_url = input(f"Confluence base URL (this defaults to what works with CRADLE BUas ->: {default_base} (just press enter if you want this)): ").strip() or default_base
    
    print("\nAPI Token Required:")
    print("Create one at: https://id.atlassian.com/manage-profile/security/api-tokens")
    print()
    
    username = input("Enter your email: ").strip().strip('"\'')
    api_token = input("Enter your API token: ").strip().strip('"\'')
    
    if not username or not api_token:
        print("Email and API token are required!")
        return
    
    # Initialize scraper
    scraper = EnhancedConfluenceScraper(base_url, username, "")
    
    # Login with API token
    print("\nAuthenticating...")
    if not scraper.login_with_api_token(api_token):
        print("Authentication failed! Check your credentials.")
        return
    
    print("Authentication successful!")
    
    # Select spaces to scrape
    selected_spaces = select_spaces(scraper)
    
    if not selected_spaces:
        return
    
    # Get output directory
    default_output = "confluence_export"
    output_dir = input(f"\nOutput directory (default: {default_output}): ").strip() or default_output
    
    # Create main output directory
    os.makedirs(output_dir, exist_ok=True)
    
    print(f"\nStarting export to: {os.path.abspath(output_dir)}")
    print("="*60)
    
    # Scrape each space
    total_files = 0
    successful_spaces = []
    failed_spaces = []
    
    for i, space_key in enumerate(selected_spaces, 1):
        try:
            print(f"\n[{i}/{len(selected_spaces)}] Processing space: {space_key}")
            files = scraper.scrape_space(space_key, output_dir)
            if files:
                total_files += len(files)
                successful_spaces.append(space_key)
                print(f"✓ {space_key}: {len(files)} pages exported")
            else:
                failed_spaces.append(space_key)
                print(f"✗ {space_key}: No pages exported")
        except Exception as e:
            logger.error(f"Failed to scrape space {space_key}: {e}")
            failed_spaces.append(space_key)
            print(f"✗ {space_key}: Export failed - {str(e)}")
    
    # Final summary
    print("\n" + "="*60)
    print("EXPORT SUMMARY")
    print("="*60)
    print(f"Total pages exported: {total_files}")
    print(f"Successful spaces ({len(successful_spaces)}): {', '.join(successful_spaces)}")
    
    if failed_spaces:
        print(f"Failed spaces ({len(failed_spaces)}): {', '.join(failed_spaces)}")
    
    print(f"\nFiles saved to: {os.path.abspath(output_dir)}")
    print("\nEach space contains:")
    print("  • README.md (index with navigation)")
    print("  • Individual page .md files")
    print("  • attachments/ folder with images and files")
    print("\nReady to import into Fibery!")

if __name__ == "__main__":
    main()