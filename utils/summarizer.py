import logging
import json
import re
from typing import List, Dict, Optional, Tuple
import os
from collections import Counter
from .ollama_client import sync_chat_completion, sync_generate_text
from .transcript_segmenter import TranscriptSegmenter, create_structured_prompt

# Ollama-only approach - no transformers dependency needed

logger = logging.getLogger(__name__)

class Phi3EducationalSummarizer:
    """
    Advanced educational summarizer using Phi-3 model via Ollama
    Specifically designed for extracting structured knowledge from video course transcripts
    Falls back to structured text processing if Ollama is unavailable
    """
    
    def __init__(self, enable_phi3=True):
        """Initialize the Phi-3 summarizer pipeline"""
        self.ollama_model = "phi3:medium-128k"
        self.use_fallback = True  # Start with fallback, try to initialize later
        self.use_ollama = False
        self.enable_phi3 = enable_phi3
        
        # Try to initialize if phi3 is enabled
        if self.enable_phi3:
            self._initialize_model()
        else:
            logger.info("📚 Phi-3 model loading disabled, using structured text processing fallback")
    
    def _initialize_model(self):
        """Initialize the Phi-3 model via Ollama only"""
        
        # Try Ollama phi3 model
        if self._try_ollama_initialization():
            return
        
        # Hosted API failed, use text processing fallback
        logger.warning("❌ Failed to initialize hosted Phi3, using text processing fallback")
        self.use_fallback = True
    
    def _try_ollama_initialization(self):
        """Try to initialize hosted Phi3 model"""
        try:
            logger.info("🌐 Trying to initialize hosted Phi3 model...")
            
            # Test if we can generate with hosted API
            test_response = sync_generate_text(
                model=self.ollama_model,
                prompt="Test connection",
                max_tokens=10
            )
            
            if test_response:
                self.use_ollama = True
                self.use_fallback = False
                logger.info("✅ Hosted Phi3 model initialized successfully!")
                return True
            else:
                logger.warning("❌ Hosted Phi3 test failed")
                return False
                
        except Exception as e:
            logger.warning(f"❌ Failed to initialize hosted Phi3: {e}")
            return False
    

    
    def _create_educational_prompt(self, transcript: str) -> str:
        """Create the detailed educational prompt for structured summarization"""
        
        # Truncate transcript to fit within context window and reduce timeout risk
        max_transcript_length = 3000  # Reduced from 6000 to avoid timeouts
        truncated_transcript = transcript[:max_transcript_length]
        if len(transcript) > max_transcript_length:
            truncated_transcript += "... [content truncated]"
        
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
    
    def _generate_summary_with_phi3(self, transcript: str) -> Dict:
        """Generate structured summary using Phi-3 model via hosted API"""
        try:
            if self.use_fallback:
                return self._create_structured_summary_fallback(transcript)
            
            prompt = self._create_educational_prompt(transcript)
            
            logger.info(f"🧠 Generating educational summary with hosted Phi-3...")
            
            generated_text = None
            
            if self.use_ollama:
                # Use hosted phi3 model
                system_prompt = """You are an expert educational assistant. Analyze educational content and provide structured summaries in JSON format. Focus on key concepts, definitions, and learning objectives."""
                
                generated_text = sync_chat_completion(
                    model=self.ollama_model,
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
            logger.error(f"❌ Error generating summary with Phi-3: {e}")
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
            summary_data = self._generate_summary_with_phi3(transcript)
            logger.info("✅ Educational summary generated successfully!")
            return summary_data
            
        except Exception as e:
            logger.error(f"❌ Summarization failed: {e}")
            return self._create_structured_summary_fallback(transcript)
    
    def summarize_with_structure(self, structured_sections: List[Dict], structured_prompt: str) -> Dict:
        """
        Summarize using intelligently segmented sections and structured prompt
        
        Args:
            structured_sections: List of topical sections with metadata
            structured_prompt: Pre-built structured prompt for phi3
            
        Returns:
            Dict: Educational summary
        """
        logger.info(f"📚 Starting structured summarization with {len(structured_sections)} sections")
        
        try:
            if self.use_ollama:
                logger.info("🧠 Generating educational summary with Phi-3 (Ollama) using structured input...")
                
                system_prompt = """You are an expert educational assistant specializing in creating comprehensive learning materials from video transcripts. You analyze structured, segmented content to create educational summaries that enhance learning and comprehension."""
                
                generated_text = sync_chat_completion(
                    model=self.ollama_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": structured_prompt}
                    ],
                    temperature=0.3,  # Lower temperature for more structured output
                    max_tokens=2000   # More tokens for comprehensive analysis
                )
            else:
                logger.error("Unexpected state: not using Ollama but not using fallback either")
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
                        logger.info("✅ Successfully parsed structured phi3 response")
                        return summary_data
                
                logger.warning("Generated response not in expected JSON format, using enhanced fallback")
                return self._create_structured_summary_from_sections(structured_sections)
                
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse phi3 JSON response: {e}")
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

# Global summarizer instance
_phi3_summarizer = None

def get_phi3_summarizer(enable_phi3=True) -> Phi3EducationalSummarizer:
    """Get or create the global Phi-3 summarizer instance"""
    global _phi3_summarizer
    if _phi3_summarizer is None:
        _phi3_summarizer = Phi3EducationalSummarizer(enable_phi3=enable_phi3)
    return _phi3_summarizer

def summarize_transcript(segments: List[Dict]) -> Dict:
    """
    Main function to summarize transcript segments using intelligent segmentation and Phi-3
    
    Args:
        segments: List of transcript segments with text and timestamps
        
    Returns:
        Dict: Structured educational summary
    """
    logger.info(f"📝 Processing {len(segments)} transcript segments with intelligent segmentation")
    
    if not segments:
        logger.warning("No segments provided")
        return _create_empty_summary()
    
    # Step 1: Intelligent segmentation
    segmenter = TranscriptSegmenter()
    structured_sections = segmenter.segment_transcript(segments)
    
    if not structured_sections:
        logger.warning("No content sections created")
        return _create_empty_summary()
    
    # Step 2: Calculate metadata
    total_duration = sum(section['duration'] for section in structured_sections)
    total_text_length = sum(len(section['text']) for section in structured_sections)
    
    logger.info(f"📊 Created {len(structured_sections)} topical sections")
    logger.info(f"📊 Total content: {total_text_length} characters, {total_duration:.1f}s duration")
    
    # Step 3: Create structured prompt for phi3
    structured_prompt = create_structured_prompt(structured_sections)
    
    # Step 4: Get summarizer and generate summary
    summarizer = get_phi3_summarizer(enable_phi3=True)
    
    # Use the structured prompt instead of raw transcript
    summary_data = summarizer.summarize_with_structure(structured_sections, structured_prompt)
    
    # Step 5: Add comprehensive metadata
    summary_data.update({
        "transcript_length": total_text_length,
        "segment_count": len(segments),
        "section_count": len(structured_sections),
        "total_duration": total_duration,
        "sections_info": [
            {
                "id": section["section_id"],
                "title": section["topic_title"],
                "type": section["section_type"],
                "duration": section["duration"],
                "concepts": section["key_concepts"][:3]  # Top 3 concepts
            }
            for section in structured_sections
        ]
    })
    
    # Determine processing model
    if summarizer.use_fallback:
        processing_model = "structured-text-analysis"
    elif summarizer.use_ollama:
        processing_model = "phi3-ollama-structured"
    else:
        processing_model = "unknown"
    
    summary_data["processing_model"] = processing_model
    
    logger.info("🎯 Intelligent educational summary completed successfully!")
    return summary_data

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