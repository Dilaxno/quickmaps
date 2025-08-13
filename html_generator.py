"""
HTML Generator Service

Generates HTML pages for processed video results using templates.
"""

import os
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional
import markdown
from jinja2 import Environment, FileSystemLoader, select_autoescape

from config import OUTPUT_DIR

logger = logging.getLogger(__name__)

class HTMLGenerator:
    """Service for generating HTML pages from processing results"""
    
    def __init__(self):
        # Setup Jinja2 environment
        template_dir = Path(__file__).parent / "templates"
        self.env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            autoescape=select_autoescape(['html', 'xml'])
        )
        
        # Setup markdown processor
        self.md = markdown.Markdown(extensions=[
            'markdown.extensions.extra',
            'markdown.extensions.codehilite',
            'markdown.extensions.toc'
        ])
    
    def generate_project_html(self, job_id: str, job_data: Dict[str, Any], 
                            user_id: Optional[str] = None) -> Optional[str]:
        """
        Generate complete HTML page for a processed video project
        
        Args:
            job_id: Job identifier
            job_data: Job data from job manager
            user_id: Optional user ID
            
        Returns:
            HTML string or None if generation fails
        """
        try:
            logger.info(f"Generating HTML page for job {job_id}")
            
            # Load template
            template = self.env.get_template('project_result.html')
            
            # Prepare template data
            template_data = self._prepare_template_data(job_id, job_data)
            
            # Load additional content files
            self._load_content_files(job_id, template_data)
            
            # Render HTML
            html_content = template.render(**template_data)
            
            logger.info(f"✅ Successfully generated HTML page for job {job_id}")
            return html_content
            
        except Exception as e:
            logger.error(f"❌ Failed to generate HTML page for job {job_id}: {e}")
            return None
    
    def _prepare_template_data(self, job_id: str, job_data: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare data for template rendering"""
        
        # Extract title from notes or use default
        title = self._extract_title_from_job(job_id) or "Quickmaps Learning Notes"
        
        # Calculate processing time
        processing_time = self._calculate_processing_time(job_data)
        
        # Format processing date
        processing_date = self._format_processing_date(job_data)
        
        return {
            'job_id': job_id,
            'title': title,
            'processing_date': processing_date,
            'language': job_data.get('language', 'Unknown').upper(),
            'duration': self._format_duration(job_data),
            'segments_count': job_data.get('segments_count', 0),
            'timestamp_coverage': job_data.get('timestamp_coverage', 0),
            'mapped_sections': job_data.get('mapped_sections', 0),
            'processing_time': processing_time,
            'has_notes': job_data.get('has_notes', False),
            'has_quiz': False,  # Will be updated when loading content
            'notes_html': '',  # Will be populated from files
            'quiz_html': '',   # Will be populated from files
            'transcription_text': job_data.get('transcription', 'No transcription available.')
        }
    
    def _load_content_files(self, job_id: str, template_data: Dict[str, Any]):
        """Load and process content files for the job"""
        
        # Load notes content
        notes_file = OUTPUT_DIR / f"{job_id}_notes.md"
        if notes_file.exists():
            try:
                with open(notes_file, 'r', encoding='utf-8') as f:
                    notes_content = f.read()
                
                # Convert markdown to HTML
                self.md.reset()  # Reset markdown processor
                template_data['notes_html'] = self.md.convert(notes_content)
                template_data['has_notes'] = True
                
                logger.info(f"Loaded notes content for job {job_id}")
            except Exception as e:
                logger.error(f"Failed to load notes for job {job_id}: {e}")
        
        # Load quiz content
        quiz_file = OUTPUT_DIR / f"{job_id}_quiz.json"
        if quiz_file.exists():
            try:
                with open(quiz_file, 'r', encoding='utf-8') as f:
                    quiz_data = json.load(f)
                
                template_data['quiz_html'] = self._format_quiz_html(quiz_data)
                template_data['has_quiz'] = True
                
                logger.info(f"Loaded quiz content for job {job_id}")
            except Exception as e:
                logger.error(f"Failed to load quiz for job {job_id}: {e}")
        
        # Load transcription if not in job_data
        if not template_data.get('transcription_text') or template_data['transcription_text'] == 'No transcription available.':
            transcription_file = OUTPUT_DIR / f"{job_id}_transcription.txt"
            if transcription_file.exists():
                try:
                    with open(transcription_file, 'r', encoding='utf-8') as f:
                        template_data['transcription_text'] = f.read()
                    
                    logger.info(f"Loaded transcription content for job {job_id}")
                except Exception as e:
                    logger.error(f"Failed to load transcription for job {job_id}: {e}")
    
    def _extract_title_from_job(self, job_id: str) -> Optional[str]:
        """Extract title from notes content"""
        notes_file = OUTPUT_DIR / f"{job_id}_notes.md"
        if not notes_file.exists():
            return None
        
        try:
            with open(notes_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Look for first heading
            lines = content.split('\n')
            for line in lines:
                line = line.strip()
                if line.startswith('# '):
                    return line[2:].strip()
                elif line.startswith('## ') and not line.startswith('### '):
                    return line[3:].strip()
            
            # Fallback: use first non-empty line
            for line in lines:
                line = line.strip()
                if line and not line.startswith('#'):
                    title = line[:50] + ('...' if len(line) > 50 else '')
                    return title
            
        except Exception as e:
            logger.error(f"Failed to extract title from notes for job {job_id}: {e}")
        
        return None
    
    def _format_quiz_html(self, quiz_data: Dict[str, Any]) -> str:
        """Format quiz data as HTML"""
        if not quiz_data or 'questions' not in quiz_data:
            return '<p>No quiz questions available.</p>'
        
        html_parts = []
        questions = quiz_data.get('questions', [])
        
        for i, question in enumerate(questions, 1):
            html_parts.append(f'<div class="quiz-question">')
            html_parts.append(f'<h4>Question {i}: {question.get("question", "")}</h4>')
            
            options = question.get('options', [])
            correct_answer = question.get('correct_answer', '')
            
            if options:
                html_parts.append('<ul class="quiz-options">')
                for option in options:
                    css_class = 'correct' if option == correct_answer else ''
                    marker = '✓ ' if option == correct_answer else '• '
                    html_parts.append(f'<li class="{css_class}">{marker}{option}</li>')
                html_parts.append('</ul>')
            
            explanation = question.get('explanation', '')
            if explanation:
                html_parts.append(f'<p><strong>Explanation:</strong> {explanation}</p>')
            
            html_parts.append('</div>')
        
        return '\n'.join(html_parts)
    
    def _calculate_processing_time(self, job_data: Dict[str, Any]) -> int:
        """Calculate processing time in seconds"""
        try:
            created_at = job_data.get('created_at')
            updated_at = job_data.get('updated_at')
            
            if created_at and updated_at:
                created = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                updated = datetime.fromisoformat(updated_at.replace('Z', '+00:00'))
                delta = updated - created
                return int(delta.total_seconds())
        except Exception as e:
            logger.error(f"Failed to calculate processing time: {e}")
        
        return 0
    
    def _format_processing_date(self, job_data: Dict[str, Any]) -> str:
        """Format processing date for display"""
        try:
            created_at = job_data.get('created_at')
            if created_at:
                dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                return dt.strftime('%B %d, %Y at %I:%M %p UTC')
        except Exception as e:
            logger.error(f"Failed to format processing date: {e}")
        
        return datetime.now(timezone.utc).strftime('%B %d, %Y at %I:%M %p UTC')
    
    def _format_duration(self, job_data: Dict[str, Any]) -> str:
        """Format duration for display"""
        segments_count = job_data.get('segments_count', 0)
        if segments_count > 0:
            # Rough estimate: assume average segment is 30 seconds
            estimated_minutes = (segments_count * 30) // 60
            if estimated_minutes > 60:
                hours = estimated_minutes // 60
                minutes = estimated_minutes % 60
                return f"{hours}h {minutes}m"
            else:
                return f"{estimated_minutes}m"
        return "Unknown"

# Global instance
html_generator = HTMLGenerator()