"""
PDF Processing Service
Handles PDF text extraction and content organization using PyMuPDF
"""

import fitz  # PyMuPDF
import logging
import json
import re
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from datetime import datetime

from groq_processor import groq_generator

logger = logging.getLogger(__name__)

class PDFProcessor:
    """Service for processing PDF files and extracting structured content"""
    
    def __init__(self):
        self.supported_formats = ['.pdf']
        
    def is_pdf_file(self, file_path: str) -> bool:
        """Check if the file is a PDF"""
        return Path(file_path).suffix.lower() in self.supported_formats
    
    def extract_text_from_pdf(self, pdf_path: str) -> Dict:
        """
        Extract text content from PDF file
        
        Args:
            pdf_path: Path to the PDF file
            
        Returns:
            Dictionary containing extracted text and metadata
        """
        try:
            # Open the PDF file
            pdf_document = fitz.open(pdf_path)
            
            extracted_content = {
                "title": "",
                "pages": [],
                "total_pages": len(pdf_document),
                "metadata": {},
                "full_text": "",
                "word_count": 0,
                "has_images": False,
                "has_tables": False
            }
            
            # Extract metadata
            metadata = pdf_document.metadata
            extracted_content["metadata"] = {
                "title": metadata.get("title", ""),
                "author": metadata.get("author", ""),
                "subject": metadata.get("subject", ""),
                "creator": metadata.get("creator", ""),
                "producer": metadata.get("producer", ""),
                "creation_date": metadata.get("creationDate", ""),
                "modification_date": metadata.get("modDate", "")
            }
            
            # Use title from metadata or filename
            if metadata.get("title"):
                extracted_content["title"] = metadata["title"]
            else:
                extracted_content["title"] = Path(pdf_path).stem
            
            full_text_parts = []
            
            # Extract text from each page
            for page_num in range(len(pdf_document)):
                page = pdf_document.load_page(page_num)
                
                # Extract text
                page_text = page.get_text()
                
                # Check for images
                if page.get_images():
                    extracted_content["has_images"] = True
                
                # Basic table detection (look for multiple columns of aligned text)
                if self._detect_tables_in_text(page_text):
                    extracted_content["has_tables"] = True
                
                # Clean and organize page text
                cleaned_text = self._clean_text(page_text)
                
                if cleaned_text.strip():
                    page_info = {
                        "page_number": page_num + 1,
                        "text": cleaned_text,
                        "word_count": len(cleaned_text.split()),
                        "char_count": len(cleaned_text)
                    }
                    
                    extracted_content["pages"].append(page_info)
                    full_text_parts.append(f"--- Page {page_num + 1} ---\n{cleaned_text}")
            
            # Combine all text
            extracted_content["full_text"] = "\n\n".join(full_text_parts)
            extracted_content["word_count"] = len(extracted_content["full_text"].split())
            
            pdf_document.close()
            
            logger.info(f"✅ PDF processed: {extracted_content['total_pages']} pages, "
                       f"{extracted_content['word_count']} words")
            
            return extracted_content
            
        except Exception as e:
            logger.error(f"❌ Failed to extract text from PDF: {e}")
            raise Exception(f"PDF text extraction failed: {str(e)}")
    
    def _clean_text(self, text: str) -> str:
        """Clean and normalize extracted text"""
        if not text:
            return ""
        
        # Remove excessive whitespace
        text = re.sub(r'\s+', ' ', text)
        
        # Remove page headers/footers patterns (common patterns)
        text = re.sub(r'^Page \d+.*$', '', text, flags=re.MULTILINE)
        text = re.sub(r'^\d+\s*$', '', text, flags=re.MULTILINE)
        
        # Remove excessive line breaks
        text = re.sub(r'\n\s*\n\s*\n', '\n\n', text)
        
        # Fix hyphenated words split across lines
        text = re.sub(r'(\w+)-\s*\n\s*(\w+)', r'\1\2', text)
        
        # Normalize quotes
        text = text.replace('"', '"').replace('"', '"')
        text = text.replace(''', "'").replace(''', "'")
        
        return text.strip()
    
    def _detect_tables_in_text(self, text: str) -> bool:
        """Basic table detection in text"""
        lines = text.split('\n')
        table_indicators = 0
        
        for line in lines:
            # Look for lines with multiple spaces (potential columns)
            if re.search(r'\w+\s{3,}\w+\s{3,}\w+', line):
                table_indicators += 1
            # Look for lines with tab characters
            elif '\t' in line and line.count('\t') >= 2:
                table_indicators += 1
        
        # If more than 3 lines look like table rows, assume there's a table
        return table_indicators > 3
    
    def structure_pdf_content(self, extracted_content: Dict) -> Dict:
        """
        Structure PDF content into organized sections
        
        Args:
            extracted_content: Output from extract_text_from_pdf
            
        Returns:
            Structured content ready for AI processing
        """
        try:
            structured_content = {
                "document_info": {
                    "title": extracted_content["title"],
                    "total_pages": extracted_content["total_pages"],
                    "word_count": extracted_content["word_count"],
                    "has_images": extracted_content["has_images"],
                    "has_tables": extracted_content["has_tables"],
                    "author": extracted_content["metadata"].get("author", ""),
                    "subject": extracted_content["metadata"].get("subject", "")
                },
                "content_sections": [],
                "full_text": extracted_content["full_text"]
            }
            
            # Try to identify sections based on headers and formatting
            sections = self._identify_sections(extracted_content["full_text"])
            structured_content["content_sections"] = sections
            
            return structured_content
            
        except Exception as e:
            logger.error(f"❌ Failed to structure PDF content: {e}")
            raise Exception(f"PDF content structuring failed: {str(e)}")
    
    def _identify_sections(self, text: str) -> List[Dict]:
        """Smart section identification with improved header detection and content association"""
        sections = []
        lines = text.split('\n')
        
        # Enhanced header patterns with priority order
        header_patterns = [
            # High priority - Clear structural headers
            (r'^(CHAPTER|Chapter)\s+\d+.*$', 'chapter'),
            (r'^(SECTION|Section)\s+\d+.*$', 'section'),
            (r'^\d+\.\d+\s+[A-Z].*$', 'subsection'),  # 1.1 Introduction
            (r'^\d+\.\s+[A-Z][a-zA-Z\s]{2,}$', 'numbered'),  # 1. Introduction
            
            # Medium priority - Formatting-based headers
            (r'^[A-Z][A-Z\s]{4,}[A-Z]$', 'allcaps'),  # ALL CAPS HEADERS
            (r'^[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*$', 'titlecase'),  # Title Case Headers
            
            # Lower priority - Content-based headers
            (r'^(Introduction|Conclusion|Summary|Overview|Background|Methodology|Results|Discussion)$', 'keyword'),
            (r'^(Abstract|Preface|Acknowledgments|References|Bibliography|Appendix)$', 'document_part'),
        ]
        
        # Analyze lines to identify headers and their content
        line_analysis = []
        for i, line in enumerate(lines):
            line_stripped = line.strip()
            if not line_stripped:
                line_analysis.append({'type': 'empty', 'content': '', 'line_num': i})
                continue
                
            # Check if line is a header
            header_type = None
            header_priority = 999
            
            for j, (pattern, h_type) in enumerate(header_patterns):
                if re.match(pattern, line_stripped):
                    header_type = h_type
                    header_priority = j
                    break
            
            # Additional heuristics for header detection
            is_likely_header = False
            if header_type:
                is_likely_header = True
            elif (len(line_stripped) < 80 and  # Not too long
                  len(line_stripped.split()) <= 8 and  # Not too many words
                  not line_stripped.endswith('.') and  # Doesn't end with period
                  not line_stripped.endswith(',') and  # Doesn't end with comma
                  len(line_stripped) > 3):  # Not too short
                
                # Check if next few lines contain content (not another potential header)
                content_follows = False
                for next_i in range(i + 1, min(i + 4, len(lines))):
                    next_line = lines[next_i].strip()
                    if next_line and len(next_line) > 20:  # Substantial content
                        content_follows = True
                        break
                
                if content_follows:
                    header_type = 'inferred'
                    header_priority = 10
                    is_likely_header = True
            
            line_analysis.append({
                'type': 'header' if is_likely_header else 'content',
                'content': line_stripped,
                'line_num': i,
                'header_type': header_type,
                'priority': header_priority
            })
        
        # Build sections from analysis
        current_section = None
        
        for item in line_analysis:
            if item['type'] == 'header':
                # Save previous section if it has content
                if current_section and current_section['content'].strip():
                    sections.append(current_section)
                
                # Start new section
                current_section = {
                    'title': item['content'],
                    'content': '',
                    'page_start': self._estimate_page_number(item['line_num'], len(lines)),
                    'header_type': item['header_type'],
                    'priority': item['priority']
                }
                
            elif item['type'] == 'content' and current_section:
                # Add content to current section
                if item['content']:
                    current_section['content'] += item['content'] + '\n'
                    
            elif item['type'] == 'empty' and current_section:
                # Add spacing for readability
                current_section['content'] += '\n'
        
        # Add the last section
        if current_section and current_section['content'].strip():
            sections.append(current_section)
        
        # Post-processing: merge sections that are too small or clean up
        processed_sections = self._post_process_sections(sections, text)
        
        return processed_sections
    
    def _post_process_sections(self, sections: List[Dict], full_text: str) -> List[Dict]:
        """Post-process sections to improve quality and handle edge cases"""
        if not sections:
            return [{
                "title": "Document Content",
                "content": full_text,
                "page_start": 1,
                "header_type": "default"
            }]
        
        processed = []
        min_content_length = 100  # Minimum characters for a section
        
        for i, section in enumerate(sections):
            content = section['content'].strip()
            
            # Skip sections that are too small unless they're the only section
            if len(content) < min_content_length and len(sections) > 1:
                # Try to merge with next section
                if i + 1 < len(sections):
                    sections[i + 1]['content'] = content + '\n\n' + sections[i + 1]['content']
                    sections[i + 1]['title'] = f"{section['title']} - {sections[i + 1]['title']}"
                # Or merge with previous section
                elif processed:
                    processed[-1]['content'] += '\n\n' + content
                continue
            
            # Clean up content
            content = self._clean_section_content(content)
            
            if content:  # Only add sections with actual content
                processed.append({
                    'title': section['title'],
                    'content': content,
                    'page_start': section['page_start'],
                    'header_type': section.get('header_type', 'unknown'),
                    'word_count': len(content.split())
                })
        
        # If no sections survived processing, create a default one
        if not processed:
            processed.append({
                "title": "Document Content",
                "content": self._clean_section_content(full_text),
                "page_start": 1,
                "header_type": "default",
                "word_count": len(full_text.split())
            })
        
        return processed
    
    def _clean_section_content(self, content: str) -> str:
        """Clean and improve section content"""
        if not content:
            return ""
        
        # Remove excessive whitespace while preserving paragraph structure
        lines = content.split('\n')
        cleaned_lines = []
        
        for line in lines:
            line = line.strip()
            if line:
                cleaned_lines.append(line)
            elif cleaned_lines and cleaned_lines[-1]:  # Preserve paragraph breaks
                cleaned_lines.append('')
        
        # Join lines and clean up excessive line breaks
        cleaned = '\n'.join(cleaned_lines)
        cleaned = re.sub(r'\n\s*\n\s*\n+', '\n\n', cleaned)  # Max 2 consecutive line breaks
        
        return cleaned.strip()
    
    def _estimate_page_number(self, line_index: int, total_lines: int) -> int:
        """Estimate page number based on line position"""
        # Rough estimation assuming ~50 lines per page
        return max(1, (line_index // 50) + 1)
    
    def generate_notes_from_pdf(self, pdf_path: str) -> Dict:
        """
        Complete PDF processing pipeline: extract text and generate structured notes
        
        Args:
            pdf_path: Path to the PDF file
            
        Returns:
            Structured notes generated from PDF content
        """
        try:
            logger.info(f"🔄 Starting PDF processing for: {pdf_path}")
            
            # Step 1: Extract text from PDF
            extracted_content = self.extract_text_from_pdf(pdf_path)
            
            # Step 2: Structure the content
            structured_content = self.structure_pdf_content(extracted_content)
            
            # Step 3: Generate AI-powered notes using Groq with smart section processing
            full_text = structured_content["full_text"]
            document_info = structured_content["document_info"]
            sections = structured_content["content_sections"]
            
            logger.info("🤖 Generating structured notes from PDF content...")
            logger.info(f"📊 Processing {len(full_text)} characters from {document_info['total_pages']} pages")
            logger.info(f"🔍 Identified {len(sections)} sections for smart processing")
            
            # Create enhanced prompt with section information
            enhanced_prompt = self._create_enhanced_pdf_prompt(structured_content)
            
            # Use the groq_generator's PDF-specific processing
            structured_notes = groq_generator.generate_pdf_notes(full_text)
            
            # Step 4: Combine results
            result = {
                "source": "pdf",
                "document_info": structured_content["document_info"],
                "extracted_text": extracted_content["full_text"],
                "structured_notes": structured_notes,
                "processing_metadata": {
                    "pages_processed": extracted_content["total_pages"],
                    "word_count": extracted_content["word_count"],
                    "sections_identified": len(structured_content["content_sections"]),
                    "processing_time": datetime.now().isoformat()
                }
            }
            
            logger.info(f"✅ PDF processing completed successfully")
            return result
            
        except Exception as e:
            logger.error(f"❌ PDF processing failed: {e}")
            raise Exception(f"PDF processing failed: {str(e)}")
    
    def _create_enhanced_pdf_prompt(self, structured_content: Dict) -> str:
        """Create an enhanced prompt for AI processing with smart section handling"""
        
        document_info = structured_content["document_info"]
        sections = structured_content["content_sections"]
        
        # Build section summaries for context
        section_summaries = []
        for i, section in enumerate(sections, 1):
            word_count = section.get('word_count', len(section['content'].split()))
            section_summaries.append(f"{i}. {section['title']} ({word_count} words)")
        
        prompt = f"""Please analyze this PDF document and create comprehensive, structured notes that preserve the document's organization and content depth.

DOCUMENT INFORMATION:
- Title: {document_info['title']}
- Pages: {document_info['total_pages']}
- Total Words: {document_info['word_count']}
- Author: {document_info.get('author', 'Unknown')}
- Subject: {document_info.get('subject', 'Not specified')}
- Sections Identified: {len(sections)}

DOCUMENT STRUCTURE:
{chr(10).join(section_summaries)}

FULL DOCUMENT CONTENT:
{structured_content['full_text']}

INSTRUCTIONS FOR STRUCTURED NOTES:
1. Create a comprehensive summary that reflects the document's structure
2. For each major section, provide:
   - Clear section heading
   - Key concepts and main points
   - Important details and explanations
   - Relevant examples or case studies
3. Maintain the logical flow and organization of the original document
4. Include definitions of technical terms and concepts
5. Highlight important conclusions, findings, or recommendations
6. Use bullet points, numbered lists, and clear formatting for readability
7. Ensure no section is reduced to just a title - provide substantial content for each

FORMAT REQUIREMENTS:
- Use markdown formatting with clear headings (##, ###)
- Include bullet points for key information
- Bold important terms and concepts
- Maintain paragraph structure for complex explanations
- Create a logical hierarchy that matches the document structure

The goal is to create study notes that someone could use to understand the full document without reading the original."""

        return prompt

# Global instance
pdf_processor = PDFProcessor()