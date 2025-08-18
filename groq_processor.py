"""
Groq API integration for generating structured learning notes from transcriptions
with auto-generated diagram functionality
"""

import logging
import hashlib
import time
import os
import threading
from typing import Optional, Dict, Set, List
from groq import Groq
from config import GROQ_API_KEY, GROQ_MODEL, ENABLE_NOTES_GENERATION

logger = logging.getLogger(__name__)

# Global throttling settings for Groq API
_GROQ_THROTTLE_LOCK = threading.Lock()
_GROQ_LAST_CALL_TS = 0.0
try:
    _GROQ_MIN_INTERVAL = float(os.getenv("GROQ_MIN_INTERVAL_SECONDS", "1.0"))
except Exception:
    _GROQ_MIN_INTERVAL = 1.0

class GroqNotesGenerator:
    """Generate structured learning notes using Groq API"""
    
    def __init__(self):
        if not GROQ_API_KEY:
            logger.warning("GROQ_API_KEY not set. Notes generation will be disabled.")
            self.client = None
            self.model = None
        else:
            self.client = Groq(api_key=GROQ_API_KEY)
            self.model = GROQ_MODEL
            # Install throttling on this client's chat.completions.create
            self._install_throttling()
        
        # Track generated content to prevent repetition
        self.generated_content_hashes: Set[str] = set()
        self.recent_introductions: List[str] = []
        self.recent_takeaways: List[str] = []
        self.content_variations: Dict[str, int] = {}
        
        # Cleanup old tracking data periodically
        self.last_cleanup = time.time()

    def _install_throttling(self):
        """Wrap the Groq client's chat.completions.create with a throttle (min interval between requests)."""
        try:
            # Access nested attribute once
            original_create = self.client.chat.completions.create

            def throttled_create(*args, **kwargs):
                global _GROQ_LAST_CALL_TS
                # Enforce minimum interval across threads/process within this app instance
                with _GROQ_THROTTLE_LOCK:
                    now = time.time()
                    elapsed = now - _GROQ_LAST_CALL_TS
                    if elapsed < _GROQ_MIN_INTERVAL:
                        sleep_for = _GROQ_MIN_INTERVAL - elapsed
                        if sleep_for > 0:
                            time.sleep(sleep_for)
                    # Perform the API call
                    result = original_create(*args, **kwargs)
                    _GROQ_LAST_CALL_TS = time.time()
                    return result

            # Replace the method
            self.client.chat.completions.create = throttled_create
            logger.info(f"Groq throttling installed: min { _GROQ_MIN_INTERVAL }s between requests")
        except Exception as e:
            logger.warning(f"Failed to install Groq throttling wrapper: {e}")
    
    def is_available(self) -> bool:
        """Check if Groq API is available"""
        return self.client is not None and ENABLE_NOTES_GENERATION
    
    def _cleanup_tracking_data(self):
        """Clean up old tracking data to prevent memory buildup"""
        current_time = time.time()
        # Clean up every hour
        if current_time - self.last_cleanup > 3600:
            # Keep only recent data (last 100 items)
            if len(self.generated_content_hashes) > 100:
                # Convert to list, keep last 50, convert back to set
                hash_list = list(self.generated_content_hashes)
                self.generated_content_hashes = set(hash_list[-50:])
            
            # Keep only recent introductions and takeaways
            self.recent_introductions = self.recent_introductions[-20:]
            self.recent_takeaways = self.recent_takeaways[-20:]
            
            # Reset variation counters periodically
            self.content_variations.clear()
            
            self.last_cleanup = current_time
            logger.info("Cleaned up content tracking data")
    
    def _get_content_hash(self, content: str) -> str:
        """Generate hash for content to track uniqueness"""
        return hashlib.md5(content.encode('utf-8')).hexdigest()
    
    def _is_content_similar(self, new_content: str) -> bool:
        """Check if content is similar to recently generated content"""
        content_hash = self._get_content_hash(new_content)
        
        # Check exact duplicates
        if content_hash in self.generated_content_hashes:
            return True
        
        # Check for similar introductions (first 200 characters)
        intro = new_content[:200].lower().strip()
        for recent_intro in self.recent_introductions:
            if self._calculate_similarity(intro, recent_intro) > 0.7:
                return True
        
        return False
    
    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """Calculate similarity between two texts (simple word overlap)"""
        if not text1 or not text2:
            return 0.0
        
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union) if union else 0.0
    
    def _track_generated_content(self, content: str):
        """Track generated content to prevent future repetition"""
        content_hash = self._get_content_hash(content)
        self.generated_content_hashes.add(content_hash)
        
        # Track introduction (first 200 characters)
        intro = content[:200].lower().strip()
        self.recent_introductions.append(intro)
        
        # Track key takeaways if present
        if "key takeaways" in content.lower():
            takeaway_start = content.lower().find("key takeaways")
            if takeaway_start != -1:
                takeaway_section = content[takeaway_start:takeaway_start+300].lower().strip()
                self.recent_takeaways.append(takeaway_section)
        
        # Cleanup if needed
        self._cleanup_tracking_data()
    
    def _get_variation_prompt_addition(self, content_type: str) -> str:
        """Get additional prompt instructions to ensure content variation"""
        variation_count = self.content_variations.get(content_type, 0)
        self.content_variations[content_type] = variation_count + 1
        
        variations = [
            "Focus on practical applications and real-world examples.",
            "Emphasize theoretical foundations and conceptual understanding.",
            "Highlight step-by-step processes and methodologies.",
            "Concentrate on problem-solving approaches and critical thinking.",
            "Focus on connections between concepts and interdisciplinary links.",
            "Emphasize historical context and development of ideas.",
            "Highlight comparative analysis and contrasting viewpoints.",
            "Focus on implementation strategies and best practices."
        ]
        
        selected_variation = variations[variation_count % len(variations)]
        
        return f"""
UNIQUENESS REQUIREMENTS:
- {selected_variation}
- Avoid generic introductory phrases like "This section covers", "Important concepts include", "Key principles are"
- Use varied sentence structures and avoid repetitive patterns
- Create unique section titles that are specific and descriptive
- Avoid standard "Key Takeaways" sections - integrate important points naturally into explanations
- Use diverse vocabulary and avoid overused educational terminology
- Make each section distinctive with its own voice and approach
"""
    
    def generate_notes(self, transcription: str, content_type: str = "video") -> Optional[str]:
        """
        Generate structured learning notes from transcription or text content
        
        Args:
            transcription: Raw transcription text or PDF content
            content_type: Type of content - "video" or "pdf"
            
        Returns:
            Structured notes or None if generation fails
        """
        if not self.is_available():
            logger.warning("Groq API not available. Skipping notes generation.")
            return None
        
        if not transcription or len(transcription.strip()) < 50:
            logger.warning("Content too short for notes generation")
            return None
        
        try:
            # Split long content into chunks if needed
            max_chunk_size = 15000  # Conservative limit for API
            chunks = self._split_content(transcription, max_chunk_size)
            
            # Generate notes with uniqueness tracking
            notes = None
            max_attempts = 3
            
            for attempt in range(max_attempts):
                if len(chunks) == 1:
                    notes = self._generate_notes_chunk(chunks[0], content_type)
                    if notes:
                        # Validate and fix structure even for single chunks
                        notes = self._validate_and_fix_notes_structure(notes)
                else:
                    # Process multiple chunks and combine
                    notes = self._generate_notes_multiple_chunks(chunks, content_type)
                
                # Enforce per-note word limit before uniqueness tracking
                if notes:
                    try:
                        max_words = int(os.getenv("NOTES_MAX_WORDS", "50"))
                    except Exception:
                        max_words = 50
                    notes = self._enforce_word_limit_on_notes(notes, max_words)

                # Check for uniqueness
                if notes and not self._is_content_similar(notes):
                    # Track the generated content
                    self._track_generated_content(notes)
                    logger.info(f"Generated unique notes on attempt {attempt + 1}")
                    return notes
                elif notes:
                    logger.warning(f"Generated content is similar to previous content, retrying... (attempt {attempt + 1})")
                    # Add some randomness for retry
                    time.sleep(0.5)
                else:
                    logger.warning(f"Failed to generate notes on attempt {attempt + 1}")
            
            # If all attempts failed to generate unique content, return the last attempt
            if notes:
                logger.warning("Using potentially similar content after max attempts")
                self._track_generated_content(notes)
                return notes
            
            return None
                
        except Exception as e:
            logger.error(f"Error generating notes with Groq: {e}")
            return None
    
    def generate_video_notes(self, transcription: str) -> Optional[str]:
        """Generate notes specifically for video transcriptions"""
        return self.generate_notes(transcription, "video")
    
    def generate_pdf_notes(self, pdf_content: str) -> Optional[str]:
        """Generate notes specifically for PDF documents"""
        return self.generate_notes(pdf_content, "pdf")
    
    def generate_study_notes(self, content: str) -> Optional[str]:
        """Generate study notes from any text content (OCR, PDF, etc.)"""
        return self.generate_notes(content, "study")
    
    def generate_notes_with_diagram(self, transcription: str, content_type: str = "video", 
                                  diagram_type: str = "flowchart") -> Optional[Dict]:
        """
        Generate structured learning notes with auto-generated diagram
        
        Args:
            transcription: Raw transcription text or content
            content_type: Type of content - "video", "pdf", or "study"
            diagram_type: Type of diagram - "flowchart", "mindmap", "sequence", "process"
            
        Returns:
            Dictionary containing notes and diagram data or None if generation fails
        """
        # Generate notes first
        notes = self.generate_notes(transcription, content_type)
        if not notes:
            return None
        
        # Import diagram generator here to avoid circular imports
        try:
            from diagram_generator import diagram_generator
            
            # Generate diagram from the notes
            diagram_data = diagram_generator.generate_diagram_from_notes(notes, diagram_type)
            
            result = {
                "notes": notes,
                "diagram": diagram_data,
                "content_type": content_type,
                "diagram_type": diagram_type
            }
            
            # Save diagram as HTML if generation was successful
            if diagram_data:
                html_filename = f"{content_type}_{diagram_type}_diagram.html"
                html_path = diagram_generator.save_diagram_html(diagram_data, html_filename)
                if html_path:
                    result["diagram_html_path"] = html_path
                    logger.info(f"Diagram HTML saved: {html_path}")
            
            return result
            
        except ImportError as e:
            logger.warning(f"Diagram generator not available: {e}")
            return {"notes": notes, "diagram": None, "content_type": content_type}
        except Exception as e:
            logger.error(f"Error generating diagram: {e}")
            return {"notes": notes, "diagram": None, "content_type": content_type}
    
    def generate_video_notes_with_diagram(self, transcription: str, diagram_type: str = "flowchart") -> Optional[Dict]:
        """Generate video notes with auto-generated diagram"""
        return self.generate_notes_with_diagram(transcription, "video", diagram_type)
    
    def generate_pdf_notes_with_diagram(self, pdf_content: str, diagram_type: str = "mindmap") -> Optional[Dict]:
        """Generate PDF notes with auto-generated diagram"""
        return self.generate_notes_with_diagram(pdf_content, "pdf", diagram_type)
    
    def generate_study_notes_with_diagram(self, content: str, diagram_type: str = "flowchart") -> Optional[Dict]:
        """Generate study notes with auto-generated diagram"""
        return self.generate_notes_with_diagram(content, "study", diagram_type)
    
    def generate_process_diagram_from_content(self, content: str) -> Optional[Dict]:
        """Generate process/workflow diagram directly from content"""
        try:
            from diagram_generator import diagram_generator
            return diagram_generator.generate_process_diagram(content)
        except ImportError:
            logger.warning("Diagram generator not available")
            return None
    
    def generate_mindmap_from_content(self, content: str) -> Optional[Dict]:
        """Generate mind map diagram directly from content"""
        try:
            from diagram_generator import diagram_generator
            return diagram_generator.generate_mindmap_diagram(content)
        except ImportError:
            logger.warning("Diagram generator not available")
            return None
    
    def _split_content(self, text: str, max_size: int) -> list[str]:
        """Split content into manageable chunks"""
        if len(text) <= max_size:
            return [text]
        
        chunks = []
        sentences = text.split('. ')
        current_chunk = ""
        
        for sentence in sentences:
            if len(current_chunk + sentence + '. ') <= max_size:
                current_chunk += sentence + '. '
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = sentence + '. '
        
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        return chunks
    
    def _generate_notes_chunk(self, content_chunk: str, content_type: str = "video") -> str:
        """Generate notes for a single chunk"""
        prompt = self._get_notes_prompt(content_chunk, content_type)
        
        try:
            response = self.client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert AI learning assistant helping students learn complex material efficiently through bite-sized, focused notes."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.3,
                max_tokens=3000,
                top_p=0.9
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            logger.error(f"Error calling Groq API: {e}")
            raise
    
    def _generate_notes_multiple_chunks(self, chunks: list[str], content_type: str = "video") -> str:
        """Generate and combine notes from multiple chunks maintaining sequential flow"""
        all_notes = []
        
        for i, chunk in enumerate(chunks):
            logger.info(f"Processing chunk {i+1}/{len(chunks)}")
            
            try:
                # Use specialized prompt for chunk processing to maintain continuity
                chunk_notes = self._generate_notes_chunk_sequential(chunk, content_type, i+1, len(chunks))
                if chunk_notes:
                    # Validate that the chunk has proper structure
                    validated_notes = self._validate_and_fix_notes_structure(chunk_notes)
                    all_notes.append(validated_notes)
            except Exception as e:
                logger.error(f"Failed to process chunk {i+1}: {e}")
                all_notes.append(f"## Section {i+1} - Processing Error\n\n*[Error processing this section: {str(e)}]*")
        
        if not all_notes:
            return None
        
        # Combine all notes with a header
        if content_type == "pdf":
            combined_notes = "# Complete Document Notes\n\n"
            combined_notes += "*This content has been automatically generated from the PDF document and organized into structured learning notes.*\n\n"
        elif content_type == "study":
            combined_notes = "# Study Notes\n\n"
            combined_notes += "*This content has been automatically generated and organized into structured learning notes.*\n\n"
        else:
            combined_notes = "# Complete Course Notes\n\n"
            combined_notes += "*This content has been automatically generated from the video transcription and organized into structured learning notes.*\n\n"
        
        combined_notes += "---\n\n"
        combined_notes += "\n\n".join(all_notes)
        
        return combined_notes
    
    def _generate_notes_chunk_sequential(self, content_chunk: str, content_type: str, chunk_num: int, total_chunks: int) -> str:
        """Generate notes for a chunk with sequential context"""
        prompt = self._get_sequential_notes_prompt(content_chunk, content_type, chunk_num, total_chunks)
        
        try:
            response = self.client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert AI learning assistant helping students learn complex material efficiently. You specialize in creating sequential, bite-sized notes that maintain logical flow with short, focused sections."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.3,
                max_tokens=3000,
                top_p=0.9
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            logger.error(f"Error calling Groq API for sequential chunk: {e}")
            raise
    
    def _validate_and_fix_notes_structure(self, notes: str) -> str:
        """Validate and fix notes structure to ensure each section has title and content"""
        lines = notes.split('\n')
        fixed_lines = []
        current_section = None
        current_content = []
        
        for line in lines:
            stripped_line = line.strip()
            
            # Check if this is a heading (starts with ##)
            if stripped_line.startswith('##') and not stripped_line.startswith('###'):
                # Save previous section if it exists
                if current_section:
                    content_text = '\n'.join(current_content).strip()
                    
                    # Check if content is insufficient (empty, too short, or just bullet points)
                    if not content_text or len(content_text) < 150 or self._is_content_insufficient(content_text):
                        logger.warning(f"Section '{current_section.strip()}' has insufficient content, regenerating...")
                        # Try to regenerate content for this specific section
                        enhanced_content = self._generate_enhanced_section_content(current_section.strip(), content_text)
                        content_text = enhanced_content if enhanced_content else self._get_fallback_content(current_section.strip())
                    
                    fixed_lines.append(current_section)
                    fixed_lines.append('')
                    # Always use the processed content_text (either original if sufficient, or enhanced/fallback)
                    fixed_lines.append(content_text)
                    fixed_lines.append('')
                
                # Start new section
                current_section = line
                current_content = []
            else:
                # Add to current content
                current_content.append(line)
        
        # Handle the last section
        if current_section:
            content_text = '\n'.join(current_content).strip()
            
            # Check if content is insufficient
            if not content_text or len(content_text) < 150 or self._is_content_insufficient(content_text):
                logger.warning(f"Final section '{current_section.strip()}' has insufficient content, regenerating...")
                enhanced_content = self._generate_enhanced_section_content(current_section.strip(), content_text)
                content_text = enhanced_content if enhanced_content else self._get_fallback_content(current_section.strip())
            
            fixed_lines.append(current_section)
            fixed_lines.append('')
            fixed_lines.append(content_text)
        
        return '\n'.join(fixed_lines)

    def _split_text_by_word_limit(self, text: str, max_words: int) -> list[str]:
        """Split a text into chunks not exceeding max_words, preferring sentence boundaries."""
        import re
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', str(text or '').strip()) if s.strip()]
        chunks: list[str] = []
        current: list[str] = []
        count = 0
        for s in sentences:
            words = s.split()
            if not words:
                continue
            if count + len(words) <= max_words:
                current.append(s)
                count += len(words)
            else:
                if current:
                    chunks.append(' '.join(current).strip())
                    current = []
                    count = 0
                # If the sentence itself is longer than max_words, hard-split by words
                while len(words) > max_words:
                    chunks.append(' '.join(words[:max_words]).strip())
                    words = words[max_words:]
                if words:
                    current = [' '.join(words).strip()]
                    count = len(words)
        if current:
            chunks.append(' '.join(current).strip())
        # Handle case when there were no sentence boundaries
        if not chunks and text:
            words = text.split()
            for i in range(0, len(words), max_words):
                chunks.append(' '.join(words[i:i+max_words]).strip())
        return chunks

    def _enforce_word_limit_on_notes(self, notes: str, max_words: int = 50) -> str:
        """Ensure each note section has <= max_words words; split longer sections into continuations."""
        lines = (notes or '').splitlines()
        result_lines: list[str] = []
        current_title: str | None = None
        current_content: list[str] = []

        def flush_section():
            nonlocal result_lines, current_title, current_content
            if current_title is None:
                # No title context; dump content as-is
                for l in current_content:
                    result_lines.append(l)
                current_content = []
                return
            content_text = '\n'.join(current_content).strip()
            if not content_text:
                result_lines.append(current_title)
                result_lines.append('')
            else:
                chunks = self._split_text_by_word_limit(content_text, max_words)
                if len(chunks) <= 1:
                    result_lines.append(current_title)
                    result_lines.append('')
                    result_lines.append(chunks[0] if chunks else content_text)
                    result_lines.append('')
                else:
                    # Emit first as original title, subsequent with (cont. N)
                    for idx, chunk in enumerate(chunks):
                        if idx == 0:
                            title_out = current_title
                        else:
                            if current_title.strip().startswith('##'):
                                base = current_title.strip()[2:].strip()
                                title_out = f"## {base} (cont. {idx+1})"
                            else:
                                title_out = f"{current_title} (cont. {idx+1})"
                        result_lines.append(title_out)
                        result_lines.append('')
                        result_lines.append(chunk)
                        result_lines.append('')
            current_title = None
            current_content = []

        for line in lines:
            striped = line.strip()
            if striped.startswith('##') and not striped.startswith('###'):
                if current_title is not None:
                    flush_section()
                current_title = striped
                current_content = []
            else:
                if current_title is None:
                    result_lines.append(line)
                else:
                    current_content.append(line)
        if current_title is not None:
            flush_section()
        return '\n'.join(result_lines).strip()

    def _is_content_insufficient(self, content: str) -> bool:
        """Check if content is insufficient (just bullet points, too short, or generic)"""
        if not content or len(content.strip()) < 100:
            return True
        
        # Remove empty lines and strip whitespace
        lines = [line.strip() for line in content.split('\n') if line.strip()]
        
        # Check if content is mostly bullet points or very short lines
        bullet_lines = sum(1 for line in lines if line.startswith(('•', '-', '*', '1.', '2.', '3.', '4.', '5.')))
        total_lines = len(lines)
        
        # If more than 70% are bullet points and no substantial paragraphs, it's insufficient
        if total_lines > 0 and (bullet_lines / total_lines) > 0.7:
            # Check if there are any substantial paragraphs (>50 chars)
            substantial_lines = [line for line in lines if len(line) > 50 and not line.startswith(('•', '-', '*', '1.', '2.', '3.', '4.', '5.'))]
            if len(substantial_lines) < 2:
                return True
        
        # Check for generic placeholder content
        generic_phrases = [
            "this section covers",
            "important concepts",
            "key principles",
            "essential information",
            "further elaboration",
            "key takeaways",
            "in summary",
            "to conclude",
            "important points include",
            "main ideas are"
        ]
        
        content_lower = content.lower()
        generic_count = sum(1 for phrase in generic_phrases if phrase in content_lower)
        if generic_count >= 3:  # Too many generic phrases
            return True
        
        # Check for repetitive sentence structures
        sentences = [s.strip() for s in content.split('.') if len(s.strip()) > 10]
        if len(sentences) >= 3:
            # Check if too many sentences start with similar patterns
            similar_starts = 0
            common_starts = ["this", "the", "it", "these", "in", "for", "with", "by"]
            for start_word in common_starts:
                count = sum(1 for s in sentences if s.lower().startswith(start_word))
                if count > len(sentences) * 0.4:  # More than 40% start with same word
                    similar_starts += 1
            
            if similar_starts >= 2:  # Multiple repetitive patterns
                return True
        
        return False
    
    def _generate_enhanced_section_content(self, section_title: str, existing_content: str) -> str:
        """Generate enhanced content for a specific section"""
        if not self.is_available():
            return None
        
        try:
            prompt = f"""You are an expert educational content creator. A section titled "{section_title}" needs focused, concise content.

Current content (if any):
{existing_content if existing_content else "No content provided"}

Your task is to create focused, educational content for this section that includes:

1. **Concise explanation** (50-60 words maximum) that covers the key concept
2. **Clear definitions** of important terms in simple language
3. **One practical example** when relevant
4. **Essential information** that students need to know
5. **Educational value** in a quick-to-read format

Requirements:
- Keep content to 50-60 words maximum
- Focus on one main concept
- Make it clear and easy to understand
- Ensure it's suitable for quick review
- Prioritize essential information only

Generate focused content (50-60 words) for the section "{section_title}":"""

            response = self.client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert educational content creator specializing in concise, focused explanatory content for quick study and review."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.4,
                max_tokens=200,
                top_p=0.9
            )
            
            generated_content = response.choices[0].message.content.strip()
            logger.info(f"Enhanced content generated for section: {section_title}")
            return generated_content
            
        except Exception as e:
            logger.error(f"Error generating enhanced content for section '{section_title}': {e}")
            return None
    
    def _get_fallback_content(self, section_title: str) -> str:
        """Generate fallback content when AI enhancement fails"""
        # Extract key terms from the title for more specific fallback content
        title_clean = section_title.replace('#', '').strip()
        
        return f"""This section covers {title_clean.lower()}, an important concept in this material. It includes key principles and practical applications that students need to understand. The topic connects to other areas of study and provides essential knowledge for further learning."""
    
    def _get_notes_prompt(self, content: str, content_type: str = "video") -> str:
        """Get the prompt for notes generation based on content type"""
        base_prompt = ""
        if content_type == "pdf":
            base_prompt = self._get_pdf_prompt(content)
        elif content_type == "study":
            base_prompt = self._get_study_prompt(content)
        else:
            base_prompt = self._get_video_prompt(content)
        
        # Add uniqueness requirements
        uniqueness_addition = self._get_variation_prompt_addition(content_type)
        return base_prompt + uniqueness_addition
    
    def _get_sequential_notes_prompt(self, content: str, content_type: str, chunk_num: int, total_chunks: int) -> str:
        """Get prompt for sequential chunk processing"""
        context_info = f"This is part {chunk_num} of {total_chunks} sequential sections from the same content."
        uniqueness_addition = self._get_variation_prompt_addition(f"{content_type}_chunk_{chunk_num}")
        
        if content_type == "pdf":
            return f"""{context_info}
            
You are processing a PDF document sequentially. Create bite-sized study notes that maintain the document's logical flow and academic accuracy.

CRITICAL REQUIREMENTS:
1. **Each section should contain 50-60 words maximum** - keep explanations concise and focused
2. **Maintain sequential order** - organize content as it appears in the source
3. **Academic accuracy** - preserve technical precision in short format
4. **Comprehensive coverage** - break complex topics into multiple short sections

Instructions:
- Use ## for main concepts
- Break down complex topics into multiple short sections
- Each section must contain:
  * Clear, specific title
  * 50-60 words maximum of focused explanation
  * Key concepts and definitions in simple terms
  * One essential example when relevant
- Maintain the natural flow of the document
- Create many small, digestible sections

Content to process:
{content}

Generate sequential, short-format notes (50-60 words per section):""" + uniqueness_addition

        elif content_type == "study":
            return f"""{context_info}
            
You are creating bite-sized study notes from extracted text content. Organize the material sequentially with short, focused sections.

CRITICAL REQUIREMENTS:
1. **Each section should contain 50-60 words maximum** - keep explanations concise and focused
2. **Sequential organization** - follow the natural flow of the content
3. **Comprehensive coverage** - break complex topics into multiple short sections
4. **Study-friendly format** - make content quick to read and review

Instructions:
- Use ## for main concepts
- Break down complex topics into multiple short sections
- Each section must contain:
  * Clear, specific title
  * 50-60 words maximum of focused explanation
  * Key points and concepts in simple terms
  * One practical example when relevant
- Organize content from beginning to end
- Create many small, digestible sections

Content to process:
{content}

Generate sequential, short-format study notes (50-60 words per section):""" + uniqueness_addition

        else:  # video content
            return f"""{context_info}
            
You are processing a video transcription sequentially. Create bite-sized learning notes that follow the instructor's teaching sequence.

CRITICAL REQUIREMENTS:
1. **Each section should contain 50-60 words maximum** - keep explanations concise and focused
2. **Follow the lecture sequence** - maintain the instructor's teaching order
3. **Educational flow** - preserve the learning progression in short sections
4. **Comprehensive coverage** - break complex topics into multiple short sections

Instructions:
- Use ## for main concepts covered
- Break down complex topics into multiple short sections
- Each section must contain:
  * Clear, specific title reflecting the concept
  * 50-60 words maximum of focused explanation
  * Key concepts and definitions in simple terms
  * One essential example from the instructor when relevant
- Follow the chronological order of the lecture
- Maintain the educational sequence from start to finish
- Create many small, digestible sections for easy review

Transcription to process:
{content}

Generate sequential, short-format learning notes (50-60 words per section):""" + uniqueness_addition
    
    def _get_video_prompt(self, transcription: str) -> str:
        """Get the prompt specifically for video transcriptions"""
        return f"""You are an expert AI learning assistant helping students learn complex material efficiently through bite-sized, focused notes.
You are given a transcript from a long educational video or course. Your task is to transform this raw transcription into well-structured, student-friendly notes with short, digestible sections.

CRITICAL REQUIREMENTS - BITE-SIZED SECTIONS:
1. **Each section should contain 50-60 words maximum** - keep explanations concise and focused
2. **Sequential organization** - follow the instructor's teaching sequence from start to finish
3. **Comprehensive coverage** - break complex topics into multiple short sections
4. **Quick review format** - make content easy to scan and review

Instructions:
1. Organize the notes with many short sections based on concepts in chronological order.
2. For each concept, include:
   - A clear, specific title (## Concept Title)
   - **50-60 words maximum of focused explanation**
   - Key definitions in simple terms
   - One essential example from the lecture when relevant
3. Use clear formatting:
   - Main concepts as ## Concept Title
   - Break complex topics into multiple short sections
   - **PRIMARY FOCUS: Concise, focused explanations**
   - Bold important terms within explanations
4. **CONTENT STRUCTURE FOR EACH SECTION:**
   - Title (## Concept)
   - Short, focused explanation (50-60 words maximum)
   - Essential information only
5. Make the notes perfect for quick review and exam prep.
6. Remove filler words or repeated phrases from the transcription.
7. If the content is technical, provide simple explanations in short format.
8. **MAINTAIN SEQUENTIAL FLOW** - organize content from the beginning of the lecture to the end.
9. **CREATE MANY SHORT SECTIONS** - break down complex topics into multiple digestible pieces.

Here is the course transcript you need to process:

[TRANSCRIPT START]
{transcription}
[TRANSCRIPT END]

Now generate the structured learning notes with sequential organization and short-format sections (50-60 words each):"""

    def _get_pdf_prompt(self, pdf_content: str) -> str:
        """Get the prompt specifically for PDF documents"""
        return f"""You are an expert AI learning assistant specializing in academic document analysis and bite-sized note creation.
You are given content from a PDF document (textbook, research paper, manual, or academic material). Your task is to create short, focused study notes that preserve academic accuracy while being quick to read and review.

CRITICAL REQUIREMENTS:
1. **Each section should contain 50-60 words maximum** - keep explanations concise and focused
2. **Sequential organization** - follow the document's natural structure from beginning to end
3. **Academic accuracy** - preserve technical precision in short format
4. **Comprehensive coverage** - break complex topics into multiple short sections

Instructions:
1. **Document Structure Analysis**: Break down the document's content into many short, focused sections in sequential order.
2. **Academic Content Processing**: For each concept, provide:
   - **Clear, specific heading** (## Concept Title)
   - **50-60 words maximum of focused explanation**
   - **Key definitions** in simple terms
   - **One essential example** when relevant
   - **Critical insights** in concise format
3. **Formatting Requirements**:
   - Use ## for main concepts
   - Break complex topics into multiple short sections
   - **Bold** important terms within explanations
   - Focus on essential information only
4. **Academic Standards**:
   - Maintain technical accuracy in short format
   - Preserve important details concisely
   - Include key formulas or data when essential
   - Explain complex concepts simply but accurately
5. **Study-Friendly Features**:
   - Create many small, digestible sections
   - Perfect for quick review and scanning
   - Easy to memorize and recall
   - **MAINTAIN SEQUENTIAL FLOW** - organize from document beginning to end

Here is the PDF document content you need to process:

[DOCUMENT START]
{pdf_content}
[DOCUMENT END]

Now generate short-format, structured study notes with sequential organization (50-60 words per section):"""
    
    def _get_study_prompt(self, content: str) -> str:
        """Get the prompt specifically for general study content (OCR, extracted text, etc.)"""
        return f"""You are an expert AI learning assistant specializing in creating bite-sized study notes from various text sources.
You are given extracted text content that may come from OCR processing, document extraction, or other text sources. Your task is to create short, focused study notes that organize the material for quick and effective learning.

CRITICAL REQUIREMENTS:
1. **Each section should contain 50-60 words maximum** - keep explanations concise and focused
2. **Sequential organization** - follow the natural flow of the content from beginning to end
3. **Comprehensive coverage** - break complex topics into multiple short sections
4. **Quick review format** - make content easy to scan and memorize

Instructions:
1. **Content Analysis**: Break down the content into many short, focused sections in logical, sequential order.
2. **Study Note Creation**: For each concept, provide:
   - **Clear, specific title** (## Concept Title)
   - **50-60 words maximum of focused explanation**
   - **Key concepts and definitions** in simple terms
   - **One essential example** when relevant
   - **Important principles** in concise format
3. **Formatting Requirements**:
   - Use ## for main concepts
   - Break complex topics into multiple short sections
   - **Bold** important terms within explanations
   - Focus on essential information only
4. **Study Standards**:
   - Make content quick to read and understand
   - Preserve important details concisely
   - Explain complex concepts simply but accurately
   - Create logical flow between short sections
5. **Learning Features**:
   - Create many small, digestible sections
   - Perfect for quick review and memorization
   - Easy to scan and recall
   - **MAINTAIN SEQUENTIAL FLOW** - organize content from beginning to end
   - Make notes ideal for rapid review and exam preparation

Here is the content you need to process:

[CONTENT START]
{content}
[CONTENT END]

Now generate short-format, structured study notes with sequential organization (50-60 words per section):"""

# Global instance
groq_generator = GroqNotesGenerator()