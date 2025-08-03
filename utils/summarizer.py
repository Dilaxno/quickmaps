import logging
import json
import re
from typing import List, Dict, Optional, Tuple
import os
from collections import Counter
from .groq_client import sync_chat_completion, sync_generate_text
# Removed transcript_segmenter - now using direct token-based processing

# Ollama-only approach - no transformers dependency needed

logger = logging.getLogger(__name__)

def count_tokens(text: str) -> int:
    """
    Estimate token count for text (rough approximation: 1 token ≈ 4 characters)
    This is a simple approximation suitable for our use case
    """
    return len(text) // 4

def split_transcript_into_chapters(segments: List[Dict], max_tokens: int = 8000) -> List[Dict]:
    """
    Split transcript segments into chapters based on token count
    
    Args:
        segments: List of transcript segments with text and timestamps
        max_tokens: Maximum tokens per chapter (default 8000)
        
    Returns:
        List of chapter dictionaries with combined text and metadata
    """
    if not segments:
        return []
    
    chapters = []
    current_chapter = {
        'text': '',
        'start_time': None,
        'end_time': None,
        'segments': []
    }
    current_tokens = 0
    
    for segment in segments:
        segment_text = segment.get('text', '')
        segment_tokens = count_tokens(segment_text)
        
        # If adding this segment would exceed max tokens and we have content, start new chapter
        if current_tokens + segment_tokens > max_tokens and current_chapter['text']:
            # Finalize current chapter
            chapters.append(current_chapter)
            
            # Start new chapter
            current_chapter = {
                'text': segment_text,
                'start_time': segment.get('start'),
                'end_time': segment.get('end'),
                'segments': [segment]
            }
            current_tokens = segment_tokens
        else:
            # Add to current chapter
            if current_chapter['start_time'] is None:
                current_chapter['start_time'] = segment.get('start')
            
            current_chapter['text'] += ' ' + segment_text if current_chapter['text'] else segment_text
            current_chapter['end_time'] = segment.get('end')
            current_chapter['segments'].append(segment)
            current_tokens += segment_tokens
    
    # Add the last chapter if it has content
    if current_chapter['text']:
        chapters.append(current_chapter)
    
    # Add chapter metadata
    for i, chapter in enumerate(chapters):
        chapter['chapter_id'] = i + 1
        chapter['token_count'] = count_tokens(chapter['text'])
        chapter['duration'] = (chapter['end_time'] or 0) - (chapter['start_time'] or 0)
        chapter['segment_count'] = len(chapter['segments'])
    
    logger.info(f"📚 Split transcript into {len(chapters)} chapters")
    for i, chapter in enumerate(chapters):
        logger.info(f"   Chapter {i+1}: {chapter['token_count']} tokens, {chapter['duration']:.1f}s duration")
    
    return chapters

