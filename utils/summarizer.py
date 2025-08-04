import logging
import json
import re
from typing import List, Dict, Optional, Tuple
import os
from collections import Counter
from .groq_client import sync_chat_completion, sync_generate_text

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
            current_chapter['token_count'] = current_tokens
            current_chapter['duration'] = current_chapter['end_time'] - current_chapter['start_time']
            current_chapter['chapter_id'] = len(chapters) + 1
            chapters.append(current_chapter)
            
            # Start new chapter
            current_chapter = {
                'text': '',
                'start_time': None,
                'end_time': None,
                'segments': []
            }
            current_tokens = 0
        
        # Add segment to current chapter
        if current_chapter['start_time'] is None:
            current_chapter['start_time'] = segment.get('start', 0)
        current_chapter['end_time'] = segment.get('end', 0)
        current_chapter['text'] += ' ' + segment_text if current_chapter['text'] else segment_text
        current_chapter['segments'].append(segment)
        current_tokens += segment_tokens
    
    # Add final chapter if it has content
    if current_chapter['text']:
        current_chapter['token_count'] = current_tokens
        current_chapter['duration'] = current_chapter['end_time'] - current_chapter['start_time']
        current_chapter['chapter_id'] = len(chapters) + 1
        chapters.append(current_chapter)
    
    logger.info(f"📚 Split transcript into {len(chapters)} chapters:")
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
        self.use_fallback = True
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
            
            # Test simple completion
            test_response = sync_chat_completion(
                model=self.groq_model,
                messages=[{"role": "user", "content": "Say 'test successful'"}],
                temperature=0.1,
                max_tokens=10
            )
            
            if test_response and "test successful" in test_response.lower():
                logger.info("✅ Groq LLaMA model initialized successfully!")
                self.use_groq = True
                self.use_fallback = False
                return True
            else:
                logger.warning("⚠️ Groq model test failed")
                return False
                
        except Exception as e:
            logger.warning(f"❌ Groq initialization failed: {e}")
            return False

    def _create_educational_prompt(self, transcript: str, is_segment: bool = False, segment_info: str = "") -> str:
        """Create educational prompt for LLaMA model"""
        
        segment_context = ""
        if segment_info:
            segment_context = f"\n\nSegment Context: {segment_info}"
        
        return f"""You are an expert educational assistant specializing in creating comprehensive learning materials from video transcripts. Analyze this transcript and extract structured educational content.

TRANSCRIPT:
{transcript[:4000]}{"... [content continues]" if len(transcript) > 4000 else ""}
{segment_context}

Please provide a JSON response with this structure:
{{
  "title": "Clear, descriptive title for the content",
  "summary": "Comprehensive 2-3 paragraph summary highlighting the main educational concepts and their relationships",
  "key_points": [
    "Most important concept or takeaway",
    "Second key learning point", 
    "Third essential concept",
    "Fourth important idea",
    "Fifth key insight"
  ],
  "definitions": [
    {{"term": "Key Term 1", "definition": "Clear explanation of the term"}},
    {{"term": "Key Term 2", "definition": "Clear explanation of the term"}}
  ],
  "examples": [
    "Concrete example that illustrates the concepts",
    "Another practical example",
    "Third example if applicable"
  ],
  "questions": [
    "What is the main concept explained?",
    "How does this apply in practice?",
    "What are the key benefits or implications?"
  ],
  "common_mistakes": [
    "Common misunderstanding to avoid",
    "Frequent error in application"
  ],
  "visual_notes": [
    "Visual element or diagram mentioned",
    "Chart or graph reference"
  ],
  "important_facts": [
    "Key statistic or data point",
    "Important numerical information"
  ]
}}

Focus on educational value and learning outcomes. Extract the most important concepts that a student should understand. Respond only with valid JSON."""

    def _generate_summary_with_llama(self, transcript: str) -> Dict:
        """Generate educational summary using LLaMA model via Groq"""
        try:
            prompt = self._create_educational_prompt(transcript)
            
            generated_text = sync_chat_completion(
                model=self.groq_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=2000
            )
            
            if generated_text:
                return self._parse_response(generated_text)
            else:
                logger.warning("No response from Groq model, using fallback")
                return self._create_structured_summary_fallback(transcript)
                
        except Exception as e:
            logger.error(f"Error generating summary with LLaMA: {e}")
            return self._create_structured_summary_fallback(transcript)

    def _create_structured_summary_fallback(self, transcript: str) -> Dict:
        """Create structured summary using text processing fallback"""
        logger.info("📝 Creating structured summary using text processing fallback")
        
        # Clean and process the text
        text = transcript.strip()
        sentences = [s.strip() for s in text.split('.') if len(s.strip()) > 10]
        total_length = len(text)
        
        # Extract title from content
        title = "Educational Content Summary"
        if sentences:
            first_sentence = sentences[0][:50]
            if any(word in first_sentence.lower() for word in ['welcome', 'today', 'lesson', 'learn', 'course']):
                title = sentences[0][:80] + "..." if len(sentences[0]) > 80 else sentences[0]
        
        # Create summary (first few sentences)
        summary_sentences = sentences[:4] if len(sentences) >= 4 else sentences
        summary = '. '.join(summary_sentences) + '.'
        
        # Extract key points from various parts of the text
        key_points = []
        for sentence in sentences[:10]:
            if len(sentence) > 20 and len(sentence) < 150:
                if any(word in sentence.lower() for word in ['important', 'key', 'main', 'essential', 'crucial']):
                    key_points.append(sentence.strip())
        
        # Simple definition extraction
        definition_patterns = [r'(\w+)\s+is\s+(.+)', r'(\w+)\s+means\s+(.+)', r'(\w+)\s+refers to\s+(.+)']
        definitions = []
        for sentence in sentences[:15]:
            for pattern in definition_patterns:
                matches = re.finditer(pattern, sentence, re.IGNORECASE)
                for match in matches:
                    term = match.group(1).strip()
                    definition = match.group(2).strip()
                    if len(term) < 30 and len(definition) < 200:
                        definitions.append({"term": term, "definition": definition})
        
        # Extract examples
        examples = []
        for sentence in sentences:
            if any(word in sentence.lower() for word in ['example', 'for instance', 'such as', 'like']):
                if len(sentence) < 200:
                    examples.append(sentence.strip())
        
        # Generate questions
        questions = [
            "What are the main concepts discussed?",
            "How can this information be applied?",
            "What are the key takeaways?"
        ]
        
        # Common mistakes (generic)
        common_mistakes = []
        visual_notes = []
        important_facts = []
        
        # Basic chapters structure
        chapters = []
        if total_length > 500:
            chapters.append({
                "title": "Introduction",
                "summary": "Opening concepts and overview",
                "timestamp": "0:00-5:00"
            })
            chapters.append({
                "title": "Main Content", 
                "summary": "Core educational material",
                "timestamp": "5:00-15:00"
            })
            if total_length > 1500:
                chapters.append({
                    "title": "Advanced Topics",
                    "summary": "Detailed concepts and applications", 
                    "timestamp": "15:00-25:00"
                })
        
        # Convert to new dynamic content structure
        content_structure = []
        
        # Create main topics from key points and definitions
        if key_points:
            # Group key points into topics
            main_topic = {
                "main_topic": "Key Concepts",
                "subtopics": []
            }
            
            # Add key points as subtopics
            for i, point in enumerate(key_points[:4]):
                subtopic = {
                    "name": f"Concept {i+1}",
                    "details": [point],
                    "examples": [],
                    "key_points": [point]
                }
                main_topic["subtopics"].append(subtopic)
            
            content_structure.append(main_topic)
        
        # Add definitions as a separate topic if available
        if definitions:
            def_topic = {
                "main_topic": "Important Definitions",
                "subtopics": []
            }
            
            for definition in definitions[:3]:
                subtopic = {
                    "name": definition.get("term", "Term"),
                    "details": [definition.get("definition", "Definition")],
                    "examples": [],
                    "key_points": [f"Definition: {definition.get('definition', '')}"]
                }
                def_topic["subtopics"].append(subtopic)
            
            content_structure.append(def_topic)
        
        # Add examples as a topic if available
        if examples:
            example_topic = {
                "main_topic": "Examples and Applications",
                "subtopics": [{
                    "name": "Practical Examples",
                    "details": examples[:3],
                    "examples": examples[:3],
                    "key_points": ["Review practical applications"]
                }]
            }
            content_structure.append(example_topic)
        
        # If no structured content found, create a basic structure
        if not content_structure:
            content_structure = [{
                "main_topic": "Content Overview",
                "subtopics": [{
                    "name": "Main Points",
                    "details": sentences[:3] if sentences else ["Content analysis in progress"],
                    "examples": [],
                    "key_points": ["Review the main content"]
                }]
            }]
        
        return {
            "title": title,
            "summary": summary,
            "content_structure": content_structure
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
                    
                    # Validate the structure
                    if isinstance(parsed_data, dict) and 'title' in parsed_data:
                        # Convert old format to new dynamic structure if needed
                        if "content_structure" not in parsed_data:
                            parsed_data = self._convert_to_dynamic_structure(parsed_data)
                        
                        logger.info("✅ Successfully parsed JSON response from LLM")
                        return parsed_data
                        
                except json.JSONDecodeError as json_error:
                    logger.warning(f"JSON parsing failed: {json_error}")
                    # Try aggressive extraction
                    return self._extract_json_aggressively(response_text)
            
            logger.warning("No valid JSON found in response, attempting manual parsing")
            return self._manual_parse_response(response_text)
            
        except Exception as e:
            logger.error(f"Failed to parse response: {e}")
            return self._create_basic_summary_structure()
    
    def _clean_json_string(self, json_str: str) -> str:
        """Clean common JSON formatting issues"""
        # Remove trailing commas
        json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)
        
        # Fix unescaped quotes in strings (basic attempt)
        json_str = re.sub(r'(?<!\\)"(?=[^"]*"[^"]*:)', '\\"', json_str)
        
        return json_str
    
    def _extract_json_aggressively(self, response_text: str) -> Dict:
        """Try to extract JSON content even from malformed responses"""
        try:
            # Look for any content that might be JSON-like
            patterns = [
                r'\{[^{}]*"title"[^{}]*\}',
                r'\{[\s\S]*?"title"[\s\S]*?\}',
                r'\{.*?\}',
            ]
            
            for pattern in patterns:
                matches = re.finditer(pattern, response_text, re.DOTALL)
                for match in matches:
                    try:
                        potential_json = match.group()
                        potential_json = self._clean_json_string(potential_json)
                        parsed = json.loads(potential_json)
                        if isinstance(parsed, dict) and len(parsed) > 2:
                            logger.info("✅ Aggressively extracted JSON content")
                            # Convert to dynamic structure if needed
                            if "content_structure" not in parsed:
                                parsed = self._convert_to_dynamic_structure(parsed)
                            return parsed
                    except:
                        continue
            
            logger.warning("Aggressive JSON extraction failed")
            return self._manual_parse_response(response_text)
            
        except Exception as e:
            logger.error(f"Aggressive extraction failed: {e}")
            return self._create_basic_summary_structure()

    def _convert_to_dynamic_structure(self, old_data: Dict) -> Dict:
        """Convert old-style summary to new dynamic content structure"""
        content_structure = []
        
        # Create topics from key points
        if old_data.get("key_points"):
            key_topic = {
                "main_topic": "Key Concepts",
                "subtopics": []
            }
            
            for i, point in enumerate(old_data["key_points"][:4]):
                subtopic = {
                    "name": f"Concept {i+1}",
                    "details": [point],
                    "examples": [],
                    "key_points": [point]
                }
                key_topic["subtopics"].append(subtopic)
            content_structure.append(key_topic)
        
        # Add definitions topic
        if old_data.get("definitions"):
            def_topic = {
                "main_topic": "Important Definitions",
                "subtopics": []
            }
            
            definitions = old_data["definitions"]
            if isinstance(definitions, list):
                for definition in definitions[:3]:
                    if isinstance(definition, dict):
                        subtopic = {
                            "name": definition.get("term", "Term"),
                            "details": [definition.get("definition", "")],
                            "examples": [],
                            "key_points": [f"Definition of {definition.get('term', '')}"]
                        }
                        def_topic["subtopics"].append(subtopic)
            content_structure.append(def_topic)
        
        # Add examples topic
        if old_data.get("examples"):
            example_topic = {
                "main_topic": "Examples and Applications", 
                "subtopics": [{
                    "name": "Practical Examples",
                    "details": old_data["examples"][:3],
                    "examples": old_data["examples"][:3],
                    "key_points": ["Review practical applications"]
                }]
            }
            content_structure.append(example_topic)
        
        return {
            "title": old_data.get("title", "Educational Content"),
            "summary": old_data.get("summary", ""),
            "content_structure": content_structure
        }

    def _manual_parse_response(self, text: str) -> Dict:
        """Manually parse response when JSON parsing fails"""
        logger.info("🔧 Attempting manual parsing of LLM response")
        
        # Extract title
        title_match = re.search(r'["\']title["\']:\s*["\']([^"\']+)["\']', text, re.IGNORECASE)
        title = title_match.group(1) if title_match else "Educational Content"
        
        # Extract summary
        summary_match = re.search(r'["\']summary["\']:\s*["\']([^"\']+)["\']', text, re.IGNORECASE)
        summary = summary_match.group(1) if summary_match else "Content summary not available"
        
        # Try to extract key points
        key_points = []
        key_points_match = re.search(r'["\']key_points["\']:\s*\[(.*?)\]', text, re.DOTALL)
        if key_points_match:
            points_text = key_points_match.group(1)
            points = re.findall(r'["\']([^"\']+)["\']', points_text)
            key_points = points[:5]
        
        # Create basic dynamic structure
        content_structure = [{
            "main_topic": "Main Content",
            "subtopics": [{
                "name": "Key Points",
                "details": key_points[:3] if key_points else ["Content analysis in progress"],
                "examples": [],
                "key_points": key_points[:3] if key_points else []
            }]
        }]
        
        return {
            "title": title,
            "summary": summary,
            "content_structure": content_structure
        }
    
    def _create_basic_summary_structure(self) -> Dict:
        """Create basic summary structure when parsing fails"""
        return {
            "title": "Educational Content",
            "summary": "Content processing encountered an issue. Using basic structure.",
            "content_structure": [{
                "main_topic": "Content Overview",
                "subtopics": [{
                    "name": "Main Points",
                    "details": ["Content analysis in progress"],
                    "examples": [],
                    "key_points": ["Review content when available"]
                }]
            }]
        }

    def summarize(self, transcript: str) -> Dict:
        """Main entry point for summarization"""
        if not transcript or not transcript.strip():
            logger.warning("Empty transcript provided")
            return self._create_basic_summary_structure()
        
        logger.info(f"📚 Starting summarization of {len(transcript)} character transcript")
        
        if self.use_groq:
            return self._generate_summary_with_llama(transcript)
        else:
            return self._create_structured_summary_fallback(transcript)

    def summarize_segments(self, segments: List[Dict]) -> Dict:
        """Summarize from transcript segments"""
        if not segments:
            return self._create_basic_summary_structure()
        
        # Combine all segment text
        full_text = ' '.join([segment.get('text', '') for segment in segments])
        return self.summarize(full_text)

    def summarize_from_segments(self, segments: List[Dict]) -> Dict:
        """Enhanced segment-based summarization with token management"""
        if not segments:
            logger.warning("No segments provided for summarization")
            return self._create_basic_summary_structure()
        
        # Combine all text
        full_transcript = ' '.join([segment.get('text', '') for segment in segments])
        total_tokens = count_tokens(full_transcript)
        
        logger.info(f"📊 Processing transcript: {total_tokens} tokens, {len(segments)} segments")
        
        # If small enough, process as single unit
        if total_tokens <= 8000:
            logger.info("🔄 Processing as single unit (under 8000 tokens)")
            return self.summarize_full_transcript(full_transcript, segments)
        else:
            logger.info("📚 Processing in chapters (over 8000 tokens)")
            chapters = split_transcript_into_chapters(segments, max_tokens=8000)
            return self.summarize_chapters(chapters, segments)

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
                
                # Extract variables to avoid backslash in f-string
                transcript_excerpt = full_transcript[:6000]
                truncation_note = "... [content truncated]" if len(full_transcript) > 6000 else ""
                
                user_prompt = f"""
You are an expert in educational content analysis and knowledge structuring. Your task is to read the provided video transcript and produce a HIGH-QUALITY dynamic mind map representation that captures the actual flow of ideas and topics discussed in the video.
### OBJECTIVE:
Convert the transcript into a **hierarchical JSON mind map** that accurately reflects the main topics, subtopics, and supporting details in the same order as they appear in the video. Focus on clarity, relevance, and preserving the natural progression of concepts.
---
### INSTRUCTIONS FOR OUTPUT:
- Respond ONLY with **valid JSON** (no explanations, no extra text).
- Extract **3 to 6 main topics** based on the core structure of the video.
- Each main topic should have **2 to 4 subtopics**.
- For every subtopic:
    - `name`: short descriptive title
    - `details`: concise bullet points summarizing key details
    - `examples`: include real examples mentioned in the video (or empty array if none)
    - `key_points`: most important insights, tips, or facts
- Do NOT create generic categories (like "Introduction" or "Conclusion") unless explicitly present in the video.
- Maintain **natural flow** (order of discussion as in transcript).
- Write concise, meaningful text for all fields (avoid long paragraphs).
---
### OUTPUT JSON TEMPLATE:
{{
  "title": "Main subject of the video in 3-6 words",
  "content_structure": [
    {{
      "main_topic": "First major topic discussed",
      "subtopics": [
        {{
          "name": "Subtopic 1",
          "details": ["detail 1", "detail 2", "detail 3"],
          "examples": ["example if mentioned"],
          "key_points": ["important point 1", "important point 2"],
          "child_nodes": [
            {{
              "name": "Specific Aspect 1",
              "details": ["specific detail 1", "specific detail 2"],
              "examples": ["specific example"],
              "key_points": ["specific insight"]
            }},
            {{
              "name": "Specific Aspect 2",
              "details": ["another detail"],
              "examples": [],
              "key_points": ["another insight"]
            }}
          ]
        }},
        {{
          "name": "Subtopic 2", 
          "details": ["detail 1", "detail 2"],
          "examples": [],
          "key_points": ["important point"],
          "child_nodes": []
        }}
      ]
    }},
    {{
      "main_topic": "Second major topic discussed",
      "subtopics": [
        {{
          "name": "Subtopic A",
          "details": ["detail 1", "detail 2"],
          "examples": [],
          "key_points": ["important point"],
          "child_nodes": [
            {{
              "name": "Implementation Detail",
              "details": ["how to implement", "step by step"],
              "examples": ["practical example"],
              "key_points": ["key consideration"]
            }}
          ]
        }}
      ]
    }}
  ],
  "summary": "A concise 2-sentence summary of the entire video"
}}
---
### QUALITY REQUIREMENTS:
- Ensure **logical grouping** of topics and subtopics with natural hierarchy.
- Keep names short and specific (3–6 words max) at all levels.
- Write details and key points as **concise bullet phrases**, not paragraphs.
- Avoid redundancy between details and key_points across levels.
- Be precise and factual, based on transcript.
- **Child Nodes Guidelines**:
  - Only create child_nodes when a subtopic has multiple distinct aspects/components
  - Child nodes should represent specific techniques, methods, steps, or detailed breakdowns
  - If a subtopic is simple, leave child_nodes as empty array []
  - Aim for 1-4 child nodes per subtopic when they exist
  - Each child node should have meaningful details, examples, or key_points
---
### TRANSCRIPT TO ANALYZE:
{transcript_excerpt}{truncation_note}
Return ONLY the JSON result as per the template above.
"""
                
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
                    
                    # Validate required fields for new dynamic structure
                    required_fields = ['title', 'content_structure', 'summary']
                    if all(field in summary_data for field in required_fields):
                        # Validate content_structure format
                        if isinstance(summary_data['content_structure'], list) and len(summary_data['content_structure']) > 0:
                            logger.info("✅ Successfully parsed dynamic content structure response")
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
        all_content_structure = []
        
        # Process each chapter
        for chapter in chapters:
            logger.info(f"Processing Chapter {chapter['chapter_id']}: {chapter['token_count']} tokens")
            
            try:
                chapter_summary = self.summarize(chapter['text'])
                chapter_summaries.append(chapter_summary)
                
                # Collect content structure from each chapter
                if 'content_structure' in chapter_summary:
                    all_content_structure.extend(chapter_summary['content_structure'])
                    
            except Exception as e:
                logger.error(f"Failed to summarize chapter {chapter['chapter_id']}: {e}")
                continue
        
        if not chapter_summaries:
            logger.error("No chapters were successfully summarized")
            return self._create_basic_summary_structure()
        
        # Combine chapter summaries
        combined_title = chapter_summaries[0].get('title', 'Educational Content')
        combined_summary = ' '.join([cs.get('summary', '') for cs in chapter_summaries])
        
        # Limit content structure to avoid overwhelming
        limited_content_structure = all_content_structure[:6]  # Max 6 main topics
        
        return {
            "title": combined_title,
            "summary": combined_summary,
            "content_structure": limited_content_structure
        }

