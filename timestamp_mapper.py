"""
Timestamp Mapper - Maps generated notes back to original audio timestamps
"""

import logging
import re
from typing import List, Dict, Tuple, Optional
from difflib import SequenceMatcher
import json

logger = logging.getLogger(__name__)

class TimestampMapper:
    """Maps structured notes back to original transcription timestamps"""
    
    def __init__(self):
        self.similarity_threshold = 0.3  # Minimum similarity to consider a match
        self.min_segment_length = 10    # Minimum characters for a meaningful segment
    
    def map_notes_to_timestamps(self, structured_notes: str, transcription_segments: List[Dict]) -> Dict:
        """
        Map structured notes sections to their corresponding audio timestamps
        
        Args:
            structured_notes: The generated structured notes (markdown format)
            transcription_segments: List of segments with 'start', 'end', 'text' keys
            
        Returns:
            Dictionary with note sections and their timestamp mappings
        """
        try:
            # Parse the structured notes into sections
            note_sections = self._parse_note_sections(structured_notes)
            
            # Create a mapping of each section to timestamps
            timestamp_mappings = []
            
            for section in note_sections:
                timestamps = self._find_timestamps_for_section(section, transcription_segments)
                
                timestamp_mappings.append({
                    'title': section['title'],
                    'content': section['content'],
                    'level': section['level'],
                    'timestamps': timestamps,
                    'start_time': timestamps[0]['start'] if timestamps else None,
                    'end_time': timestamps[-1]['end'] if timestamps else None,
                    'duration': (timestamps[-1]['end'] - timestamps[0]['start']) if timestamps else 0
                })
            
            return {
                'sections': timestamp_mappings,
                'total_sections': len(timestamp_mappings),
                'mapped_sections': len([s for s in timestamp_mappings if s['timestamps']]),
                'coverage_percentage': self._calculate_coverage(timestamp_mappings, transcription_segments)
            }
            
        except Exception as e:
            logger.error(f"Error mapping notes to timestamps: {e}")
            return {'sections': [], 'error': str(e)}
    
    def _parse_note_sections(self, structured_notes: str) -> List[Dict]:
        """Parse structured notes into sections with titles and content"""
        sections = []
        lines = structured_notes.split('\n')
        current_section = None
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # Check for headers (## Title, ### Subtitle, etc.)
            header_match = re.match(r'^(#{1,6})\s+(.+)$', line)
            if header_match:
                # Save previous section if exists
                if current_section:
                    # Determine section type based on content
                    content = current_section['content'].strip()
                    if not content:
                        current_section['type'] = 'title'  # Title-only section
                    else:
                        current_section['type'] = 'content'  # Section with content
                    sections.append(current_section)
                
                # Start new section
                level = len(header_match.group(1))
                title = header_match.group(2).strip()
                current_section = {
                    'title': title,
                    'content': '',
                    'level': level,
                    'type': 'content'  # Default, will be updated when section ends
                }
            elif current_section:
                # Add content to current section
                current_section['content'] += line + '\n'
        
        # Add the last section
        if current_section:
            # Determine section type based on content
            content = current_section['content'].strip()
            if not content:
                current_section['type'] = 'title'  # Title-only section
            else:
                current_section['type'] = 'content'  # Section with content
            sections.append(current_section)
        
        return sections
    
    def _find_timestamps_for_section(self, section: Dict, transcription_segments: List[Dict]) -> List[Dict]:
        """Find the best matching timestamps for a note section"""
        section_content = section['content'].strip()
        
        # For title-only sections, use the title for matching
        if section.get('type') == 'title' or len(section_content) < self.min_segment_length:
            if section.get('type') == 'title':
                # Use title for matching title-only sections
                search_text = section['title']
            else:
                # Content too short, skip
                return []
        else:
            # Use content for regular sections
            search_text = section_content
        
        # Extract key phrases from the search text
        key_phrases = self._extract_key_phrases(search_text)
        
        # Find matching segments
        matching_segments = []
        used_segments = set()  # Track used segments to avoid overlap
        
        for phrase in key_phrases:
            best_matches = self._find_best_matching_segments(phrase, transcription_segments, used_segments)
            for match in best_matches:
                if match['segment_index'] not in used_segments:
                    matching_segments.append({
                        'start': match['segment']['start'],
                        'end': match['segment']['end'],
                        'text': match['segment']['text'],
                        'similarity': match['similarity'],
                        'matched_phrase': phrase
                    })
                    used_segments.add(match['segment_index'])
        
        # Sort by start time and merge adjacent segments
        matching_segments.sort(key=lambda x: x['start'])
        merged_segments = self._merge_adjacent_segments(matching_segments)
        
        return merged_segments
    
    def _extract_key_phrases(self, content: str) -> List[str]:
        """Extract key phrases from note content for matching"""
        # Remove markdown formatting
        clean_content = re.sub(r'\*\*([^*]+)\*\*', r'\1', content)  # Bold
        clean_content = re.sub(r'\*([^*]+)\*', r'\1', clean_content)  # Italic
        clean_content = re.sub(r'`([^`]+)`', r'\1', clean_content)  # Code
        clean_content = re.sub(r'^\s*[-*+]\s+', '', clean_content, flags=re.MULTILINE)  # Bullets
        
        # Split into sentences and filter
        sentences = re.split(r'[.!?]+', clean_content)
        phrases = []
        
        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) > 20 and len(sentence) < 200:  # Reasonable length
                # Remove common filler words and phrases
                if not self._is_filler_sentence(sentence):
                    phrases.append(sentence)
        
        # Also extract quoted text or definitions
        quoted_matches = re.findall(r'"([^"]+)"', content)
        for quote in quoted_matches:
            if len(quote) > 10:
                phrases.append(quote)
        
        return phrases[:10]  # Limit to top 10 phrases to avoid too many matches
    
    def _is_filler_sentence(self, sentence: str) -> bool:
        """Check if a sentence is likely filler content"""
        filler_patterns = [
            r'^(this|that|these|those|it|they)\s+(is|are|was|were)',
            r'^(in|on|at|for|with|by)\s+this',
            r'^(here|there)\s+(is|are)',
            r'^(as\s+we\s+can\s+see|as\s+mentioned|as\s+discussed)',
            r'^(the\s+following|the\s+above|the\s+below)',
        ]
        
        sentence_lower = sentence.lower()
        for pattern in filler_patterns:
            if re.match(pattern, sentence_lower):
                return True
        
        return False
    
    def _find_best_matching_segments(self, phrase: str, segments: List[Dict], used_segments: set) -> List[Dict]:
        """Find segments that best match a given phrase"""
        matches = []
        
        for i, segment in enumerate(segments):
            if i in used_segments:
                continue
                
            similarity = self._calculate_similarity(phrase, segment['text'])
            if similarity >= self.similarity_threshold:
                matches.append({
                    'segment': segment,
                    'segment_index': i,
                    'similarity': similarity
                })
        
        # Sort by similarity and return top matches
        matches.sort(key=lambda x: x['similarity'], reverse=True)
        return matches[:3]  # Return top 3 matches
    
    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """Calculate similarity between two text strings"""
        # Normalize texts
        text1 = re.sub(r'[^\w\s]', '', text1.lower())
        text2 = re.sub(r'[^\w\s]', '', text2.lower())
        
        # Use sequence matcher for similarity
        return SequenceMatcher(None, text1, text2).ratio()
    
    def _merge_adjacent_segments(self, segments: List[Dict], max_gap: float = 5.0) -> List[Dict]:
        """Merge segments that are close together in time"""
        if not segments:
            return []
        
        merged = []
        current_group = [segments[0]]
        
        for segment in segments[1:]:
            # If this segment starts within max_gap seconds of the last segment's end
            if segment['start'] - current_group[-1]['end'] <= max_gap:
                current_group.append(segment)
            else:
                # Merge current group and start new one
                merged.append(self._merge_segment_group(current_group))
                current_group = [segment]
        
        # Merge the last group
        if current_group:
            merged.append(self._merge_segment_group(current_group))
        
        return merged
    
    def _merge_segment_group(self, segments: List[Dict]) -> Dict:
        """Merge a group of segments into one"""
        if len(segments) == 1:
            return segments[0]
        
        return {
            'start': segments[0]['start'],
            'end': segments[-1]['end'],
            'text': ' '.join([s['text'] for s in segments]),
            'similarity': max([s['similarity'] for s in segments]),
            'matched_phrase': segments[0]['matched_phrase'],
            'segment_count': len(segments)
        }
    
    def _calculate_coverage(self, timestamp_mappings: List[Dict], transcription_segments: List[Dict]) -> float:
        """Calculate what percentage of the original audio is covered by mapped notes"""
        if not transcription_segments:
            return 0.0
        
        total_duration = transcription_segments[-1]['end'] - transcription_segments[0]['start']
        covered_duration = 0.0
        
        for mapping in timestamp_mappings:
            if mapping['timestamps']:
                covered_duration += mapping['duration']
        
        return (covered_duration / total_duration) * 100 if total_duration > 0 else 0.0
    
    def export_timestamped_notes(self, mapped_data: Dict, format: str = 'json') -> str:
        """Export the timestamped notes in various formats"""
        if format == 'json':
            return json.dumps(mapped_data, indent=2, ensure_ascii=False)
        
        elif format == 'srt':
            return self._export_as_srt(mapped_data)
        
        elif format == 'vtt':
            return self._export_as_vtt(mapped_data)
        
        elif format == 'markdown':
            return self._export_as_markdown(mapped_data)
        
        else:
            raise ValueError(f"Unsupported format: {format}")
    
    def _export_as_srt(self, mapped_data: Dict) -> str:
        """Export as SRT subtitle format"""
        srt_content = ""
        counter = 1
        
        for section in mapped_data['sections']:
            if section['timestamps']:
                start_time = self._seconds_to_srt_time(section['start_time'])
                end_time = self._seconds_to_srt_time(section['end_time'])
                
                srt_content += f"{counter}\n"
                srt_content += f"{start_time} --> {end_time}\n"
                srt_content += f"{section['title']}\n\n"
                counter += 1
        
        return srt_content
    
    def _export_as_vtt(self, mapped_data: Dict) -> str:
        """Export as WebVTT format"""
        vtt_content = "WEBVTT\n\n"
        
        for section in mapped_data['sections']:
            if section['timestamps']:
                start_time = self._seconds_to_vtt_time(section['start_time'])
                end_time = self._seconds_to_vtt_time(section['end_time'])
                
                vtt_content += f"{start_time} --> {end_time}\n"
                vtt_content += f"{section['title']}\n\n"
        
        return vtt_content
    
    def _export_as_markdown(self, mapped_data: Dict) -> str:
        """Export as enhanced markdown with timestamps"""
        md_content = "# Timestamped Learning Notes\n\n"
        md_content += f"**Coverage:** {mapped_data.get('coverage_percentage', 0):.1f}% of original audio\n\n"
        md_content += "---\n\n"
        
        for section in mapped_data['sections']:
            # Add section header with timestamp and type
            header_level = '#' * (section['level'] + 1)
            if section['start_time'] is not None:
                timestamp_str = f" `[{self._seconds_to_readable(section['start_time'])} - {self._seconds_to_readable(section['end_time'])}]`"
            else:
                timestamp_str = " `[No timestamp found]`"
            
            # Add type indicator for title-only sections
            type_indicator = ""
            if section.get('type') == 'title':
                type_indicator = " `[TITLE]`"
            
            md_content += f"{header_level} {section['title']}{timestamp_str}{type_indicator}\n\n"
            
            # Only add content if it exists (not for title-only sections)
            if section['content'].strip():
                md_content += f"{section['content']}\n\n"
            elif section.get('type') == 'title':
                md_content += "*This is a title-only section without additional content.*\n\n"
            
            # Add timestamp details if available
            if section['timestamps']:
                md_content += "**Audio Segments:**\n"
                for ts in section['timestamps']:
                    start_readable = self._seconds_to_readable(ts['start'])
                    end_readable = self._seconds_to_readable(ts['end'])
                    md_content += f"- {start_readable} - {end_readable}: {ts['text'][:100]}...\n"
                md_content += "\n"
            
            md_content += "---\n\n"
        
        return md_content
    
    def _seconds_to_srt_time(self, seconds: float) -> str:
        """Convert seconds to SRT time format (HH:MM:SS,mmm)"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millisecs = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millisecs:03d}"
    
    def _seconds_to_vtt_time(self, seconds: float) -> str:
        """Convert seconds to WebVTT time format (HH:MM:SS.mmm)"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millisecs = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millisecs:03d}"
    
    def _seconds_to_readable(self, seconds: float) -> str:
        """Convert seconds to readable time format (MM:SS)"""
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes:02d}:{secs:02d}"

# Global instance
timestamp_mapper = TimestampMapper()