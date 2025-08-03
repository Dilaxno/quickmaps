"""
Intelligent transcript segmentation for better educational content processing.
Groups transcript segments by topics, detects slide changes, and structures content for phi3.
"""

import re
import logging
from typing import List, Dict, Tuple, Optional
from collections import Counter
import math

logger = logging.getLogger(__name__)

class TranscriptSegmenter:
    """
    Intelligent segmentation of educational transcripts into coherent topics/sections
    """
    
    def __init__(self):
        # Common educational transition words/phrases
        self.transition_markers = [
            "now let's", "next", "moving on", "let's talk about", "another", 
            "the next", "first", "second", "third", "finally", "in conclusion",
            "let's look at", "let's examine", "turning to", "chapter", "section",
            "slide", "screen", "diagram", "figure", "table", "example",
            "question", "problem", "exercise", "practice", "review"
        ]
        
        # Common educational topic starters
        self.topic_starters = [
            "what is", "how to", "why", "when", "where", "definition of",
            "let's define", "this is", "we can see", "notice that",
            "important", "key", "main", "primary", "basic", "fundamental"
        ]
        
        # Pause indicators (long silence markers)
        self.pause_threshold = 3.0  # seconds
        
    def segment_transcript(self, segments: List[Dict]) -> List[Dict]:
        """
        Segment transcript into coherent topical sections
        
        Args:
            segments: List of transcript segments with text, start, end times
            
        Returns:
            List of topical segments with grouped content
        """
        if not segments:
            return []
            
        logger.info(f"🔍 Segmenting {len(segments)} transcript segments into topics...")
        
        # Step 1: Detect potential breakpoints
        breakpoints = self._detect_breakpoints(segments)
        logger.info(f"📍 Found {len(breakpoints)} potential breakpoints")
        
        # Step 2: Group segments into sections
        sections = self._group_into_sections(segments, breakpoints)
        logger.info(f"📚 Created {len(sections)} topical sections")
        
        # Step 3: Enhance sections with metadata
        enhanced_sections = self._enhance_sections(sections)
        
        return enhanced_sections
    
    def _detect_breakpoints(self, segments: List[Dict]) -> List[int]:
        """Detect potential topic transition points"""
        breakpoints = []
        
        for i in range(1, len(segments)):
            current = segments[i]
            previous = segments[i-1]
            
            # Check for pause-based breaks
            pause_score = self._calculate_pause_score(previous, current)
            
            # Check for content-based breaks
            content_score = self._calculate_content_shift_score(previous, current)
            
            # Check for structural markers
            structure_score = self._calculate_structure_score(current.get('text', ''))
            
            # Combined score
            total_score = pause_score + content_score + structure_score
            
            # Threshold for breakpoint detection
            if total_score > 0.6:  # Adjustable threshold
                breakpoints.append(i)
                logger.debug(f"Breakpoint at segment {i}: pause={pause_score:.2f}, content={content_score:.2f}, structure={structure_score:.2f}")
        
        return breakpoints
    
    def _calculate_pause_score(self, prev_segment: Dict, current_segment: Dict) -> float:
        """Calculate score based on pause duration between segments"""
        try:
            prev_end = float(prev_segment.get('end', 0))
            current_start = float(current_segment.get('start', 0))
            
            pause_duration = current_start - prev_end
            
            if pause_duration >= self.pause_threshold:
                return min(pause_duration / 10.0, 1.0)  # Normalize to 0-1
            
            return 0.0
        except (ValueError, TypeError):
            return 0.0
    
    def _calculate_content_shift_score(self, prev_segment: Dict, current_segment: Dict) -> float:
        """Calculate score based on content/topic shift"""
        prev_text = prev_segment.get('text', '').lower()
        current_text = current_segment.get('text', '').lower()
        
        if not prev_text or not current_text:
            return 0.0
        
        # Extract keywords
        prev_keywords = self._extract_keywords(prev_text)
        current_keywords = self._extract_keywords(current_text)
        
        if not prev_keywords or not current_keywords:
            return 0.0
        
        # Calculate keyword overlap
        overlap = len(set(prev_keywords) & set(current_keywords))
        total_unique = len(set(prev_keywords) | set(current_keywords))
        
        if total_unique == 0:
            return 0.0
        
        # Low overlap indicates topic shift
        overlap_ratio = overlap / total_unique
        shift_score = 1.0 - overlap_ratio
        
        return min(shift_score, 1.0)
    
    def _calculate_structure_score(self, text: str) -> float:
        """Calculate score based on structural/transition markers"""
        text_lower = text.lower()
        score = 0.0
        
        # Check for transition markers
        for marker in self.transition_markers:
            if marker in text_lower:
                score += 0.3
        
        # Check for topic starters
        for starter in self.topic_starters:
            if text_lower.startswith(starter) or f" {starter}" in text_lower:
                score += 0.4
        
        # Check for questions (often indicate new topics)
        if '?' in text:
            score += 0.2
        
        # Check for enumeration (first, second, etc.)
        if re.search(r'\b(first|second|third|fourth|fifth|1st|2nd|3rd|4th|5th)\b', text_lower):
            score += 0.3
        
        return min(score, 1.0)
    
    def _extract_keywords(self, text: str) -> List[str]:
        """Extract meaningful keywords from text"""
        # Remove common stop words
        stop_words = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 
            'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
            'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
            'should', 'may', 'might', 'can', 'this', 'that', 'these', 'those',
            'i', 'you', 'he', 'she', 'it', 'we', 'they', 'me', 'him', 'her', 'us', 'them'
        }
        
        # Extract words (3+ characters, alphanumeric)
        words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
        
        # Filter out stop words and get significant terms
        keywords = [word for word in words if word not in stop_words]
        
        # Return most frequent keywords (up to 5)
        word_counts = Counter(keywords)
        return [word for word, count in word_counts.most_common(5)]
    
    def _group_into_sections(self, segments: List[Dict], breakpoints: List[int]) -> List[Dict]:
        """Group segments into sections based on breakpoints"""
        sections = []
        start_idx = 0
        
        # Add breakpoints + end
        all_breakpoints = sorted(breakpoints + [len(segments)])
        
        for breakpoint in all_breakpoints:
            if breakpoint > start_idx:
                section_segments = segments[start_idx:breakpoint]
                
                # Create section
                section = {
                    'segments': section_segments,
                    'start_time': section_segments[0].get('start', 0),
                    'end_time': section_segments[-1].get('end', 0),
                    'text': ' '.join(seg.get('text', '') for seg in section_segments),
                }
                
                sections.append(section)
                start_idx = breakpoint
        
        return sections
    
    def _enhance_sections(self, sections: List[Dict]) -> List[Dict]:
        """Enhance sections with topic analysis and metadata"""
        enhanced = []
        
        for i, section in enumerate(sections):
            text = section['text']
            
            # Generate topic title
            topic_title = self._generate_topic_title(text)
            
            # Extract key concepts
            key_concepts = self._extract_key_concepts(text)
            
            # Determine section type
            section_type = self._classify_section_type(text)
            
            enhanced_section = {
                'section_id': i + 1,
                'topic_title': topic_title,
                'section_type': section_type,
                'text': text,
                'start_time': section['start_time'],
                'end_time': section['end_time'],
                'duration': section['end_time'] - section['start_time'],
                'key_concepts': key_concepts,
                'segment_count': len(section['segments']),
                'original_segments': section['segments']
            }
            
            enhanced.append(enhanced_section)
            
        return enhanced
    
    def _generate_topic_title(self, text: str) -> str:
        """Generate a descriptive title for the section"""
        # Look for explicit titles or topic mentions
        text_lower = text.lower()
        
        # Check for definition patterns
        if 'definition' in text_lower or 'what is' in text_lower or 'define' in text_lower:
            # Try to extract the defined term
            patterns = [
                r'what is (\w+(?:\s+\w+){0,2})',
                r'define (\w+(?:\s+\w+){0,2})',
                r'definition of (\w+(?:\s+\w+){0,2})',
                r'(\w+(?:\s+\w+){0,2}) is defined as'
            ]
            
            for pattern in patterns:
                match = re.search(pattern, text_lower)
                if match:
                    return f"Definition: {match.group(1).title()}"
        
        # Check for process descriptions
        if any(word in text_lower for word in ['process', 'steps', 'procedure', 'method']):
            # Try to extract the process name
            keywords = self._extract_keywords(text)
            if keywords:
                return f"Process: {keywords[0].title()}"
        
        # Check for examples
        if 'example' in text_lower or 'for instance' in text_lower:
            return "Examples and Applications"
        
        # Default: use most frequent meaningful terms
        keywords = self._extract_keywords(text)
        if keywords:
            if len(keywords) >= 2:
                return f"{keywords[0].title()} and {keywords[1].title()}"
            else:
                return keywords[0].title()
        
        return f"Section {hash(text) % 1000}"  # Fallback
    
    def _extract_key_concepts(self, text: str) -> List[str]:
        """Extract key concepts/terms from the section"""
        keywords = self._extract_keywords(text)
        
        # Look for capitalized terms (often proper nouns/concepts)
        capitalized_terms = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', text)
        
        # Combine and deduplicate
        concepts = list(set(keywords + [term.lower() for term in capitalized_terms]))
        
        return concepts[:8]  # Limit to top concepts
    
    def _classify_section_type(self, text: str) -> str:
        """Classify the type of educational content"""
        text_lower = text.lower()
        
        if any(word in text_lower for word in ['definition', 'what is', 'define', 'means']):
            return 'definition'
        elif any(word in text_lower for word in ['example', 'for instance', 'such as', 'like']):
            return 'example'
        elif any(word in text_lower for word in ['process', 'steps', 'procedure', 'first', 'then', 'next']):
            return 'process'
        elif any(word in text_lower for word in ['problem', 'solve', 'calculate', 'find']):
            return 'problem_solving'
        elif '?' in text:
            return 'question'
        elif any(word in text_lower for word in ['summary', 'conclusion', 'review', 'recap']):
            return 'summary'
        else:
            return 'explanation'