class LlamaEducationalSummarizer:
    """
    Advanced educational summarizer using LLaMA 3.1 8B model via Groq API
    Specifically designed for extracting structured knowledge from video course transcripts
    Falls back to structured text processing if Groq API is unavailable
    """
    
    def __init__(self, enable_llama=True):
        """Initialize the LLaMA summarizer pipeline"""
        self.groq_model = "llama-3.1-8b-instant"
        self.use_fallback = True  # Start with fallback, try to initialize later
        self.use_groq = False
        self.enable_llama = enable_llama
        
        # Try to initialize if llama is enabled
        if self.enable_llama:
            self._initialize_model()
        else:
            logger.info("📚 LLaMA model loading disabled, using structured text processing fallback")
    
    def _initialize_model(self):
        """Initialize the LLaMA model via Groq API only"""
        
        # Try Groq llama model
        if self._try_groq_initialization():
            return
        
        # Groq API failed, use text processing fallback
        logger.warning("❌ Failed to initialize Groq LLaMA, using text processing fallback")
        self.use_fallback = True
    
    def _try_groq_initialization(self):
        """Try to initialize Groq LLaMA model"""
        try:
            logger.info("🌐 Trying to initialize Groq LLaMA model...")
            
            # Test if we can generate with Groq API
            test_response = sync_generate_text(
                model=self.groq_model,
                prompt="Test connection",
                max_tokens=10
            )
            
            if test_response:
                self.use_groq = True
                self.use_fallback = False
                logger.info("✅ Groq LLaMA model initialized successfully!")
                return True
            else:
                logger.warning("❌ Groq LLaMA test failed")
                return False
                
        except Exception as e:
            logger.warning(f"❌ Failed to initialize Groq LLaMA: {e}")
            return False
    

    
    def _create_educational_prompt(self, transcript: str, is_segment: bool = False, segment_info: str = "") -> str:
        """Create the detailed educational prompt for structured summarization"""
        
        # For segments, use longer length since individual segments are typically shorter
        max_transcript_length = 2000 if is_segment else 3000
        truncated_transcript = transcript[:max_transcript_length]
        if len(transcript) > max_transcript_length:
            truncated_transcript += "... [content truncated]"
        
        segment_context = f"\n\nSegment Context: {segment_info}" if segment_info else ""
        
        if is_segment:
            prompt = f"""Analyze this segment of educational content and extract key learning points in JSON format.

Content Segment:
{truncated_transcript}{segment_context}

Provide a JSON response with this structure for this segment:
{{
  "segment_title": "Title for this segment",
  "key_concepts": ["concept1", "concept2"],
  "definitions": {{"term": "definition"}},
  "summary": "Brief summary of this segment in 1-2 sentences",
  "important_facts": ["fact1", "fact2"],
  "segment_questions": ["question1?", "question2?"]
}}

Focus only on content from this specific segment. Respond only with valid JSON."""
        else:
            prompt = f"""Analyze this educational content and extract key learning points in JSON format.

Content:
{truncated_transcript}

Provide a JSON response with this structure:
{{
  "title": "Main topic title",
  "key_concepts": ["concept1", "concept2", "concept3"],
  "definitions": {{"term": "definition"}},
  "summary": "Brief summary in 2-3 sentences",
  "important_facts": ["fact1", "fact2"],
  "quiz_questions": ["question1?", "question2?"]
}}

Respond only with valid JSON."""

        return prompt
    
    def _generate_summary_with_llama(self, transcript: str) -> Dict:
        """Generate structured summary using LLaMA model via Groq API"""
        try:
            if self.use_fallback:
                return self._create_structured_summary_fallback(transcript)
            
            prompt = self._create_educational_prompt(transcript)
            
            logger.info(f"🧠 Generating educational summary with Groq LLaMA...")
            
            generated_text = None
            
            if self.use_groq:
                # Use Groq llama model
                system_prompt = """You are an expert educational assistant. Analyze educational content and provide structured summaries in JSON format. Focus on key concepts, definitions, and learning objectives."""
                
                generated_text = sync_chat_completion(
                    model=self.groq_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.3,  # Lower temperature for more structured output
                    max_tokens=1200
                )
            else:
                # Should not reach here since we removed HF fallback
                logger.error("Unexpected state: not using hosted API but not using fallback either")
                return self._create_structured_summary_fallback(transcript)
            
            if not generated_text:
                logger.warning("No response generated, using fallback")
                return self._create_structured_summary_fallback(transcript)
            
            logger.info(f"📝 Generated {len(generated_text)} characters")
            
            # Try to parse as JSON, fallback to structured parsing if needed
            summary_data = self._parse_response(generated_text)
            
            return summary_data
            
        except Exception as e:
            logger.error(f"❌ Error generating summary with LLaMA: {e}")
            return self._create_structured_summary_fallback(transcript)
    
    def _create_structured_summary_fallback(self, transcript: str) -> Dict:
        """Create structured summary using rule-based approach when AI is unavailable"""
        logger.info("📚 Using structured text analysis fallback")
        
        # Split transcript into sentences
        sentences = re.split(r'[.!?]+', transcript)
        sentences = [s.strip() for s in sentences if s.strip()]
        
        # Extract title from first few sentences
        title = "Educational Content Analysis"
        if sentences:
            first_sentence = sentences[0][:50]
            if any(word in first_sentence.lower() for word in ['welcome', 'today', 'lesson', 'learn', 'course']):
                title = f"Lesson: {first_sentence}..."
        
        # Create summary from first few sentences
        summary_sentences = sentences[:3]
        summary = " ".join(summary_sentences) if summary_sentences else "Content analysis in progress."
        
        # Extract key points (sentences with keywords)
        key_point_keywords = ['important', 'key', 'main', 'remember', 'note', 'first', 'second', 'third']
        key_points = []
        for sentence in sentences[:10]:
            if any(keyword in sentence.lower() for keyword in key_point_keywords):
                key_points.append(sentence.strip())
        
        if not key_points:
            key_points = sentences[:5]  # Fallback to first sentences
        
        # Extract definitions (sentences with "is", "means", "refers to")
        definition_patterns = [r'(\w+)\s+is\s+(.+)', r'(\w+)\s+means\s+(.+)', r'(\w+)\s+refers to\s+(.+)']
        definitions = []
        
        for sentence in sentences:
            for pattern in definition_patterns:
                match = re.search(pattern, sentence, re.IGNORECASE)
                if match and len(definitions) < 5:
                    term = match.group(1).strip()
                    definition = match.group(2).strip()
                    definitions.append({"term": term, "definition": definition})
        
        # Extract examples (sentences with "example", "for instance", "such as")
        example_keywords = ['example', 'for instance', 'such as', 'like', 'including']
        examples = []
        for sentence in sentences:
            if any(keyword in sentence.lower() for keyword in example_keywords):
                examples.append(sentence.strip())
                if len(examples) >= 4:
                    break
        
        # Extract questions
        questions = []
        for sentence in sentences:
            if sentence.strip().endswith('?'):
                questions.append(sentence.strip())
                if len(questions) >= 5:
                    break
        
        # Add some default questions if none found
        if not questions:
            questions = [
                "What are the main concepts covered in this content?",
                "How can this knowledge be applied practically?",
                "What are the key takeaways from this lesson?"
            ]
        
        # Extract common mistakes
        mistake_keywords = ['mistake', 'error', 'wrong', 'avoid', 'don\'t', 'never', 'common problem']
        common_mistakes = []
        for sentence in sentences:
            if any(keyword in sentence.lower() for keyword in mistake_keywords):
                common_mistakes.append(sentence.strip())
                if len(common_mistakes) >= 3:
                    break
        
        # Visual notes (look for visual references)
        visual_keywords = ['diagram', 'chart', 'graph', 'image', 'visual', 'picture', 'see', 'look at']
        visual_notes = []
        for sentence in sentences:
            if any(keyword in sentence.lower() for keyword in visual_keywords):
                visual_notes.append(sentence.strip())
                if len(visual_notes) >= 3:
                    break
        
        # Create simple chapters based on content length
        chapters = []
        total_length = len(transcript)
        if total_length > 500:
            mid_point = total_length // 2
            chapters = [
                {
                    "title": "Introduction",
                    "summary": "Opening concepts and overview",
                    "timestamp": "0:00-5:00"
                },
                {
                    "title": "Main Content", 
                    "summary": "Core educational material and examples",
                    "timestamp": "5:00-15:00"
                }
            ]
            if total_length > 1500:
                chapters.append({
                    "title": "Advanced Topics",
                    "summary": "Detailed concepts and applications", 
                    "timestamp": "15:00-25:00"
                })
        
        return {
            "title": title,
            "summary": summary,
            "key_points": key_points[:8],  # Limit to 8 key points
            "definitions": definitions[:5],
            "examples": examples[:4],
            "questions": questions[:6],
            "common_mistakes": common_mistakes[:3],
            "visual_notes": visual_notes[:3],
            "chapters": chapters
        }
    
    def _parse_response(self, response_text: str) -> Dict:
        """Parse the model response into structured data"""
        try:
            # Remove markdown code blocks if present
            cleaned_text = re.sub(r'```(?:json)?\s*', '', response_text)
            cleaned_text = re.sub(r'```\s*$', '', cleaned_text)
            
            # First, try to extract JSON from the response with improved regex
            json_match = re.search(r'\{[\s\S]*?\}(?=\s*$|\s*\n\s*[A-Z]|\s*\*\*)', cleaned_text)
            if json_match:
                json_str = json_match.group()
                
                # Clean up common JSON issues
                json_str = self._clean_json_string(json_str)
                
                try:
                    parsed_data = json.loads(json_str)
                    
                    # Handle different response formats
                    if "chapters" in parsed_data and isinstance(parsed_data["chapters"], list):
                        # Old chapter-based format
                        return self._convert_chapter_format(parsed_data)
                    elif "title" in parsed_data and "key_concepts" in parsed_data:
                        # New simplified format - convert to legacy format
                        return self._convert_simple_format(parsed_data)
                    
                    return parsed_data
                    
                except json.JSONDecodeError as e:
                    logger.warning(f"JSON parsing failed after cleaning: {e}")
                    # Try a more aggressive extraction
                    return self._extract_json_aggressively(cleaned_text)
            
            # If no JSON found, parse manually
            logger.warning("No JSON found in response, using fallback parsing...")
            return self._manual_parse_response(cleaned_text)
            
        except Exception as e:
            logger.warning(f"Response parsing failed: {e}, using fallback parsing...")
            return self._manual_parse_response(response_text)
    
    def _clean_json_string(self, json_str: str) -> str:
        """Clean up common JSON formatting issues"""
        # Remove trailing commas before closing braces/brackets
        json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)
        
        # Fix common quote issues
        json_str = json_str.replace('""', '"')
        
        # Remove any text after the closing brace
        json_str = re.sub(r'\}.*$', '}', json_str, flags=re.DOTALL)
        
        return json_str.strip()
    
    def _extract_json_aggressively(self, response_text: str) -> Dict:
        """Try to extract JSON more aggressively when standard parsing fails"""
        try:
            # Look for key-value patterns and build JSON manually
            title_match = re.search(r'"title":\s*"([^"]*)"', response_text)
            summary_match = re.search(r'"summary":\s*"([^"]*)"', response_text)
            
            # Extract arrays
            key_concepts_match = re.search(r'"key_concepts":\s*\[(.*?)\]', response_text, re.DOTALL)
            important_facts_match = re.search(r'"important_facts":\s*\[(.*?)\]', response_text, re.DOTALL)
            quiz_questions_match = re.search(r'"quiz_questions":\s*\[(.*?)\]', response_text, re.DOTALL)
            
            # Extract definitions object
            definitions_match = re.search(r'"definitions":\s*\{(.*?)\}', response_text, re.DOTALL)
            
            # Build the result
            result = {
                "title": title_match.group(1) if title_match else "Educational Content",
                "summary": summary_match.group(1) if summary_match else "",
                "key_concepts": [],
                "definitions": {},
                "important_facts": [],
                "quiz_questions": []
            }
            
            # Parse arrays
            if key_concepts_match:
                concepts = re.findall(r'"([^"]*)"', key_concepts_match.group(1))
                result["key_concepts"] = concepts
            
            if important_facts_match:
                facts = re.findall(r'"([^"]*)"', important_facts_match.group(1))
                result["important_facts"] = facts
            
            if quiz_questions_match:
                questions = re.findall(r'"([^"]*)"', quiz_questions_match.group(1))
                result["quiz_questions"] = questions
            
            # Parse definitions
            if definitions_match:
                def_pairs = re.findall(r'"([^"]*)"\s*:\s*"([^"]*)"', definitions_match.group(1))
                result["definitions"] = dict(def_pairs)
            
            return self._convert_simple_format(result)
            
        except Exception as e:
            logger.warning(f"Aggressive JSON extraction failed: {e}")
            return self._manual_parse_response(response_text)
    
    def _convert_chapter_format(self, chapter_data: Dict) -> Dict:
        """Convert new chapter-based format to legacy format for compatibility"""
        try:
            chapters = chapter_data.get("chapters", [])
            if not chapters:
                return self._create_empty_summary()
            
            # Combine all chapters into a single summary
            all_key_concepts = []
            all_definitions = []
            all_important_facts = []
            all_quiz_questions = []
            chapter_summaries = []
            
            for chapter in chapters:
                # Collect key concepts
                key_concepts = chapter.get("key_concepts", [])
                all_key_concepts.extend(key_concepts)
                
                # Collect definitions
                definitions = chapter.get("definitions", {})
                for term, definition in definitions.items():
                    all_definitions.append({"term": term, "definition": definition})
                
                # Collect important facts
                important_facts = chapter.get("important_facts", [])
                all_important_facts.extend(important_facts)
                
                # Collect quiz questions
                quiz_questions = chapter.get("quiz_questions", [])
                all_quiz_questions.extend(quiz_questions)
                
                # Collect chapter summaries
                chapter_title = chapter.get("title", "Chapter")
                chapter_summary = chapter.get("summary", "")
                if chapter_summary:
                    chapter_summaries.append(f"{chapter_title}: {chapter_summary}")
            
            # Create the main title from first chapter or general title
            main_title = chapters[0].get("title", "Educational Content") if chapters else "Educational Content"
            
            # Combine all chapter summaries
            combined_summary = " ".join(chapter_summaries) if chapter_summaries else "Educational content summary."
            
            # Create legacy format
            legacy_format = {
                "title": main_title,
                "summary": combined_summary,
                "key_points": all_key_concepts[:10],  # Limit to 10 key points
                "definitions": all_definitions[:8],   # Limit to 8 definitions
                "examples": all_important_facts[:5],  # Use important facts as examples
                "questions": all_quiz_questions[:6],  # Limit to 6 questions
                "common_mistakes": [],  # Not available in new format
                "visual_notes": [],     # Not available in new format
                "chapters": chapters    # Keep original chapters for reference
            }
            
            return legacy_format
            
        except Exception as e:
            logger.error(f"Error converting chapter format: {e}")
            return self._create_empty_summary()
    
    def _convert_simple_format(self, simple_data: Dict) -> Dict:
        """Convert new simplified format to legacy format for compatibility"""
        try:
            # Extract data from simplified format
            title = simple_data.get("title", "Educational Content")
            summary = simple_data.get("summary", "")
            key_concepts = simple_data.get("key_concepts", [])
            definitions_dict = simple_data.get("definitions", {})
            important_facts = simple_data.get("important_facts", [])
            quiz_questions = simple_data.get("quiz_questions", [])
            
            # Convert definitions from dict to list format
            definitions_list = []
            for term, definition in definitions_dict.items():
                definitions_list.append({"term": term, "definition": definition})
            
            # Create legacy format
            legacy_format = {
                "title": title,
                "summary": summary,
                "key_points": key_concepts[:10],  # Limit to 10 key points
                "definitions": definitions_list[:8],   # Limit to 8 definitions
                "examples": important_facts[:5],  # Use important facts as examples
                "questions": quiz_questions[:6],  # Limit to 6 questions
                "common_mistakes": [],  # Not provided in simple format
                "visual_notes": [],     # Not provided in simple format
                "chapters": []          # Not provided in simple format
            }
            
            return legacy_format
            
        except Exception as e:
            logger.error(f"Error converting simple format: {e}")
            return self._create_empty_summary()
    
    def _create_empty_summary(self) -> Dict:
        """Create an empty summary structure"""
        return {
            "title": "Educational Content",
            "summary": "Content analysis in progress.",
            "key_points": [],
            "definitions": [],
            "examples": [],
            "questions": [],
            "common_mistakes": [],
            "visual_notes": [],
            "chapters": []
        }
    
    def _manual_parse_response(self, text: str) -> Dict:
        """Manually parse the response if JSON parsing fails"""
        try:
            # Initialize structure
            summary_data = {
                "title": "Educational Content Summary",
                "summary": "",
                "key_points": [],
                "definitions": [],
                "examples": [],
                "questions": [],
                "common_mistakes": [],
                "visual_notes": [],
                "chapters": []
            }
            
            # Extract title
            title_match = re.search(r'(?:title|Title)[:\-\s]*(.+?)(?:\n|$)', text)
            if title_match:
                summary_data["title"] = title_match.group(1).strip().strip('"')
            
            # Extract summary  
            summary_match = re.search(r'(?:summary|Summary)[:\-\s]*(.+?)(?:\n\n|\n[A-Z]|$)', text, re.DOTALL)
            if summary_match:
                summary_data["summary"] = summary_match.group(1).strip().strip('"')
            
            # Extract key points
            key_points_section = re.search(r'(?:key.?points|Key.?Points)[:\-\s]*(.+?)(?:\n\n|\n[A-Z]|$)', text, re.DOTALL | re.IGNORECASE)
            if key_points_section:
                points = re.findall(r'[-•]\s*(.+)', key_points_section.group(1))
                summary_data["key_points"] = [point.strip().strip('"') for point in points]
            
            return summary_data
            
        except Exception as e:
            logger.error(f"Manual parsing failed: {e}")
            return self._create_basic_summary_structure()
    
    def _create_basic_summary_structure(self) -> Dict:
        """Create basic summary structure"""
        return {
            "title": "Educational Content",
            "summary": "Content processed successfully. Detailed analysis available.",
            "key_points": [
                "Educational content has been analyzed",
                "Structured summary generated",
                "Ready for mind map visualization"
            ],
            "definitions": [],
            "examples": [],
            "questions": [],
            "common_mistakes": [],
            "visual_notes": [],
            "chapters": []
        }
    
    def summarize(self, transcript: str) -> Dict:
        """Main method to summarize transcript"""
        if not transcript or len(transcript.strip()) < 50:
            logger.warning("Transcript too short for meaningful summary")
            return self._create_basic_summary_structure()
        
        logger.info(f"📚 Starting educational summarization of {len(transcript)} characters")
        
        try:
            summary_data = self._generate_summary_with_llama(transcript)
            logger.info("✅ Educational summary generated successfully!")
            return summary_data
            
        except Exception as e:
            logger.error(f"❌ Summarization failed: {e}")
            return self._create_structured_summary_fallback(transcript)
    
    def summarize_segments(self, segments: List[Dict]) -> Dict:
        """
        Public method to summarize transcript segments using chunk-based processing
        
        Args:
            segments: List of transcript segments with 'text' and optionally 'start'/'end' times
            
        Returns:
            Combined structured summary
        """
        return self.summarize_from_segments(segments)
    
    def summarize_from_segments(self, segments: List[Dict]) -> Dict:
        """
        Summarize content from transcript segments, processing each separately then combining
        
        Args:
            segments: List of transcript segments with 'text' and optionally 'start'/'end' times
            
        Returns:
            Combined structured summary
        """
        logger.info(f"📚 Processing {len(segments)} transcript segments separately...")
        
        segment_summaries = []
        total_processed = 0
        
        for i, segment in enumerate(segments):
            try:
                segment_text = segment.get('text', '')
                if not segment_text or len(segment_text.strip()) < 10:
                    continue
                
                # Create segment info for context
                start_time = segment.get('start', 0)
                end_time = segment.get('end', 0)
                segment_info = f"Segment {i+1}/{len(segments)}"
                if start_time and end_time:
                    segment_info += f" ({start_time:.1f}s - {end_time:.1f}s)"
                
                logger.info(f"🔍 Processing {segment_info}...")
                
                # Generate summary for this segment
                segment_summary = self._generate_segment_summary(segment_text, segment_info)
                
                if segment_summary:
                    segment_summary['segment_index'] = i
                    segment_summary['timestamp'] = f"{start_time:.1f}s - {end_time:.1f}s" if start_time and end_time else ""
                    segment_summaries.append(segment_summary)
                    total_processed += 1
                
            except Exception as e:
                logger.warning(f"❌ Failed to process segment {i}: {e}")
                continue
        
        logger.info(f"✅ Successfully processed {total_processed} segments")
        
        # Combine all segment summaries
        return self._combine_segment_summaries(segment_summaries)
    
    def _combine_segment_summaries(self, segment_summaries: List[Dict]) -> Dict:
        """Combine multiple segment summaries into a comprehensive final summary"""
        
        if not segment_summaries:
            logger.warning("No segment summaries to combine, using fallback")
            return self._create_structured_summary_fallback("No content available")
        
        logger.info(f"🔗 Combining {len(segment_summaries)} segment summaries...")
        
        # Combine all concepts, definitions, etc.
        all_concepts = []
        all_definitions = {}
        all_facts = []
        all_questions = []
        segment_chapters = []
        
        # Extract overall title from first segment or create one
        main_title = "Educational Video Summary"
        if segment_summaries:
            first_summary = segment_summaries[0]
            if first_summary.get('segment_title'):
                main_title = f"Course: {first_summary['segment_title']}"
        
        # Combine content from all segments
        combined_summary_parts = []
        
        for i, summary in enumerate(segment_summaries):
            # Collect key concepts
            concepts = summary.get('key_concepts', [])
            if isinstance(concepts, list):
                all_concepts.extend(concepts)
            
            # Collect definitions
            definitions = summary.get('definitions', {})
            if isinstance(definitions, dict):
                all_definitions.update(definitions)
            
            # Collect facts  
            facts = summary.get('important_facts', [])
            if isinstance(facts, list):
                all_facts.extend(facts)
            
            # Collect questions
            questions = summary.get('segment_questions', []) or summary.get('quiz_questions', [])
            if isinstance(questions, list):
                all_questions.extend(questions)
            
            # Add segment summary to combined summary
            segment_summary_text = summary.get('summary', '')
            if segment_summary_text:
                combined_summary_parts.append(segment_summary_text)
            
            # Create chapter from segment
            chapter = {
                "title": summary.get('segment_title', f'Segment {i+1}'),
                "summary": segment_summary_text,
                "timestamp": summary.get('timestamp', ''),
                "key_concepts": concepts[:3] if isinstance(concepts, list) else []
            }
            segment_chapters.append(chapter)
        
        # Remove duplicates and limit counts
        unique_concepts = list(dict.fromkeys([c for c in all_concepts if c]))[:10]
        unique_facts = list(dict.fromkeys([f for f in all_facts if f]))[:8]
        unique_questions = list(dict.fromkeys([q for q in all_questions if q]))[:8]
        
        # Create combined summary text
        combined_summary = " ".join(combined_summary_parts[:3])  # First 3 segments for summary
        if len(combined_summary_parts) > 3:
            combined_summary += f" ...and {len(combined_summary_parts) - 3} more topics covered."
        
        # Convert definitions format if needed
        definitions_list = []
        for term, definition in all_definitions.items():
            definitions_list.append({"term": term, "definition": definition})
        
        result = {
            "title": main_title,
            "summary": combined_summary or "Comprehensive educational content covering multiple topics.",
            "key_points": unique_concepts,
            "definitions": definitions_list[:5],
            "examples": [],  # Could be extracted from segments in future
            "questions": unique_questions,
            "common_mistakes": [],  # Could be extracted from segments in future  
            "visual_notes": [],  # Could be extracted from segments in future
            "chapters": segment_chapters
        }
        
        logger.info(f"✅ Combined summary created with {len(unique_concepts)} concepts, {len(definitions_list)} definitions, {len(unique_questions)} questions")
        
        return result
    
    def summarize_with_structure(self, structured_sections: List[Dict], structured_prompt: str) -> Dict:
        """
        Summarize using intelligently segmented sections and structured prompt
        
        Args:
            structured_sections: List of topical sections with metadata
            structured_prompt: Pre-built structured prompt for llama
            
        Returns:
            Dict: Educational summary
        """
        logger.info(f"📚 Starting structured summarization with {len(structured_sections)} sections")
        
        try:
            if self.use_groq:
                logger.info("🧠 Generating educational summary with Groq LLaMA using structured input...")
                
                system_prompt = """You are an expert educational assistant specializing in creating comprehensive learning materials from video transcripts. You analyze structured, segmented content to create educational summaries that enhance learning and comprehension."""
                
                # Estimate token count (rough: 1 token ≈ 4 characters)
                estimated_tokens = len(structured_prompt) // 4 + len(system_prompt) // 4
                logger.info(f"🔢 Estimated prompt tokens: {estimated_tokens}")
                
                # Use higher token limit for 70B models, optimized for 8B models
                max_tokens = 3000 if "70b" in self.groq_model else 1800
                
                generated_text = sync_chat_completion(
                    model=self.groq_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": structured_prompt}
                    ],
                    temperature=0.3,  # Lower temperature for more structured output
                    max_tokens=max_tokens
                )
            else:
                logger.info("Using fallback text processing (Groq not available)")
                return self._create_structured_summary_from_sections(structured_sections)
            
            if not generated_text:
                logger.warning("No response generated from structured prompt, using enhanced fallback")
                return self._create_structured_summary_from_sections(structured_sections)
            
            # Try to parse the JSON response
            try:
                # Extract JSON from response if it's wrapped in text
                json_match = re.search(r'\{.*\}', generated_text, re.DOTALL)
                if json_match:
                    json_text = json_match.group(0)
                    summary_data = json.loads(json_text)
                    
                    # Validate required fields
                    required_fields = ['title', 'summary', 'key_points', 'definitions', 'examples']
                    if all(field in summary_data for field in required_fields):
                        logger.info("✅ Successfully parsed structured llama response")
                        return summary_data
                
                logger.warning("Generated response not in expected JSON format, using enhanced fallback")
                return self._create_structured_summary_from_sections(structured_sections)
                
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse llama JSON response: {e}")
                return self._create_structured_summary_from_sections(structured_sections)
                
        except Exception as e:
            logger.error(f"❌ Structured summarization failed: {e}")
            return self._create_structured_summary_from_sections(structured_sections)
    
    def _create_structured_summary_from_sections(self, structured_sections: List[Dict]) -> Dict:
        """
        Create enhanced fallback summary using the intelligent section analysis
        """
        logger.info("📚 Creating enhanced structured summary from section analysis")
        
        # Aggregate information from all sections
        all_concepts = []
        all_text = []
        section_summaries = []
        
        for section in structured_sections:
            all_concepts.extend(section['key_concepts'])
            all_text.append(section['text'])
            
            # Create chapter entry
            chapter = {
                "title": section['topic_title'],
                "timestamp": f"{section['start_time']:.1f}s-{section['end_time']:.1f}s",
                "summary": self._create_section_summary(section),
                "key_concepts": section['key_concepts'][:3]
            }
            section_summaries.append(chapter)
        
        # Get most frequent concepts
        concept_counts = Counter(all_concepts)
        top_concepts = [concept for concept, count in concept_counts.most_common(10)]
        
        # Generate overall title
        if structured_sections:
            title = self._generate_overall_title(structured_sections)
        else:
            title = "Educational Content Summary"
        
        # Combine all text for fallback processing
        full_text = ' '.join(all_text)
        
        # Use existing fallback logic but enhanced with section info
        base_summary = self._create_structured_summary_fallback(full_text)
        
        # Enhance with section-specific information
        base_summary.update({
            "title": title,
            "chapters": section_summaries,
            "key_concepts_structured": top_concepts,
            "section_analysis": {
                "total_sections": len(structured_sections),
                "section_types": list(set(s['section_type'] for s in structured_sections)),
                "avg_section_duration": sum(s['duration'] for s in structured_sections) / len(structured_sections)
            }
        })
        
        return base_summary
    
    def _create_section_summary(self, section: Dict) -> str:
        """Create a brief summary for a section"""
        text = section['text']
        section_type = section['section_type']
        
        # Create type-specific summaries
        if section_type == 'definition':
            return f"Defines key concepts: {', '.join(section['key_concepts'][:3])}"
        elif section_type == 'example':
            return f"Provides examples and practical applications"
        elif section_type == 'process':
            return f"Explains step-by-step process or procedure"
        elif section_type == 'question':
            return f"Addresses questions and problem-solving"
        else:
            # Extract first sentence or create generic summary
            sentences = text.split('.')
            if sentences and len(sentences[0]) > 10:
                return sentences[0].strip() + "."
            else:
                return f"Covers {', '.join(section['key_concepts'][:2])} concepts"
    
    def _generate_overall_title(self, structured_sections: List[Dict]) -> str:
        """Generate an overall title from section analysis"""
        # Collect all concepts and titles
        all_concepts = []
        all_titles = []
        
        for section in structured_sections:
            all_concepts.extend(section['key_concepts'])
            all_titles.append(section['topic_title'])
        
        # Find most common concepts
        concept_counts = Counter(all_concepts)
        top_concepts = [concept for concept, count in concept_counts.most_common(3)]
        
        if len(top_concepts) >= 2:
            return f"{top_concepts[0].title()} and {top_concepts[1].title()}"
        elif len(top_concepts) >= 1:
            return f"{top_concepts[0].title()} - Educational Overview"
        else:
            return "Educational Content Summary"
    
    def summarize_full_transcript(self, full_transcript: str, segments: List[Dict]) -> Dict:
        """
        Summarize the full transcript as a single unit (when under 8000 tokens)
        
        Args:
            full_transcript: Complete transcript text
            segments: Original segments for metadata
            
        Returns:
            Dict: Educational summary
        """
        logger.info("📝 Summarizing full transcript as single unit")
        
        try:
            if self.use_groq:
                logger.info("🧠 Generating educational summary with Groq LLaMA...")
                
                system_prompt = """You are an expert educational assistant specializing in creating comprehensive learning materials from video transcripts. Analyze the complete transcript and create a structured educational summary that enhances learning and comprehension."""
                
                user_prompt = f"""Analyze this complete educational video transcript and provide a comprehensive JSON summary:

TRANSCRIPT:
{full_transcript[:6000]}{"... [content truncated]" if len(full_transcript) > 6000 else ""}

Provide a JSON response with this exact structure:
{{
  "title": "Descriptive title for the content",
  "summary": "Comprehensive 2-3 paragraph summary of the main content",
  "key_points": ["point1", "point2", "point3", "point4", "point5"],
  "definitions": {{"term1": "definition1", "term2": "definition2"}},
  "examples": ["example1", "example2", "example3"],
  "questions": ["question1?", "question2?", "question3?"],
  "common_mistakes": ["mistake1", "mistake2"],
  "visual_notes": ["visual element 1", "visual element 2"],
  "chapters": [
    {{
      "title": "Chapter 1 Title",
      "timestamp": "0:00-5:30",
      "summary": "Brief chapter summary",
      "key_concepts": ["concept1", "concept2"]
    }}
  ]
}}

Focus on educational value and learning outcomes. Respond only with valid JSON."""
                
                generated_text = sync_chat_completion(
                    model=self.groq_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.3,
                    max_tokens=2000
                )
            else:
                logger.info("Using fallback text processing (Groq not available)")
                return self._create_structured_summary_fallback(full_transcript)
            
            if not generated_text:
                logger.warning("No response generated, using fallback")
                return self._create_structured_summary_fallback(full_transcript)
            
            # Try to parse the JSON response
            try:
                # Extract JSON from response if it's wrapped in text
                json_match = re.search(r'\{.*\}', generated_text, re.DOTALL)
                if json_match:
                    json_str = json_match.group()
                    summary_data = json.loads(json_str)
                    
                    # Validate required fields
                    required_fields = ['title', 'summary', 'key_points', 'definitions', 'examples']
                    if all(field in summary_data for field in required_fields):
                        logger.info("✅ Successfully parsed full transcript response")
                        return summary_data
                
                logger.warning("Generated response not in expected JSON format, using fallback")
                return self._create_structured_summary_fallback(full_transcript)
                
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse JSON response: {e}")
                return self._create_structured_summary_fallback(full_transcript)
                
        except Exception as e:
            logger.error(f"❌ Full transcript summarization failed: {e}")
            return self._create_structured_summary_fallback(full_transcript)
    
    def summarize_chapters(self, chapters: List[Dict], segments: List[Dict]) -> Dict:
        """
        Summarize transcript that has been split into chapters
        
        Args:
            chapters: List of chapter dictionaries with text and metadata
            segments: Original segments for metadata
            
        Returns:
            Dict: Educational summary combining all chapters
        """
        logger.info(f"📚 Summarizing {len(chapters)} chapters")
        
        chapter_summaries = []
        all_key_points = []
        all_definitions = {}
        all_examples = []
        all_questions = []
        all_mistakes = []
        all_visual_notes = []
        
        # Process each chapter
        for chapter in chapters:
            logger.info(f"Processing Chapter {chapter['chapter_id']}: {chapter['token_count']} tokens")
            
            try:
                if self.use_groq:
                    system_prompt = """You are an expert educational assistant. Analyze this chapter from a video transcript and extract key educational content in JSON format."""
                    
                    user_prompt = f"""Analyze this chapter from an educational video and provide a JSON summary:

CHAPTER {chapter['chapter_id']} ({chapter['duration']:.1f}s duration):
{chapter['text'][:4000]}{"... [content truncated]" if len(chapter['text']) > 4000 else ""}

Provide a JSON response with this structure:
{{
  "chapter_title": "Descriptive title for this chapter",
  "summary": "1-2 paragraph summary of this chapter",
  "key_points": ["point1", "point2", "point3"],
  "definitions": {{"term": "definition"}},
  "examples": ["example1", "example2"],
  "questions": ["question1?", "question2?"],
  "common_mistakes": ["mistake1"],
  "visual_notes": ["visual element"]
}}

Focus on this chapter's specific content. Respond only with valid JSON."""
                    
                    generated_text = sync_chat_completion(
                        model=self.groq_model,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}
                        ],
                        temperature=0.3,
                        max_tokens=1000
                    )
                    
                    if generated_text:
                        # Try to parse JSON
                        json_match = re.search(r'\{.*\}', generated_text, re.DOTALL)
                        if json_match:
                            chapter_data = json.loads(json_match.group())
                            
                            # Create chapter summary
                            chapter_summary = {
                                "title": chapter_data.get("chapter_title", f"Chapter {chapter['chapter_id']}"),
                                "timestamp": f"{chapter['start_time']:.1f}s-{chapter['end_time']:.1f}s",
                                "summary": chapter_data.get("summary", "Chapter content summary"),
                                "key_concepts": chapter_data.get("key_points", [])[:3]
                            }
                            chapter_summaries.append(chapter_summary)
                            
                            # Aggregate content
                            all_key_points.extend(chapter_data.get("key_points", []))
                            all_definitions.update(chapter_data.get("definitions", {}))
                            all_examples.extend(chapter_data.get("examples", []))
                            all_questions.extend(chapter_data.get("questions", []))
                            all_mistakes.extend(chapter_data.get("common_mistakes", []))
                            all_visual_notes.extend(chapter_data.get("visual_notes", []))
                            
                            continue
                
                # Fallback for this chapter
                logger.warning(f"Using fallback for Chapter {chapter['chapter_id']}")
                fallback_summary = self._create_structured_summary_fallback(chapter['text'])
                
                chapter_summary = {
                    "title": f"Chapter {chapter['chapter_id']}",
                    "timestamp": f"{chapter['start_time']:.1f}s-{chapter['end_time']:.1f}s",
                    "summary": fallback_summary.get("summary", "Chapter content"),
                    "key_concepts": fallback_summary.get("key_points", [])[:3]
                }
                chapter_summaries.append(chapter_summary)
                
                # Aggregate fallback content
                all_key_points.extend(fallback_summary.get("key_points", []))
                all_definitions.update(fallback_summary.get("definitions", {}))
                all_examples.extend(fallback_summary.get("examples", []))
                all_questions.extend(fallback_summary.get("questions", []))
                
            except Exception as e:
                logger.error(f"Error processing Chapter {chapter['chapter_id']}: {e}")
                # Add minimal chapter info
                chapter_summaries.append({
                    "title": f"Chapter {chapter['chapter_id']}",
                    "timestamp": f"{chapter['start_time']:.1f}s-{chapter['end_time']:.1f}s",
                    "summary": "Chapter content processing failed",
                    "key_concepts": []
                })
        
        # Generate overall title from all chapters
        if all_key_points:
            concept_counts = Counter(all_key_points)
            top_concepts = [concept for concept, count in concept_counts.most_common(2)]
            if len(top_concepts) >= 2:
                title = f"{top_concepts[0]} and {top_concepts[1]}"
            else:
                title = f"{top_concepts[0]} - Educational Content"
        else:
            title = "Multi-Chapter Educational Content"
        
        # Create combined summary
        combined_summary = f"This educational content covers {len(chapters)} main chapters. " + \
                          " ".join([ch["summary"][:100] + "..." for ch in chapter_summaries[:3]])
        
        return {
            "title": title,
            "summary": combined_summary,
            "key_points": list(dict.fromkeys(all_key_points))[:10],  # Remove duplicates, limit to 10
            "definitions": dict(list(all_definitions.items())[:8]),  # Limit to 8 definitions
            "examples": list(dict.fromkeys(all_examples))[:8],  # Remove duplicates, limit to 8
            "questions": list(dict.fromkeys(all_questions))[:8],  # Remove duplicates, limit to 8
            "common_mistakes": list(dict.fromkeys(all_mistakes))[:5],  # Remove duplicates, limit to 5
            "visual_notes": list(dict.fromkeys(all_visual_notes))[:5],  # Remove duplicates, limit to 5
            "chapters": chapter_summaries
        }

