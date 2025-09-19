# Confluence Export Tools

A comprehensive set of Python scripts to extract content from Confluence spaces and prepare it for import into Fibery or other documentation systems.

## Overview

This toolkit provides three complementary approaches for migrating Confluence content:

1. **CSV Export of Confluence SPACE(S)** - Structured data export optimized for database imports
2. **Markdown Export of Confluence SPACE(S)** - Traditional file-based export with hierarchy preservation
3. **Markdown Restructuring** - Post-processing tool for flattening exports

## Scripts

### 1. `confluence_spaces_exporter_in_csv.py`
**Direct CSV Export for Database Import**

Exports Confluence spaces directly to CSV format with rich metadata, optimized for importing into database-driven systems like Fibery.

**Features:**
- Structured CSV output with relational data
- Rich metadata preservation (creation dates, authors, versions)
- Proper parent-child relationships using actual API data
- Hierarchy path tracking
- Enhanced attachment metadata
- Type-safe data handling

**Usage:**
```bash
py confluence_spaces_exporter_in_csv.py
```

**Output Structure:**
```
confluence_csv_export/
├── SPACE_KEY/
│   ├── SPACE_KEY_pages.csv
│   ├── SPACE_KEY_attachments.csv
│   ├── attachments/
│   │   └── [downloaded files]
│   └── IMPORT_INSTRUCTIONS.md
```

**CSV Columns (Pages):**
- Name, Content, Project, Parent Page
- Confluence ID, Space Name, Created Date, Created By
- Version, Hierarchy Path, Hierarchy Level, Page URL

**CSV Columns (Attachments):**
- Filename, Page Name, Page ID, Project, File Type
- Extension, Attachment ID, Size, Upload Date, Uploaded By
- Local File Path, Download URL

**Best For:**
- Fibery imports
- Database-driven documentation systems
- Maintaining relational data integrity
- Bulk processing workflows


### 2. `confluence_spaces_exporter_in_md.py`

This is for the case where you want to approach the through Markdown and not CSV.

**Markdown Export with Full Hierarchy**

Exports Confluence spaces to markdown files with nested folder structure, preserving the original page hierarchy and downloading all attachments.

**Features:**
- Interactive space selection
- Preserves original page hierarchy as nested folders
- Downloads all attachments (images, PDFs, documents)
- Converts Confluence macros to markdown equivalents
- Maintains metadata in YAML frontmatter
- Creates navigational README files

**Usage:**
```bash
py confluence_spaces_exporter_in_md.py
```

**Output Structure:**
```
confluence_export/
├── SPACE_KEY/
│   ├── Page_Title.md
│   ├── Parent_Page/
│   │   └── Child_Page.md
│   ├── attachments/
│   │   ├── image1.jpg
│   │   └── document.pdf
│   └── README.md (space index)
```

**Best For:**
- Preserving exact Confluence structure
- Manual content review and editing
- Systems that support nested folder imports


### 3. `restructure_md_space_import_for_fibery_import.py`
**Markdown Restructuring Tool**

Post-processes markdown exports to flatten the structure and fix attachment paths for systems that don't handle nested folders well.

**Features:**
- Flattens nested folder structure
- Consolidates all attachments into single folder
- Fixes relative path references
- Handles filename conflicts
- Preserves metadata in filenames

**Usage:**
```bash
py restructure_md_space_import_for_fibery_import.py <input_dir> <output_dir>
```

**Example:**
```bash
py restructure_md_space_import_for_fibery_import.py ./confluence_export/3OV ./fibery_ready/3OV
```

**Output Structure:**
```
fibery_ready/
├── SPACE_KEY/
│   ├── pages/
│   │   ├── Parent_Page_Child_Page.md
│   │   └── Another_Page.md
│   ├── attachments/
│   │   └── [all files flattened]
│   └── README.md (import instructions)
```

**Best For:**
- Preparing markdown exports for Fibery
- Systems requiring flat file structures
- Fixing broken attachment links

## Prerequisites

**Required Python Packages:**

**Install requirements for all scripts**:
```bash
py -m pip install -r requirements.txt
```

**For Confluence Cloud:**
- API token (create at: https://id.atlassian.com/manage-profile/security/api-tokens)
- Your email address
- Confluence base URL

## Quick Start


### For Fibery Import (Recommended)

1. **Use CSV Export** (most reliable):
```bash
py confluence_spaces_exporter_in_csv.py
```
2. **Alternativelly**:
    2.1. Follow the generated `IMPORT_INSTRUCTIONS.md`
    2.2. Upload CSV files to Fibery's CSV import feature


## Authentication

**confluence_spaces_exporter_in_csv** and **confluence_spaces_exporter_in_md** scripts use Confluence Cloud API tokens:

1. Go to: https://id.atlassian.com/manage-profile/security/api-tokens
2. Create a new token
3. Use your **email** as username
4. Use the **API token** as password

## Configuration

Scripts auto-detect Confluence Cloud instances and handle:
- Multiple attachment download URL formats
- Rate limiting and error handling
- Large space pagination
- Confluence macro conversion
- File system compatibility

## Workflow Recommendations

### For Fibery Migration
```
Confluence → CSV Export → Direct Fibery Import
```

### For General Documentation Migration
```
Confluence → Markdown Export → Manual Review → Target System
```

### For Complex Restructuring
```
Confluence → Markdown Export → Restructuring Tool → Manual Adjustment → Target System
```

## Troubleshooting

**Common Issues:**

1. **Authentication Failed**
   - Verify API token is correct
   - Use email (not username) for authentication
   - Check Confluence URL format

2. **Attachment Download Failures**
   - Some attachments may have restricted access
   - Check file permissions in Confluence
   - Large files may timeout (handled gracefully)

3. **Unicode/Encoding Errors**
   - Scripts use UTF-8 encoding
   - Windows users may need to set console encoding

4. **Rate Limiting**
   - Scripts include automatic rate limiting
   - Large spaces may take significant time
   - Progress is logged throughout

**Debug Mode:**
Set logging level to DEBUG in script headers for detailed output.

## Output Data Quality

**Preserved:**
- Complete page content and formatting
- All attachments and images
- Page hierarchies and relationships
- Creation dates and author information
- Version history metadata
- Confluence URLs and IDs

**Converted:**
- Confluence macros → Markdown equivalents
- Confluence storage format → Clean HTML → Markdown
- Relative links → Absolute URLs
- Special characters → File system safe names

**Limitations:**
- Some complex Confluence macros become placeholder text
- Advanced table formatting may be simplified
- Comments and page history are not exported
- User permissions are not preserved

## Contributing

To extend these tools:

1. **Authentication** - Modify `login_with_api_token()` methods
2. **Content Processing** - Update `process_content_to_markdown()` 
3. **Output Format** - Modify CSV field definitions or markdown templates
4. **Error Handling** - Add exception handling in download methods

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.