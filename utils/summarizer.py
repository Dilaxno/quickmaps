"""
Educational Summarizer - Creates comprehensive study notes from video transcripts
Uses Llama 3.1 8b instant model via Groq API for detailed educational content generation
"""

import json
import logging
import re
from datetime import datetime
from typing import Dict, List, Optional
from .groq_client import sync_chat_completion

logger = logging.getLogger(__name__)

def count_tokens(text: str) -> int:
    """
    Estimate token count for text (rough approximation: 1 token ≈ 4 characters)
    """
    return len(text) // 4

class EducationalSummarizer:
    """
    Advanced educational summarizer that creates comprehensive study notes
    from video transcripts using Llama 3.1 8b instant model
    """
    
    def __init__(self):
        """Initialize the educational summarizer"""
        self.groq_model = "llama-3.1-8b-instant"  # 131k context window
        self.max_tokens = 4000  # Conservative limit for all models
        self.temperature = 0.7  # Balanced for comprehensive content generation
        self.max_input_tokens = 3000  # Conservative limit to account for prompt + transcript tokens
        
    def summarize(self, segments: List[Dict]) -> Dict:
        """
        Main entry point for creating educational summary from transcript segments
        
        Args:
            segments: List of transcript segments with text and timestamps
            
        Returns:
            Dict: Comprehensive educational summary
        """
        if not segments:
            logger.warning("No segments provided for summarization")
            return self._create_empty_summary()
        
        # Combine all transcript text
        full_transcript = ' '.join([segment.get('text', '') for segment in segments])
        total_tokens = count_tokens(full_transcript)
        
        logger.info(f"📊 Processing transcript: {total_tokens:,} tokens, {len(segments)} segments")
        
        # Estimate total tokens including prompt (prompt is ~2000 tokens)
        estimated_total_tokens = total_tokens + 2000
        
        # Check if we need to chunk due to rate limits or context window
        if estimated_total_tokens > 5500:  # Stay well under 6000 TPM limit
            logger.info(f"🔄 Content too large ({estimated_total_tokens:,} estimated tokens), chunking into smaller parts")
            return self._process_chunked_transcript(full_transcript, total_tokens)
        else:
            logger.info(f"🔄 Processing complete transcript ({estimated_total_tokens:,} estimated tokens)")
            return self._generate_comprehensive_notes(full_transcript)
    
    def _process_chunked_transcript(self, transcript: str, total_tokens: int) -> Dict:
        """
        Process large transcripts by chunking them into smaller parts
        
        Args:
            transcript: Full transcript text
            total_tokens: Total token count
            
        Returns:
            Dict: Combined educational summary from all chunks
        """
        # Split transcript into chunks that fit within rate limits
        chunk_size = 2000  # Conservative size - prompt is ~2000 tokens, so total ~4000 per request
        words = transcript.split()
        chunks = []
        
        current_chunk = []
        current_tokens = 0
        
        for word in words:
            word_tokens = count_tokens(word)
            if current_tokens + word_tokens > chunk_size and current_chunk:
                chunks.append(' '.join(current_chunk))
                current_chunk = [word]
                current_tokens = word_tokens
            else:
                current_chunk.append(word)
                current_tokens += word_tokens
        
        if current_chunk:
            chunks.append(' '.join(current_chunk))
        
        logger.info(f"📝 Split transcript into {len(chunks)} chunks")
        
        # Process each chunk and combine results
        all_summaries = []
        for i, chunk in enumerate(chunks):
            logger.info(f"🔄 Processing chunk {i+1}/{len(chunks)}")
            chunk_summary = self._generate_comprehensive_notes(chunk, chunk_number=i+1, total_chunks=len(chunks))
            if chunk_summary and chunk_summary.get('success'):
                all_summaries.append(chunk_summary)
        
        # Combine all chunk summaries into final comprehensive notes
        return self._combine_chunk_summaries(all_summaries)
    
    def _combine_chunk_summaries(self, summaries: List[Dict]) -> Dict:
        """
        Combine multiple chunk summaries into a comprehensive final summary
        
        Args:
            summaries: List of summary dictionaries from each chunk
            
        Returns:
            Dict: Combined comprehensive educational summary
        """
        if not summaries:
            logger.warning("No valid summaries to combine")
            return self._create_fallback_summary("No content could be processed")
        
        # Combine all the content from chunks
        combined_key_concepts = []
        combined_detailed_notes = []
        combined_examples = []
        combined_questions = []
        
        for summary in summaries:
            if summary.get('educational_content'):
                content = summary['educational_content']
                combined_key_concepts.extend(content.get('key_concepts', []))
                combined_detailed_notes.extend(content.get('detailed_notes', []))
                combined_examples.extend(content.get('examples_and_applications', []))
                combined_questions.extend(content.get('study_questions', []))
        
        # Create final combined summary
        return {
            "success": True,
            "processing_method": "chunked_processing",
            "total_chunks": len(summaries),
            "educational_content": {
                "title": "Comprehensive Educational Notes",
                "overview": f"Educational notes compiled from {len(summaries)} content sections",
                "key_concepts": combined_key_concepts[:20],  # Limit to top 20
                "detailed_notes": combined_detailed_notes,
                "examples_and_applications": combined_examples,
                "study_questions": combined_questions[:15],  # Limit to 15 questions
                "learning_objectives": [
                    "Understand the main concepts presented in the content",
                    "Apply the knowledge through practical examples",
                    "Analyze the relationships between different topics",
                    "Synthesize information for comprehensive understanding"
                ]
            },
            "metadata": {
                "processing_time": datetime.now().isoformat(),
                "content_type": "educational_notes",
                "source": "video_transcript",
                "processing_method": "ai_chunked_analysis"
            }
        }

    def _generate_comprehensive_notes(self, transcript: str, chunk_number: int = None, total_chunks: int = None) -> Dict:
        """
        Generate comprehensive educational notes using Llama 3.1 8b instant
        
        Args:
            transcript: Complete transcript text
            
        Returns:
            Dict: Comprehensive educational notes
        """
        try:
            logger.info("🧠 Generating comprehensive educational notes with Llama 3.1 8b instant...")
            
            prompt = self._create_educational_prompt(transcript, chunk_number, total_chunks)
            
            response = sync_chat_completion(
                model=self.groq_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.temperature,
                max_tokens=self.max_tokens
            )
            
            if response:
                return self._parse_response(response)
            else:
                logger.warning("No response from Groq model, using fallback")
                return self._create_fallback_summary(transcript)
                
        except Exception as e:
            logger.error(f"Error generating comprehensive notes: {e}")
            return self._create_fallback_summary(transcript)
    
    def _create_educational_prompt(self, transcript: str, chunk_number: int = None, total_chunks: int = None) -> str:
        """
        Create a comprehensive educational prompt for generating detailed study notes
        
        Args:
            transcript: Complete transcript text
            
        Returns:
            str: Detailed prompt for educational content generation
        """
        chunk_context = ""
        if chunk_number and total_chunks:
            chunk_context = f"""
CHUNKED PROCESSING CONTEXT:
- This is chunk {chunk_number} of {total_chunks} total chunks
- Focus on the content in this specific chunk while maintaining educational quality
- This chunk will be combined with others to form complete educational notes
"""

        return f"""You are an expert educational content creator, learning specialist, and academic researcher with advanced knowledge in pedagogy, cognitive science, and instructional design. Your task is to create COMPREHENSIVE, DETAILED study notes from this video transcript content that will serve as an educational resource.

{chunk_context}

CRITICAL REQUIREMENTS FOR EDUCATIONAL NOTES:
- Generate DETAILED explanations for every concept mentioned
- Explain technical terms clearly and thoroughly
- Provide multiple levels of explanation with concrete examples
- Include practical applications and real-world connections
- Create high-quality educational materials with academic rigor
- Cover the transcript content systematically
- Generate comprehensive study notes within the response limit

TRANSCRIPT CONTENT TO ANALYZE:
{transcript}

Please provide an EXTREMELY DETAILED JSON response with this ULTRA-COMPREHENSIVE structure:

{{
  "title": "Clear, descriptive title that captures the main educational topic",
  "subtitle": "Supporting subtitle that provides additional context and scope",
  "summary": "Comprehensive 4-5 paragraph summary that explains the main concepts, their interconnections, practical applications, theoretical foundations, and broader significance in the field. This should be detailed enough to serve as a standalone overview.",
  "learning_objectives": [
    "By the end of studying this content, learners will be able to identify, explain, and apply the fundamental concepts with deep understanding",
    "Students will demonstrate mastery of technical terminology and be able to use it accurately in context",
    "Learners will analyze complex relationships between different concepts and synthesize knowledge across topics",
    "Students will evaluate different approaches and methodologies with critical thinking skills",
    "Learners will create original applications and solutions using the knowledge gained",
    "Students will connect new knowledge to existing understanding and real-world scenarios"
  ],
  "key_points": [
    "First critical concept with detailed explanation of what it is, why it matters, how it works, and its practical applications",
    "Second essential point with comprehensive analysis including background context, current applications, and future implications",
    "Third fundamental concept with thorough explanation of underlying principles, methodologies, and real-world relevance",
    "Fourth important idea with detailed breakdown of components, processes, and practical considerations",
    "Fifth crucial understanding with extensive analysis of benefits, limitations, and best practices",
    "Continue with detailed explanations for ALL major concepts mentioned in the transcript..."
  ],
  "definitions": [
    {{
      "term": "Technical Term 1",
      "definition": "Comprehensive definition that explains the concept thoroughly",
      "etymology": "Origin and development of the term",
      "context": "When and where this term is used in the field",
      "examples": ["Concrete example 1", "Practical example 2", "Real-world application"],
      "related_terms": ["Connected concept 1", "Related terminology"],
      "beginner_explanation": "Simple explanation for newcomers to the field",
      "advanced_explanation": "Detailed technical explanation for experts",
      "common_misconceptions": "What people often get wrong about this concept",
      "practical_applications": "How this is used in real-world scenarios"
    }}
  ],
  "detailed_examples": [
    {{
      "title": "Comprehensive Example: [Descriptive Title]",
      "description": "Detailed description of the example and its relevance",
      "step_by_step_breakdown": "Thorough analysis of each component or step involved",
      "real_world_context": "How this example applies in professional or academic settings",
      "learning_value": "What students gain from understanding this example",
      "variations": "Different ways this concept can be applied or modified",
      "common_mistakes": "What to avoid when applying this concept",
      "expert_insights": "Professional perspectives and advanced considerations"
    }}
  ],
  "comprehensive_explanations": [
    {{
      "concept": "Major Concept Name",
      "basic_explanation": "Simple explanation suitable for beginners",
      "intermediate_explanation": "More detailed explanation with technical aspects",
      "advanced_explanation": "Comprehensive analysis with expert-level insights",
      "theoretical_foundation": "Academic and research basis for this concept",
      "practical_applications": "How this is used in real-world scenarios",
      "case_studies": "Specific examples of successful implementation",
      "common_challenges": "Typical difficulties and how to overcome them",
      "best_practices": "Recommended approaches and methodologies",
      "future_trends": "How this concept is evolving and future directions"
    }}
  ],
  "study_guide": [
    {{
      "topic": "Study Topic 1",
      "key_questions": ["What is the fundamental principle?", "How does it work?", "Why is it important?"],
      "study_methods": "Recommended approaches for mastering this topic",
      "practice_exercises": "Suggested activities to reinforce learning",
      "assessment_criteria": "How to evaluate understanding of this topic",
      "common_difficulties": "Where students typically struggle",
      "mastery_indicators": "Signs that the concept has been fully understood"
    }}
  ],
  "research_connections": [
    {{
      "research_area": "Related Research Field",
      "key_findings": "Important research discoveries relevant to this topic",
      "methodologies": "Research methods used to study this concept",
      "current_debates": "Ongoing discussions and controversies in the field",
      "future_research": "Promising directions for further investigation",
      "practical_implications": "How research findings apply to real-world situations"
    }}
  ],
  "interactive_elements": [
    {{
      "element_type": "Deep Dive Analysis",
      "title": "Advanced Topic Exploration",
      "content": "Detailed analysis that can be expanded for deeper understanding",
      "discussion_points": ["Point for further exploration", "Question for critical thinking"],
      "additional_resources": "Suggestions for further learning and research"
    }}
  ]
}}

MANDATORY REQUIREMENTS:
- Generate AT LEAST 50+ comprehensive key points (not just basic bullet points)
- Create AT LEAST 30+ detailed definitions with full explanations
- Provide AT LEAST 25+ comprehensive examples with step-by-step analysis
- Include multiple levels of explanation for every concept
- Explain every technical term thoroughly
- Cover the ENTIRE transcript content systematically
- Generate maximum educational value within the token limit
- Ensure content is suitable for both beginners and advanced learners
- Provide research-grade academic rigor

CRITICAL: You MUST respond with ONLY valid JSON. No explanations, no markdown, no additional text.
Start your response with {{ and end with }}. 
RESPOND WITH COMPREHENSIVE, DETAILED JSON THAT MAXIMIZES EDUCATIONAL VALUE AND COVERS EVERY CONCEPT IN THE TRANSCRIPT."""

    def _parse_response(self, response_text: str) -> Dict:
        """
        Parse the model response into structured educational data
        
        Args:
            response_text: Raw response from the model
            
        Returns:
            Dict: Parsed educational summary
        """
        try:
            logger.info(f"🔍 Raw response preview: {response_text[:200]}...")
            
            # Remove markdown code blocks if present
            cleaned_text = re.sub(r'```(?:json)?\s*', '', response_text)
            cleaned_text = re.sub(r'```\s*$', '', cleaned_text)
            
            # Extract JSON from the response
            json_match = re.search(r'\{[\s\S]*\}', cleaned_text)
            if json_match:
                json_str = json_match.group()
                logger.info(f"🔍 Extracted JSON preview: {json_str[:200]}...")
                
                # Clean up common JSON issues
                json_str = self._clean_json_string(json_str)
                
                try:
                    parsed_data = json.loads(json_str)
                    
                    # Transform to expected structure
                    if isinstance(parsed_data, dict):
                        logger.info("✅ Successfully parsed JSON response")
                        return self._transform_to_educational_structure(parsed_data)
                        
                except json.JSONDecodeError as json_error:
                    logger.warning(f"JSON parsing failed: {json_error}")
                    logger.info(f"🔍 Failed JSON string: {json_str[:500]}...")
                    return self._extract_json_aggressively(response_text)
            
            logger.warning("No valid JSON found in response, attempting manual parsing")
            logger.info(f"🔍 Full response for debugging: {response_text}")
            return self._manual_parse_response(response_text)
            
        except Exception as e:
            logger.error(f"Failed to parse response: {e}")
            return self._create_empty_summary()
    
    def _transform_to_educational_structure(self, parsed_data: Dict) -> Dict:
        """
        Transform parsed JSON to the expected educational structure
        
        Args:
            parsed_data: Raw parsed JSON data
            
        Returns:
            Dict: Properly structured educational content
        """
        try:
            # Create the expected structure with flexible field mapping
            educational_content = {
                "title": parsed_data.get("title", "Educational Content"),
                "subtitle": parsed_data.get("subtitle", "Study Notes"),
                "overview": parsed_data.get("summary", "Educational content analysis"),
                "learning_objectives": parsed_data.get("learning_objectives", []),
                "key_concepts": self._extract_key_concepts(parsed_data),
                "detailed_notes": self._extract_detailed_notes(parsed_data),
                "examples_and_applications": self._extract_examples(parsed_data),
                "study_questions": []
            }
            
            # Extract study questions from study_guide if available
            if parsed_data.get("study_guide"):
                for guide in parsed_data["study_guide"]:
                    if isinstance(guide, dict) and guide.get("key_questions"):
                        educational_content["study_questions"].extend(guide["key_questions"])
            
            # Add some default study questions if none found
            if not educational_content["study_questions"]:
                educational_content["study_questions"] = [
                    "What are the main concepts discussed?",
                    "How do these ideas connect to each other?",
                    "What are the practical applications?",
                    "How can this knowledge be applied in real situations?"
                ]
            
            return {
                "success": True,
                "processing_method": "ai_generated",
                "educational_content": educational_content,
                "metadata": {
                    "processing_time": datetime.now().isoformat(),
                    "content_type": "educational_notes",
                    "source": "video_transcript",
                    "processing_method": "groq_llama_analysis"
                }
            }
            
        except Exception as e:
            logger.error(f"Structure transformation failed: {e}")
            return self._create_fallback_summary("")
    
    def _extract_key_concepts(self, parsed_data: Dict) -> List:
        """Extract key concepts from various possible field names"""
        possible_fields = [
            "key_points", "key_concepts", "main_points", 
            "important_points", "concepts", "fundamentals"
        ]
        
        for field in possible_fields:
            if field in parsed_data and parsed_data[field]:
                concepts = parsed_data[field]
                if isinstance(concepts, list):
                    formatted_concepts = [self._format_concept(c) for c in concepts[:30]]  # Limit to 30
                    return formatted_concepts
                elif isinstance(concepts, str):
                    return [{"point": concepts, "explanation": "", "practical_application": ""}]
        return []
    
    def _extract_detailed_notes(self, parsed_data: Dict) -> List:
        """Extract detailed notes from various possible field names"""
        possible_fields = [
            "definitions", "detailed_notes", "explanations", 
            "comprehensive_explanations", "notes", "details"
        ]
        
        for field in possible_fields:
            if field in parsed_data and parsed_data[field]:
                notes = parsed_data[field]
                if isinstance(notes, list):
                    formatted_notes = [self._format_note(n) for n in notes[:20]]  # Limit to 20
                    return formatted_notes
                elif isinstance(notes, str):
                    return [{"concept": "Key Concept", "definition": notes, "examples": []}]
        return []
    
    def _extract_examples(self, parsed_data: Dict) -> List:
        """Extract examples from various possible field names"""
        possible_fields = [
            "detailed_examples", "examples", "applications", 
            "practical_applications", "use_cases", "examples_and_applications"
        ]
        
        for field in possible_fields:
            if field in parsed_data and parsed_data[field]:
                examples = parsed_data[field]
                if isinstance(examples, list):
                    return [self._format_example(e) for e in examples[:15]]  # Limit to 15
                elif isinstance(examples, str):
                    return [{"title": "Practical Example", "description": examples, "application": ""}]
        
        return []
    
    def _format_concept(self, concept) -> Dict:
        """Format a concept into the expected structure"""
        if isinstance(concept, dict):
            return {
                "point": concept.get("point", concept.get("concept", "Key Concept")),
                "explanation": concept.get("explanation", concept.get("description", "")),
                "practical_application": concept.get("practical_application", concept.get("application", ""))
            }
        elif isinstance(concept, str):
            return {
                "point": concept,
                "explanation": "",
                "practical_application": ""
            }
        return {"point": str(concept), "explanation": "", "practical_application": ""}
    
    def _format_note(self, note) -> Dict:
        """Format a note into the expected structure"""
        if isinstance(note, dict):
            return {
                "concept": note.get("concept", note.get("term", "Concept")),
                "definition": note.get("definition", note.get("explanation", "")),
                "examples": note.get("examples", [])
            }
        elif isinstance(note, str):
            return {
                "concept": "Key Concept",
                "definition": note,
                "examples": []
            }
        return {"concept": str(note), "definition": "", "examples": []}
    
    def _format_example(self, example) -> Dict:
        """Format an example into the expected structure"""
        if isinstance(example, dict):
            return {
                "title": example.get("title", example.get("name", "Example")),
                "description": example.get("description", example.get("content", "")),
                "application": example.get("application", example.get("use_case", ""))
            }
        elif isinstance(example, str):
            return {
                "title": "Practical Example",
                "description": example,
                "application": ""
            }
        return {"title": str(example), "description": "", "application": ""}
    
    def _clean_json_string(self, json_str: str) -> str:
        """
        Clean common JSON formatting issues
        
        Args:
            json_str: Raw JSON string
            
        Returns:
            str: Cleaned JSON string
        """
        # Remove trailing commas before closing braces/brackets
        json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)
        
        # Remove any leading/trailing whitespace
        json_str = json_str.strip()
        
        return json_str
    
    def _extract_json_aggressively(self, response_text: str) -> Dict:
        """
        Aggressively attempt to extract JSON from malformed response
        
        Args:
            response_text: Raw response text
            
        Returns:
            Dict: Extracted data or fallback summary
        """
        try:
            # Try multiple JSON extraction patterns
            patterns = [
                r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}',
                r'\{[\s\S]*?\}(?=\s*$|\s*\n\s*[A-Z])',
                r'\{.*?\}',
            ]
            
            for pattern in patterns:
                matches = re.finditer(pattern, response_text, re.DOTALL)
                for match in matches:
                    try:
                        json_str = match.group()
                        json_str = self._clean_json_string(json_str)
                        parsed_data = json.loads(json_str)
                        
                        if isinstance(parsed_data, dict) and len(parsed_data) > 2:
                            logger.info("✅ Successfully extracted JSON aggressively")
                            return self._transform_to_educational_structure(parsed_data)
                    except:
                        continue
            
            logger.warning("Aggressive JSON extraction failed")
            return self._manual_parse_response(response_text)
            
        except Exception as e:
            logger.error(f"Aggressive extraction failed: {e}")
            return self._create_empty_summary()
    
    def _manual_parse_response(self, text: str) -> Dict:
        """
        Manually parse response when JSON parsing fails
        
        Args:
            text: Raw response text
            
        Returns:
            Dict: Manually parsed summary
        """
        logger.info("🔧 Attempting manual parsing of LLM response")
        
        try:
            # Extract title
            title_match = re.search(r'title["\']?\s*:\s*["\']([^"\']+)["\']', text, re.IGNORECASE)
            title = title_match.group(1) if title_match else "Educational Content Analysis"
            
            # Extract summary
            summary_match = re.search(r'summary["\']?\s*:\s*["\']([^"\']+)["\']', text, re.IGNORECASE)
            summary = summary_match.group(1) if summary_match else "Comprehensive educational content covering key concepts and practical applications."
            
            # Extract key points
            key_points = []
            key_point_patterns = [
                r'["\']([^"\']*(?:concept|principle|important|key|fundamental)[^"\']*)["\']',
                r'- ([^\n]+)',
                r'\d+\.\s*([^\n]+)'
            ]
            
            for pattern in key_point_patterns:
                matches = re.findall(pattern, text, re.IGNORECASE)
                key_points.extend(matches[:10])  # Limit to prevent duplicates
            
            # Remove duplicates and empty strings
            key_points = list(dict.fromkeys([kp.strip() for kp in key_points if kp.strip()]))[:20]
            
            return {
                "title": title,
                "subtitle": "Comprehensive Educational Analysis",
                "summary": summary,
                "learning_objectives": [
                    "Understand the fundamental concepts presented in the content",
                    "Apply knowledge to practical scenarios and real-world situations",
                    "Analyze relationships between different concepts and ideas",
                    "Evaluate the significance and implications of the material",
                    "Synthesize information to create new understanding"
                ],
                "key_points": key_points if key_points else [
                    "Comprehensive analysis of educational content",
                    "Detailed exploration of key concepts and principles",
                    "Practical applications and real-world relevance",
                    "Theoretical foundations and academic context",
                    "Critical thinking and analytical perspectives"
                ],
                "definitions": [],
                "detailed_examples": [],
                "comprehensive_explanations": [],
                "study_guide": [],
                "research_connections": [],
                "interactive_elements": []
            }
            
        except Exception as e:
            logger.error(f"Manual parsing failed: {e}")
            return self._create_empty_summary()
    
    def _create_fallback_summary(self, transcript: str) -> Dict:
        """
        Create a comprehensive fallback summary using text processing
        
        Args:
            transcript: Complete transcript text
            
        Returns:
            Dict: Fallback educational summary
        """
        logger.info("🔄 Creating comprehensive fallback summary")
        
        try:
            # Process the transcript text
            sentences = [s.strip() for s in transcript.split('.') if len(s.strip()) > 10]
            paragraphs = [p.strip() for p in transcript.split('\n\n') if len(p.strip()) > 20]
            word_count = len(transcript.split())
            
            # Generate comprehensive title and subtitle
            title = "Comprehensive Educational Content Analysis"
            subtitle = "Detailed Study Notes and Learning Materials"
            
            if sentences:
                first_sentence = sentences[0]
                if any(word in first_sentence.lower() for word in ['welcome', 'today', 'lesson', 'learn', 'course', 'introduction']):
                    title = first_sentence[:80] + "..." if len(first_sentence) > 80 else first_sentence
                    if len(sentences) > 1:
                        subtitle = sentences[1][:60] + "..." if len(sentences[1]) > 60 else sentences[1]
            
            # Create comprehensive summary
            summary_sentences = sentences[:25] if len(sentences) >= 25 else sentences
            summary_parts = []
            
            if len(summary_sentences) >= 5:
                summary_parts.append(f"This comprehensive educational content provides detailed analysis of {'. '.join(summary_sentences[:3])}.")
                summary_parts.append(f"Key theoretical foundations include {'. '.join(summary_sentences[3:6])}.")
                
            if len(summary_sentences) >= 10:
                summary_parts.append(f"Practical applications demonstrate {'. '.join(summary_sentences[6:9])}.")
                summary_parts.append(f"Advanced concepts explore {'. '.join(summary_sentences[9:12])}.")
                
            if len(summary_sentences) >= 15:
                summary_parts.append(f"The content synthesizes complex ideas through {'. '.join(summary_sentences[12:15])}.")
            
            summary = ' '.join(summary_parts) if summary_parts else '. '.join(summary_sentences[:10]) + '.'
            
            # Generate comprehensive key points
            key_points = []
            importance_keywords = ['important', 'key', 'main', 'essential', 'crucial', 'significant', 'fundamental', 'critical', 'vital', 'primary']
            
            for sentence in sentences[:50]:  # Process up to 50 sentences
                if len(sentence) > 25 and len(sentence) < 400:
                    if any(word in sentence.lower() for word in importance_keywords):
                        key_points.append(f"{sentence.strip()} - This concept is fundamental to understanding the broader educational context.")
            
            # Add additional comprehensive key points
            if len(sentences) > 10:
                key_points.extend([
                    f"Content analysis reveals {word_count:,} words covering comprehensive educational material across {len(paragraphs)} thematic sections",
                    f"The material demonstrates sophisticated instructional design with logical progression from foundational concepts to advanced applications",
                    f"Multiple learning modalities are supported through varied content presentation approaches and comprehensive explanations",
                    f"Advanced concepts are scaffolded through systematic introduction of prerequisite knowledge and progressive complexity",
                    f"Real-world applications and case studies provide concrete examples of abstract theoretical principles"
                ])
            
            # Generate comprehensive definitions
            definitions = []
            definition_patterns = [
                r'(\w+)\s+is\s+(.+)', r'(\w+)\s+means\s+(.+)', r'(\w+)\s+refers to\s+(.+)',
                r'(\w+)\s+can be defined as\s+(.+)', r'(\w+)\s+represents\s+(.+)', r'(\w+)\s+involves\s+(.+)'
            ]
            
            for sentence in sentences[:75]:  # Process up to 75 sentences
                for pattern in definition_patterns:
                    matches = re.finditer(pattern, sentence, re.IGNORECASE)
                    for match in matches:
                        term = match.group(1).strip()
                        definition = match.group(2).strip()
                        if len(term) < 30 and len(definition) < 400 and len(definition) > 10:
                            definitions.append({
                                "term": term,
                                "definition": definition,
                                "etymology": f"Term '{term}' has evolved through academic discourse and professional usage",
                                "context": f"This term is commonly used in educational and professional contexts when discussing {term.lower()}",
                                "examples": [f"Practical example of {term}", f"Real-world application of {term}"],
                                "related_terms": [f"Related concept to {term}", f"Connected terminology"],
                                "beginner_explanation": f"For newcomers: '{term}' can be understood as {definition[:100]}...",
                                "advanced_explanation": f"Expert perspective: '{term}' represents complex theoretical and practical implications in {definition[:80]}...",
                                "common_misconceptions": f"Students often misunderstand '{term}' by oversimplifying its complexity",
                                "practical_applications": f"In practice, '{term}' is applied through systematic approaches and methodological frameworks"
                            })
            
            # Generate comprehensive examples
            examples = []
            example_keywords = ['example', 'for instance', 'such as', 'like', 'including', 'namely', 'specifically', 'particularly']
            
            for sentence in sentences:  # Process ALL sentences
                if any(word in sentence.lower() for word in example_keywords):
                    if len(sentence) < 500 and len(sentence) > 20:
                        examples.append({
                            "title": f"Comprehensive Example: {sentence[:50]}...",
                            "description": sentence.strip(),
                            "step_by_step_breakdown": "This example demonstrates systematic application of theoretical concepts through practical implementation",
                            "real_world_context": "This scenario commonly occurs in professional and academic settings, providing relevant learning opportunities",
                            "learning_value": "Students gain practical understanding by connecting abstract concepts to concrete applications",
                            "variations": "This concept can be adapted and modified for different contexts and specific requirements",
                            "common_mistakes": "Learners should avoid oversimplifying the complexity and ensure thorough understanding of underlying principles",
                            "expert_insights": "Professionals recognize the strategic importance of this example in demonstrating key methodological approaches"
                        })
            
            return {
                "success": True,
                "processing_method": "fallback_processing",
                "educational_content": {
                    "title": title,
                    "subtitle": subtitle,
                    "overview": summary,
                    "learning_objectives": [
                        "By the end of studying this content, learners will demonstrate comprehensive understanding of all fundamental concepts",
                        "Students will master technical terminology and apply it accurately in various educational and professional contexts",
                        "Learners will analyze complex relationships between concepts and synthesize knowledge across multiple domains",
                        "Students will evaluate different approaches with critical thinking skills and evidence-based reasoning",
                        "Learners will create original applications and innovative solutions using acquired knowledge and skills",
                        "Students will connect new understanding to existing knowledge and real-world scenarios with practical relevance"
                    ],
                    "key_concepts": key_points[:50] if len(key_points) >= 50 else key_points,  # Up to 50 key points
                    "detailed_notes": definitions[:30] if len(definitions) >= 30 else definitions,  # Up to 30 definitions
                    "examples_and_applications": examples[:25] if len(examples) >= 25 else examples,  # Up to 25 examples
                    "study_questions": [
                        "What are the fundamental principles discussed in this content?",
                        "How do the main concepts interconnect and relate to each other?",
                        "What are the practical applications of these ideas?",
                        "How can this knowledge be applied in real-world scenarios?",
                        "What are the key takeaways for further learning?"
                    ]
                },
                "metadata": {
                    "processing_time": datetime.now().isoformat(),
                    "content_type": "educational_notes",
                    "source": "video_transcript",
                    "processing_method": "fallback_text_analysis",
                    "word_count": word_count,
                    "sentence_count": len(sentences)
                }
            }
            
        except Exception as e:
            logger.error(f"Fallback summary creation failed: {e}")
            return self._create_empty_summary()
    
    def _create_empty_summary(self) -> Dict:
        """
        Create an empty summary structure for error cases
        
        Returns:
            Dict: Basic empty summary structure
        """
        return {
            "success": True,
            "processing_method": "empty_fallback",
            "educational_content": {
                "title": "Educational Content",
                "subtitle": "Study Notes",
                "overview": "Educational content analysis and comprehensive study materials.",
                "learning_objectives": [
                    "Understand key concepts and principles",
                    "Apply knowledge to practical situations",
                    "Analyze relationships between ideas",
                    "Evaluate significance and implications",
                    "Synthesize information for deeper understanding"
                ],
                "key_concepts": [
                    "Comprehensive educational content analysis",
                    "Detailed exploration of key concepts",
                    "Practical applications and real-world relevance",
                    "Theoretical foundations and academic context",
                    "Critical thinking and analytical perspectives"
                ],
                "detailed_notes": [],
                "examples_and_applications": [],
                "study_questions": [
                    "What are the main topics covered?",
                    "How do the concepts relate to each other?",
                    "What are the practical applications?",
                    "How can this knowledge be applied?"
                ]
            },
            "metadata": {
                "processing_time": datetime.now().isoformat(),
                "content_type": "educational_notes",
                "source": "video_transcript",
                "processing_method": "empty_fallback"
            }
        }

# Main entry point function
def summarize_transcript(segments: List[Dict]) -> Dict:
    """
    Create comprehensive educational summary from transcript segments
    
    Args:
        segments: List of transcript segments with text and timestamps
        
    Returns:
        Dict: Comprehensive educational summary
    """
    summarizer = EducationalSummarizer()
    return summarizer.summarize(segments)

# Convenience function for getting summarizer instance
def get_educational_summarizer() -> EducationalSummarizer:
    """Get an instance of the educational summarizer"""
    return EducationalSummarizer()