# Module-level convenience functions
def get_llama_summarizer(enable_llama=True) -> LlamaEducationalSummarizer:
    """Get an instance of the LLaMA summarizer"""
    return LlamaEducationalSummarizer(enable_llama=enable_llama)

def summarize_transcript(segments: List[Dict], use_chunks: bool = False) -> Dict:
    """
    Main entry point for transcript summarization
    
    Args:
        segments: List of transcript segments with text and timestamps
        use_chunks: If True, force chunk-based processing even for small transcripts
        
    Returns:
        Dict: Structured educational summary with processing metadata
    """
    if not segments:
        logger.warning("No segments provided for summarization")
        return _create_empty_summary()
    
    logger.info(f"🎯 Starting transcript summarization with {len(segments)} segments")
    
    # Initialize summarizer
    summarizer = get_llama_summarizer(enable_llama=True)
    
    try:
        if use_chunks:
            # Force chunk-based processing
            chapters = split_transcript_into_chapters(segments, max_tokens=6000)
            summary_data = summarizer.summarize_chapters(chapters, segments)
        else:
            # Use intelligent processing (single unit vs chapters)
            summary_data = summarizer.summarize_from_segments(segments)
        
    except Exception as e:
        logger.error(f"❌ Summarization failed: {e}")
        return _create_empty_summary()
    
    # Add processing metadata
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
        "content_structure": [{
            "main_topic": "No Content Available",
            "subtopics": [{
                "name": "Status",
                "details": ["No transcript content was provided"],
                "examples": [],
                "key_points": ["Please provide valid transcript content"]
            }]
        }]
    }