# Global summarizer instance
_llama_summarizer = None

def get_llama_summarizer(enable_llama=True) -> LlamaEducationalSummarizer:
    """Get or create the global LLaMA summarizer instance"""
    global _llama_summarizer
    if _llama_summarizer is None:
        _llama_summarizer = LlamaEducationalSummarizer(enable_llama=enable_llama)
    return _llama_summarizer

def summarize_transcript(segments: List[Dict], use_chunks: bool = False) -> Dict:
    """
    Main function to summarize transcript segments using token-based processing
    
    Args:
        segments: List of transcript segments with text and timestamps
        use_chunks: If True, process each segment separately then combine (legacy approach)
                   If False, use new token-based whole transcript processing
        
    Returns:
        Dict: Structured educational summary
    """
    if use_chunks:
        logger.info(f"📝 Processing {len(segments)} transcript segments with chunk-based approach")
        summarizer = get_llama_summarizer(enable_llama=True)
        return summarizer.summarize_segments(segments)
    
    logger.info(f"📝 Processing {len(segments)} transcript segments with token-based approach")
    
    if not segments:
        logger.warning("No segments provided")
        return _create_empty_summary()
    
    # Step 1: Combine all segments into full transcript
    full_transcript = ' '.join(segment.get('text', '') for segment in segments)
    total_tokens = count_tokens(full_transcript)
    
    logger.info(f"📊 Full transcript: {len(full_transcript)} characters, ~{total_tokens} tokens")
    
    # Step 2: Check if we can process the whole transcript or need to split
    if total_tokens <= 8000:
        logger.info("✅ Transcript fits in token limit, processing as single unit")
        # Process the whole transcript at once
        summarizer = get_llama_summarizer(enable_llama=True)
        summary_data = summarizer.summarize_full_transcript(full_transcript, segments)
    else:
        logger.info(f"📚 Transcript exceeds 8000 tokens ({total_tokens}), splitting into chapters")
        # Split into chapters and process each
        chapters = split_transcript_into_chapters(segments, max_tokens=8000)
        summarizer = get_llama_summarizer(enable_llama=True)
        summary_data = summarizer.summarize_chapters(chapters, segments)
    
    # Step 3: Add comprehensive metadata
    total_duration = sum(float(segment.get('end', 0)) - float(segment.get('start', 0)) 
                        for segment in segments if segment.get('start') and segment.get('end'))
    
    summary_data.update({
        "transcript_length": len(full_transcript),
        "segment_count": len(segments),
        "total_duration": total_duration,
        "total_tokens": total_tokens,
        "processing_approach": "single_transcript" if total_tokens <= 8000 else "chapter_based"
    })
    
    # Determine processing model
    if summarizer.use_fallback:
        processing_model = "structured-text-analysis"
    elif summarizer.use_groq:
        processing_model = "llama-groq-token-based"
    else:
        processing_model = "unknown"
    
    summary_data["processing_model"] = processing_model
    
    logger.info("🎯 Token-based educational summary completed successfully!")
    return summary_data

def summarize_transcript_chunks(segments: List[Dict]) -> Dict:
    """
    Convenience function to summarize transcript using chunk-based processing
    
    Args:
        segments: List of transcript segments with text and timestamps
        
    Returns:
        Dict: Structured educational summary
    """
    return summarize_transcript(segments, use_chunks=True)

def _create_empty_summary() -> Dict:
    """Create empty summary structure for edge cases"""
    return {
        "title": "No Content",
        "summary": "No transcript content was available for summarization.",
        "key_points": [],
        "definitions": [],
        "examples": [],
        "questions": [],
        "common_mistakes": [],
        "visual_notes": [],
        "chapters": [],
        "sections_info": []
    }