def create_structured_prompt(sections: List[Dict]) -> str:
    """
    Create a structured prompt for phi3 with section information
    """
    prompt_parts = [
        "You are analyzing an educational video transcript that has been intelligently segmented into topical sections.",
        "Please provide a comprehensive educational summary in JSON format with the following structure:",
        "",
        "TRANSCRIPT SECTIONS:",
    ]
    
    for section in sections:
        prompt_parts.append(f"\n=== SECTION {section['section_id']}: {section['topic_title']} ===")
        prompt_parts.append(f"Type: {section['section_type']}")
        prompt_parts.append(f"Duration: {section['duration']:.1f}s")
        prompt_parts.append(f"Key Concepts: {', '.join(section['key_concepts'][:5])}")
        prompt_parts.append(f"Content: {section['text'][:500]}...")  # Truncate for prompt size
    
    prompt_parts.extend([
        "",
        "REQUIRED JSON OUTPUT FORMAT:",
        "{",
        '  "title": "Overall topic/lesson title",',
        '  "summary": "Comprehensive 2-3 paragraph summary",',
        '  "key_points": ["Important point 1", "Important point 2", ...],',
        '  "definitions": [{"term": "Term", "definition": "Definition"}, ...],',
        '  "examples": ["Example 1", "Example 2", ...],',
        '  "questions": ["Study question 1", "Study question 2", ...],',
        '  "common_mistakes": ["Common mistake 1", "Common mistake 2", ...],',
        '  "visual_notes": ["Visual element 1", "Visual element 2", ...],',
        '  "chapters": [',
        '    {',
        '      "title": "Chapter title",',
        '      "timestamp": "0:00-5:30",',
        '      "summary": "Chapter summary",',
        '      "key_concepts": ["concept1", "concept2"]',
        '    }, ...',
        '  ]',
        '}',
        "",
        "Focus on educational value, comprehension, and learning outcomes."
    ])
    
    return '\n'.join(prompt_parts)