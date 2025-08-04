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
        """Create comprehensive educational prompt for LLaMA model"""
        
        segment_context = ""
        if segment_info:
            segment_context = f"\n\nSegment Context: {segment_info}"
        
        return f"""You are an expert educational assistant, learning specialist, and research mentor with advanced knowledge in pedagogy, cognitive science, instructional design, and deep academic analysis. Your task is to create ultra-comprehensive, multi-layered learning materials from video transcripts that provide detailed explanations for every concept, term, and idea mentioned. Students and researchers should be able to understand every single word and concept thoroughly through your explanations.

Each explanation should include sub-explanations, examples, and be designed to support interactive deep-dive learning where users can request even more detailed explanations of specific points.

Each explanation should include sub-explanations, examples, and be designed to support interactive deep-dive learning where users can request even more detailed explanations of specific points.

TRANSCRIPT:
{transcript[:4000]}{"... [content continues]" if len(transcript) > 4000 else ""}
{segment_context}

Please provide an extremely detailed JSON response with this ultra-comprehensive structure that explains every concept in depth with interactive elements with interactive elements:
{{
  "title": "Clear, descriptive title that captures the essence of the educational content",
  "subtitle": "Supporting subtitle that provides additional context or focus area",
  "summary": "Comprehensive 3-4 paragraph summary that not only highlights main concepts but also explains their interconnections, practical applications, and broader significance in the field",
  "learning_objectives": [
    "By the end of this content, learners will be able to...",
    "Students will understand the relationship between...",
    "Learners will demonstrate proficiency in...",
    "Students will analyze and evaluate...",
    "Learners will synthesize knowledge to create..."
  ],
  "key_points": [
    "Most critical concept with detailed explanation of why it matters",
    "Second essential learning point with context and implications", 
    "Third fundamental concept with real-world connections",
    "Fourth important idea with supporting evidence",
    "Fifth key insight with practical applications",
    "Sixth crucial understanding with interdisciplinary connections",
    "Seventh vital concept with problem-solving applications"
  ],
  "detailed_concepts": [
    {{
      "concept": "Primary Concept Name",
      "explanation": "In-depth explanation of the concept",
      "importance": "Why this concept is crucial to understand",
      "applications": ["Real-world application 1", "Practical use case 2"],
      "prerequisites": ["What students should know before learning this"],
      "connections": ["How this relates to other concepts in the field"]
    }}
  ],
  "word_by_word_analysis": [
    {{
      "phrase": "Exact phrase or sentence from transcript",
      "phrase_id": "unique_phrase_id_001",
      "phrase_id": "unique_phrase_id_001",
      "word_breakdown": [
        {{
          
          "word": "individual word",
          "word_id": "unique_word_id_001",
          "meaning": "detailed meaning in context",
          "technical_definition": "academic/technical definition",
          "why_important": "why this word matters in this context",
          "related_concepts": ["connected ideas"],
          "sub_explanations": [
            {{
              "aspect": "contextual usage",
              "explanation": "detailed explanation of how this word is used in this specific context",
              "examples": ["example 1 of usage", "example 2 of usage"],
              "clickable_id": "word_context_001"
            }},
            {{
              "aspect": "theoretical foundation",
              "sub_explanations": [
            {{
              "aspect": "contextual usage",
              "explanation": "detailed explanation of how this word is used in this specific context",
              "examples": ["example 1 of usage", "example 2 of usage"],
              "clickable_id": "word_context_001"
            }},
            {{
              "aspect": "theoretical foundation",
              "explanation": "the theoretical basis behind this word choice",
              "examples": ["theoretical example 1", "theoretical example 2"],
              "clickable_id": "word_theory_001"
            }}
          ],
          "interactive_prompts": [
            "Why is this word choice more precise than alternatives?",
            "How does this word connect to broader theoretical frameworks?",
            "What would happen if we used a different word here?"
          ]
        }}
      ],
      "phrase_explanation": "Comprehensive explanation of what the entire phrase means",
      "deeper_implications": "What this phrase reveals about broader concepts",
      "research_context": "How researchers in this field would interpret this phrase",
      "clickable_details": [
        {{
          "detail_id": "phrase_deep_001",
          "summary": "Click for deeper analysis of this phrase's theoretical implications",
          "prompt_for_ai": "Explain in detail why this phrase is theoretically significant and how it connects to broader academic frameworks"
        }}
      ]  "explanation": "the theoretical basis behind this word choice",
              "examples": ["theoretical example 1", "theoretical example 2"],
              "clickable_id": "word_theory_001"
            }}
          ],
          "interactive_prompts": [
            "Why is this word choice more precise than alternatives?",
            "How does this word connect to broader theoretical frameworks?",
            "What would happen if we used a different word here?"
          ]
        }}
      ],
      "phrase_explanation": "Comprehensive explanation of what the entire phrase means",
      "deeper_implications": "What this phrase reveals about broader concepts",
      "research_context": "How researchers in this field would interpret this phrase",
      "clickable_details": [
        {{
          "detail_id": "phrase_deep_001",
          "summary": "Click for deeper analysis of this phrase's theoretical implications",
          "prompt_for_ai": "Explain in detail why this phrase is theoretically significant and how it connects to broader academic frameworks"
        }}
      ]
    }}
  ],
  "concept_deep_dive": [
    {{
      "concept": "Major concept name",
      "concept_id": "concept_deep_001",
      "basic_explanation": "Simple explanation for beginners",
      "intermediate_explanation": "More detailed explanation with context",
      "advanced_explanation": "Complex explanation with nuances and edge cases",
      "research_level_explanation": "How experts and researchers understand this concept",
      "historical_context": "How this concept developed over time",
      "current_debates": "What researchers currently debate about this concept",
      "future_directions": "Where research is heading with this concept",
      "mathematical_foundations": "Mathematical or logical basis if applicable",
      "philosophical_implications": "Deeper philosophical questions this concept raises",
      "sub_explanations": [
        {{
          "aspect": "practical applications",
          "explanation": "How this concept is applied in real-world scenarios",
          "examples": ["practical example 1", "practical example 2"],
          "clickable_id": "concept_practical_001",
          "interactive_prompts": [
            "How would this concept apply in different industries?",
            "What are the limitations of this concept in practice?",
            "Can you provide more specific examples of implementation?"
          ]
        }},
        {{
          "aspect": "theoretical foundations",
          "explanation": "The underlying theoretical principles that support this concept",
          "examples": ["theoretical framework 1", "theoretical framework 2"],
          "clickable_id": "concept_theory_001",
          "interactive_prompts": [
            "What are the philosophical assumptions behind this concept?",
            "How does this theory compare to alternative approaches?",
            "What evidence supports this theoretical foundation?"
          ]
        }}
      ],
      "clickable_details": [
        {{
          "detail_id": "concept_expert_001",
          "summary": "Click for expert-level analysis of this concept's implications",
          "prompt_for_ai": "Provide an expert-level analysis of this concept including cutting-edge research, unresolved questions, and implications for future development in the field"
        }},
        {{
          "detail_id": "concept_compare_001",
          "summary": "Click for comparative analysis with related concepts",
          "prompt_for_ai": "Compare and contrast this concept with related concepts in the field, highlighting similarities, differences, and when to use each approach"
        }}
      ]
    }}
  ],
  "terminology_encyclopedia": [
    {{
      "term": "Technical term",
      "pronunciation": "How to pronounce it",
      "definition_levels": {{
        "elementary": "Explanation for elementary students",
        "high_school": "Explanation for high school students", 
        "undergraduate": "Explanation for college students",
        "graduate": "Explanation for graduate students",
        "expert": "How experts in the field define it"
      }},
      "etymology": "Origin and history of the term",
      "evolution": "How the meaning has changed over time",
      "field_specific_usage": "How different fields use this term differently",
      "common_misconceptions": "What people often get wrong about this term",
      "related_terminology": "Network of related terms and their relationships",
      "usage_examples": [
        {{"context": "academic paper", "example": "how it appears in research"}},
        {{"context": "practical application", "example": "how it's used in real world"}}
      ]
    }}
  ],
  "definitions": [
    {{"term": "Key Term 1", "definition": "Comprehensive definition with context", "etymology": "Origin or background of the term", "synonyms": ["Alternative terms"], "antonyms": ["Opposite concepts"], "detailed_explanation": "Multi-paragraph explanation covering all aspects", "expert_perspective": "How experts in the field view this term", "beginner_friendly": "Simple explanation for newcomers"}},
    {{"term": "Key Term 2", "definition": "Detailed explanation with examples", "usage_context": "When and how this term is typically used", "common_confusion": "What this term is often confused with", "precision_notes": "Exact boundaries and limitations of this term", "interdisciplinary_usage": "How other fields use this same term"}}
  ],
  "sentence_by_sentence_breakdown": [
    {{
      "sentence": "Complete sentence from transcript",
      "grammatical_analysis": "Subject, verb, object, and grammatical structure explanation",
      "content_analysis": "What information this sentence conveys",
      "implicit_assumptions": "What the sentence assumes the audience knows",
      "logical_structure": "How this sentence builds an argument or explanation",
      "technical_terms_used": ["List of technical terms and their meanings in context"],
      "connection_to_previous": "How this sentence connects to what came before",
      "connection_to_following": "How this sentence sets up what comes next",
      "alternative_phrasings": ["Different ways this could have been expressed"],
      "complexity_level": "Academic level required to fully understand this sentence"
    }}
  ],
  "examples": [
    {{
      "title": "Example 1 Title",
      "description": "Detailed example that illustrates key concepts",
      "step_by_step_breakdown": "Breaking down every component of this example",
      "why_this_example_works": "Detailed analysis of what makes this example effective",
      "what_would_happen_if": "Analysis of variations and alternative scenarios",
      "real_world_parallels": "Similar situations in actual professional/academic contexts",
      "beginner_explanation": "How to explain this example to someone new to the field",
      "expert_insights": "What experts would notice about this example that others might miss",
      "common_student_questions": "Questions students typically ask about this example",
      "analysis": "Why this example is effective and what it demonstrates",
      "variations": ["How this example could be modified or extended"],
      "deeper_implications": "What broader principles this example reveals"
    }},
    {{
      "title": "Example 2 Title", 
      "description": "Another comprehensive practical example",
      "contextual_background": "Background knowledge needed to fully appreciate this example",
      "detailed_walkthrough": "Step-by-step explanation of every aspect",
      "interdisciplinary_connections": "How this example relates to other fields",
      "historical_context": "How similar examples have been used historically",
      "modern_relevance": "Why this example matters in today's context",
      "real_world_context": "Where this example applies in real situations",
      "learning_value": "What specific learning outcomes this example supports"
    }}
  ],
  "case_studies": [
    {{
      "title": "Case Study Title",
      "scenario": "Detailed scenario description",
      "analysis_questions": ["What factors contributed to...?", "How could this have been handled differently?"],
      "key_lessons": ["Primary lesson learned", "Secondary insights"]
    }}
  ],
  "step_by_step_processes": [
    {{
      "process_name": "Name of the process or procedure",
      "steps": [
        {{"step": 1, "action": "First step description", "rationale": "Why this step is important", "common_errors": "What typically goes wrong here"}},
        {{"step": 2, "action": "Second step description", "tips": "Pro tips for success", "checkpoints": "How to verify this step is complete"}}
      ],
      "prerequisites": ["What's needed before starting"],
      "expected_outcomes": ["What should result from following this process"]
    }}
  ],
  "questions": [
    {{
      "category": "Comprehension",
      "questions": [
        "What is the fundamental principle behind...?",
        "How would you explain this concept to someone unfamiliar with the field?",
        "What are the key components of...?"
      ]
    }},
    {{
      "category": "Application", 
      "questions": [
        "How would you apply this concept in scenario X?",
        "What steps would you take to implement...?",
        "Given these constraints, how would you modify the approach?"
      ]
    }},
    {{
      "category": "Analysis",
      "questions": [
        "What are the strengths and weaknesses of this approach?",
        "How does this compare to alternative methods?",
        "What factors influence the effectiveness of...?"
      ]
    }},
    {{
      "category": "Synthesis",
      "questions": [
        "How could you combine these concepts to solve...?",
        "What new insights emerge when connecting these ideas?",
        "How might this evolve in the future?"
      ]
    }}
  ],
  "common_mistakes": [
    {{
      "mistake": "Specific common error or misunderstanding",
      "why_it_happens": "Psychological or conceptual reason for this mistake",
      "how_to_avoid": "Specific strategies to prevent this error",
      "correct_approach": "What should be done instead"
    }},
    {{
      "mistake": "Another frequent misconception",
      "consequences": "What problems this mistake can lead to",
      "warning_signs": "How to recognize when this mistake is being made",
      "remediation": "How to correct this mistake once it's identified"
    }}
  ],
  "visual_notes": [
    {{
      "type": "Diagram/Chart/Graph type",
      "description": "Detailed description of visual element",
      "key_features": ["Important aspects to notice"],
      "interpretation": "How to read and understand this visual",
      "creation_tips": "How students could create similar visuals"
    }}
  ],
  "important_facts": [
    {{
      "fact": "Key statistic or data point",
      "source": "Where this information comes from",
      "significance": "Why this fact is important",
      "context": "Background information that gives meaning to this fact",
      "implications": "What this fact suggests or predicts"
    }}
  ],
  "mnemonics_and_memory_aids": [
    {{
      "concept": "What this helps remember",
      "technique": "Specific mnemonic device or memory aid",
      "explanation": "How to use this memory technique effectively"
    }}
  ],
  "further_reading": [
    {{
      "category": "Foundational Knowledge",
      "suggestions": ["Recommended books, articles, or resources for deeper understanding"]
    }},
    {{
      "category": "Advanced Topics", 
      "suggestions": ["Resources for students ready to explore more complex aspects"]
    }},
    {{
      "category": "Practical Applications",
      "suggestions": ["Resources focused on real-world implementation"]
    }}
  ],
  "assessment_criteria": [
    {{
      "skill": "Specific skill or knowledge area",
      "beginner": "What beginner-level understanding looks like",
      "intermediate": "Characteristics of intermediate mastery",
      "advanced": "Indicators of advanced proficiency",
      "expert": "What expert-level performance demonstrates"
    }}
  ],
  "interdisciplinary_connections": [
    {{
      "field": "Related academic discipline or field",
      "connection": "How the concepts relate to this field",
      "examples": ["Specific examples of cross-disciplinary applications"],
      "benefits": "Why understanding these connections is valuable"
    }}
  ],
  "practical_exercises": [
    {{
      "title": "Exercise Name",
      "objective": "What this exercise aims to achieve",
      "instructions": "Step-by-step instructions for the exercise",
      "materials_needed": ["Required resources or tools"],
      "time_estimate": "Expected duration",
      "difficulty_level": "Beginner/Intermediate/Advanced",
      "assessment_rubric": "How to evaluate completion and quality"
    }}
  ],
  "reflection_prompts": [
    "How does this new knowledge change your understanding of...?",
    "What connections can you make between this content and your previous experiences?",
    "What questions do you still have after learning this material?",
    "How might you apply these concepts in your personal or professional life?",
    "What was most challenging about this content and why?",
    "What strategies helped you understand this material best?"
  ],
  "extension_activities": [
    {{
      "activity": "Name of extension activity",
      "description": "Detailed description of the activity",
      "learning_goals": ["What additional learning this activity promotes"],
      "resources_needed": ["Materials, tools, or access required"],
      "collaboration": "Whether this works better individually or in groups",
      "assessment": "How to evaluate the activity outcomes"
    }}
  ],
  "research_methodology_analysis": [
    {{
      "concept": "Research concept mentioned",
      "methodology_explanation": "How researchers study this concept",
      "data_collection_methods": "How data is gathered in this field",
      "analysis_techniques": "Statistical or analytical methods used",
      "limitations_and_challenges": "What makes this research difficult",
      "current_research_trends": "What researchers are focusing on now",
      "future_research_directions": "Where the field is heading"
    }}
  ],
  "cognitive_load_analysis": [
    {{
      "concept": "Complex concept from content",
      "intrinsic_load": "How inherently difficult this concept is",
      "extraneous_load": "What makes this concept harder to understand than necessary",
      "germane_load": "Mental effort needed to process and understand this concept",
      "scaffolding_suggestions": "How to break this down for easier understanding",
      "prerequisite_knowledge": "What students must know before tackling this concept",
      "common_cognitive_barriers": "Why students struggle with this concept"
    }}
  ],
  "expert_vs_novice_perspectives": [
    {{
      "concept": "Key concept",
      "novice_understanding": "How beginners typically understand this",
      "expert_understanding": "How experts understand this differently",
      "transition_pathway": "How understanding evolves from novice to expert",
      "common_misconceptions": "Where novices go wrong",
      "expert_shortcuts": "Mental models experts use",
      "teaching_implications": "How to bridge novice-expert gap"
    }}
  ],
  "linguistic_analysis": [
    {{
      "phrase": "Important phrase from transcript",
      "register_analysis": "Formal/informal language level",
      "discourse_markers": "Words that signal relationships between ideas",
      "modal_verbs_analysis": "Use of 'can', 'should', 'must' and their implications",
      "passive_vs_active_voice": "Why certain voice choices were made",
      "nominalization_analysis": "Complex noun phrases and their simpler equivalents",
      "cohesion_devices": "How sentences connect to each other",
      "pragmatic_implications": "What the speaker implies beyond literal meaning"
    }}
  ],
  "metacognitive_guidance": [
    {{
      "learning_stage": "Stage of learning (introduction, development, mastery)",
      "self_monitoring_questions": ["Questions students should ask themselves"],
      "comprehension_checkpoints": ["How to verify understanding at this stage"],
      "common_confusion_points": ["Where students typically get lost"],
      "recovery_strategies": ["What to do when understanding breaks down"],
      "connection_prompts": ["How to link this to existing knowledge"],
      "application_readiness": ["How to know when ready to apply concepts"]
    }}
  ]
}}

CRITICAL INSTRUCTION: Focus on creating ultra-comprehensive, research-grade educational materials that explain every single word, phrase, and concept in exhaustive detail. Provide multiple levels of explanation from elementary to expert level. Students and researchers should be able to understand every nuance, implication, and connection. Consider different learning styles, cognitive loads, and provide scaffolding for complex concepts. Ensure content is academically rigorous while providing pathways for all levels of learners. Every technical term should be explained as if the reader has never encountered it before, while also providing expert-level insights. Respond only with valid JSON."""

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
        """Create comprehensive structured summary using advanced text processing fallback"""
        logger.info("📝 Creating comprehensive structured summary using text processing fallback")
        
        # Clean and process the text
        text = transcript.strip()
        sentences = [s.strip() for s in text.split('.') if len(s.strip()) > 10]
        paragraphs = [p.strip() for p in text.split('\n\n') if len(p.strip()) > 20]
        total_length = len(text)
        word_count = len(text.split())
        
        # Enhanced title extraction
        title = "Comprehensive Educational Content Analysis"
        subtitle = "Detailed Learning Materials and Study Guide"
        
        if sentences:
            first_sentence = sentences[0][:50]
            if any(word in first_sentence.lower() for word in ['welcome', 'today', 'lesson', 'learn', 'course', 'introduction', 'chapter']):
                title = sentences[0][:100] + "..." if len(sentences[0]) > 100 else sentences[0]
                if len(sentences) > 1:
                    subtitle = sentences[1][:80] + "..." if len(sentences[1]) > 80 else sentences[1]
        
        # Create comprehensive summary (multiple paragraphs)
        summary_sentences = sentences[:8] if len(sentences) >= 8 else sentences
        summary_parts = []
        
        # Introduction paragraph
        if len(summary_sentences) >= 2:
            summary_parts.append(f"This educational content covers {'. '.join(summary_sentences[:2])}.")
        
        # Main concepts paragraph
        if len(summary_sentences) >= 4:
            summary_parts.append(f"The core concepts explored include {'. '.join(summary_sentences[2:4])}.")
        
        # Applications and implications paragraph
        if len(summary_sentences) >= 6:
            summary_parts.append(f"Key applications and implications discussed are {'. '.join(summary_sentences[4:6])}.")
        
        # Conclusion paragraph
        if len(summary_sentences) >= 8:
            summary_parts.append(f"The content concludes with {'. '.join(summary_sentences[6:8])}.")
        
        summary = ' '.join(summary_parts) if summary_parts else '. '.join(summary_sentences) + '.'
        
        # Enhanced learning objectives generation
        learning_objectives = [
            "By the end of this content, learners will be able to identify and explain the main concepts presented",
            "Students will understand the practical applications and real-world relevance of the discussed topics",
            "Learners will demonstrate comprehension through analysis and synthesis of key information",
            "Students will be able to connect new knowledge with existing understanding and experiences",
            "Learners will develop critical thinking skills through evaluation of presented concepts and evidence"
        ]
        
        # Enhanced key points extraction
        key_points = []
        importance_keywords = ['important', 'key', 'main', 'essential', 'crucial', 'significant', 'fundamental', 'critical', 'vital', 'primary']
        
        for sentence in sentences[:15]:
            if len(sentence) > 25 and len(sentence) < 200:
                if any(word in sentence.lower() for word in importance_keywords):
                    key_points.append(f"{sentence.strip()} - This concept is fundamental to understanding the broader topic.")
        
        # Add additional key points from content analysis
        if len(sentences) > 10:
            key_points.extend([
                f"Content analysis reveals {word_count} words covering comprehensive educational material",
                f"The material is structured across {len(paragraphs)} main sections for optimal learning progression",
                "Multiple learning modalities are supported through varied content presentation approaches"
            ])
        
        # Enhanced definition extraction with context
        definition_patterns = [
            r'(\w+)\s+is\s+(.+)', r'(\w+)\s+means\s+(.+)', r'(\w+)\s+refers to\s+(.+)',
            r'(\w+)\s+can be defined as\s+(.+)', r'(\w+)\s+represents\s+(.+)', r'(\w+)\s+involves\s+(.+)'
        ]
        definitions = []
        for sentence in sentences[:20]:
            for pattern in definition_patterns:
                matches = re.finditer(pattern, sentence, re.IGNORECASE)
                for match in matches:
                    term = match.group(1).strip()
                    definition = match.group(2).strip()
                    if len(term) < 30 and len(definition) < 300 and len(definition) > 10:
                        definitions.append({
                            "term": term,
                            "definition": definition,
                            "etymology": "Term origin and background context",
                            "synonyms": ["Related terms", "Alternative expressions"],
                            "usage_context": f"This term is commonly used when discussing {term.lower()} in educational contexts"
                        })
        
        # Enhanced examples extraction with analysis
        examples = []
        example_keywords = ['example', 'for instance', 'such as', 'like', 'including', 'namely', 'specifically', 'particularly']
        
        for sentence in sentences:
            if any(word in sentence.lower() for word in example_keywords):
                if len(sentence) < 250 and len(sentence) > 20:
                    examples.append({
                        "title": f"Practical Example: {sentence[:30]}...",
                        "description": sentence.strip(),
                        "analysis": "This example effectively demonstrates the practical application of theoretical concepts",
                        "real_world_context": "This scenario commonly occurs in professional and academic settings",
                        "learning_value": "Helps bridge the gap between theory and practice"
                    })
        
        # Comprehensive question categories
        questions = [
            {
                "category": "Comprehension",
                "questions": [
                    "What are the fundamental principles underlying the main concepts?",
                    "How would you summarize the key ideas in your own words?",
                    "What are the essential components that make up the core concepts?",
                    "Which aspects of the content are most critical for basic understanding?"
                ]
            },
            {
                "category": "Application",
                "questions": [
                    "How could you apply these concepts in a real-world scenario?",
                    "What steps would you take to implement these ideas practically?",
                    "In what situations would this knowledge be most valuable?",
                    "How might different contexts require modifications to these approaches?"
                ]
            },
            {
                "category": "Analysis",
                "questions": [
                    "What are the strengths and limitations of the presented approaches?",
                    "How do these concepts compare to alternative methods or theories?",
                    "What evidence supports the main arguments presented?",
                    "What assumptions underlie the key concepts discussed?"
                ]
            },
            {
                "category": "Synthesis",
                "questions": [
                    "How could you combine these ideas with other knowledge you possess?",
                    "What new insights emerge when connecting these concepts?",
                    "How might these ideas evolve or develop in the future?",
                    "What creative applications could emerge from this knowledge?"
                ]
            }
        ]
        
        # Enhanced common mistakes with detailed analysis
        common_mistakes = [
            {
                "mistake": "Superficial understanding without grasping underlying principles",
                "why_it_happens": "Students often focus on memorizing facts rather than understanding concepts",
                "how_to_avoid": "Engage with material actively through questioning and application exercises",
                "correct_approach": "Seek to understand the 'why' behind each concept, not just the 'what'"
            },
            {
                "mistake": "Failing to connect new information with existing knowledge",
                "why_it_happens": "Information is processed in isolation without integration",
                "how_to_avoid": "Actively look for connections and relationships between concepts",
                "correct_approach": "Create concept maps and regularly review how new learning relates to prior knowledge"
            },
            {
                "mistake": "Passive consumption without active engagement",
                "why_it_happens": "Traditional learning habits emphasize receiving rather than processing information",
                "how_to_avoid": "Take notes, ask questions, and discuss concepts with others",
                "correct_approach": "Engage multiple senses and learning modalities for deeper understanding"
            }
        ]
        
        # Enhanced visual notes and memory aids
        visual_notes = [
            {
                "type": "Concept Map",
                "description": "Visual representation showing relationships between main concepts",
                "key_features": ["Central concepts", "Connecting relationships", "Hierarchical structure"],
                "interpretation": "Follow connections to understand how concepts relate and build upon each other",
                "creation_tips": "Start with main concept in center, add related ideas, draw connections with labeled relationships"
            },
            {
                "type": "Timeline or Process Flow",
                "description": "Sequential representation of processes or historical development",
                "key_features": ["Chronological order", "Key milestones", "Cause-and-effect relationships"],
                "interpretation": "Understand progression and development over time",
                "creation_tips": "Identify key events or steps, arrange chronologically, note important transitions"
            }
        ]
        
        # Enhanced important facts with context
        important_facts = [
            {
                "fact": f"Content contains approximately {word_count} words of educational material",
                "source": "Content analysis and word count assessment",
                "significance": "Indicates comprehensive coverage requiring sustained attention and study time",
                "context": "Typical educational content of this length requires 15-30 minutes of focused study",
                "implications": "Learners should plan adequate time for thorough comprehension and review"
            },
            {
                "fact": f"Material is organized into {len(paragraphs)} distinct sections",
                "source": "Structural analysis of content organization",
                "significance": "Demonstrates logical progression and systematic approach to topic coverage",
                "context": "Well-structured content facilitates better comprehension and retention",
                "implications": "Students can use section breaks as natural study intervals and review points"
            }
        ]
        
        # Memory aids and mnemonics
        mnemonics_and_memory_aids = [
            {
                "concept": "Main topic retention",
                "technique": "Acronym creation using first letters of key concepts",
                "explanation": "Create memorable acronyms from the first letters of important terms to aid recall"
            },
            {
                "concept": "Sequential information",
                "technique": "Story method linking concepts in narrative form",
                "explanation": "Create a story that incorporates key concepts in order to leverage narrative memory"
            },
            {
                "concept": "Complex relationships",
                "technique": "Visual association and spatial memory",
                "explanation": "Create mental images that represent relationships between concepts using spatial arrangements"
            }
        ]
        
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
        
        # Additional comprehensive features
        further_reading = [
            {
                "category": "Foundational Knowledge",
                "suggestions": [
                    "Introductory textbooks covering the fundamental concepts presented",
                    "Academic articles providing theoretical background",
                    "Online courses offering structured learning paths"
                ]
            },
            {
                "category": "Advanced Topics",
                "suggestions": [
                    "Research papers exploring cutting-edge developments",
                    "Professional journals with current industry insights",
                    "Advanced coursework for deeper specialization"
                ]
            },
            {
                "category": "Practical Applications",
                "suggestions": [
                    "Case study collections demonstrating real-world implementation",
                    "Professional development workshops and seminars",
                    "Industry reports and best practice guides"
                ]
            }
        ]
        
        assessment_criteria = [
            {
                "skill": "Conceptual Understanding",
                "beginner": "Can identify and recall basic concepts and terminology",
                "intermediate": "Can explain concepts and their relationships with some detail",
                "advanced": "Can analyze concepts critically and apply them in new contexts",
                "expert": "Can synthesize concepts to create new insights and solve complex problems"
            },
            {
                "skill": "Practical Application",
                "beginner": "Can follow step-by-step instructions for basic applications",
                "intermediate": "Can adapt procedures to slightly different contexts",
                "advanced": "Can design and implement solutions for novel problems",
                "expert": "Can innovate and create new approaches based on deep understanding"
            }
        ]
        
        interdisciplinary_connections = [
            {
                "field": "Psychology",
                "connection": "Understanding how learning and cognition relate to the presented concepts",
                "examples": ["Memory formation", "Cognitive load theory", "Motivation and engagement"],
                "benefits": "Enhances learning effectiveness and retention strategies"
            },
            {
                "field": "Technology",
                "connection": "Digital tools and platforms that support concept implementation",
                "examples": ["Software applications", "Online platforms", "Digital resources"],
                "benefits": "Provides modern tools for enhanced learning and application"
            }
        ]
        
        practical_exercises = [
            {
                "title": "Concept Mapping Exercise",
                "objective": "Create visual representations of concept relationships",
                "instructions": "1. Identify main concepts, 2. Determine relationships, 3. Create visual map, 4. Review and refine",
                "materials_needed": ["Paper or digital mapping tool", "Colored pens or software"],
                "time_estimate": "30-45 minutes",
                "difficulty_level": "Intermediate",
                "assessment_rubric": "Evaluate completeness, accuracy of relationships, and visual clarity"
            },
            {
                "title": "Application Scenario Analysis",
                "objective": "Apply learned concepts to realistic scenarios",
                "instructions": "1. Read scenario, 2. Identify relevant concepts, 3. Develop solution approach, 4. Present reasoning",
                "materials_needed": ["Scenario descriptions", "Analysis worksheet"],
                "time_estimate": "45-60 minutes",
                "difficulty_level": "Advanced",
                "assessment_rubric": "Assess concept application accuracy, reasoning quality, and solution feasibility"
            }
        ]
        
        reflection_prompts = [
            "How does this new knowledge change your understanding of related topics?",
            "What connections can you make between this content and your previous experiences?",
            "What questions do you still have after learning this material?",
            "How might you apply these concepts in your personal or professional life?",
            "What was most challenging about this content and why?",
            "What strategies helped you understand this material best?",
            "How confident do you feel about explaining these concepts to others?",
            "What additional resources would help deepen your understanding?"
        ]
        
        extension_activities = [
            {
                "activity": "Research Project",
                "description": "Conduct independent research on a related topic of interest",
                "learning_goals": ["Develop research skills", "Deepen subject knowledge", "Practice critical evaluation"],
                "resources_needed": ["Library access", "Internet connection", "Research databases"],
                "collaboration": "Can be done individually or in small groups",
                "assessment": "Evaluate research quality, source credibility, and presentation of findings"
            },
            {
                "activity": "Peer Teaching Session",
                "description": "Prepare and deliver a mini-lesson on a key concept to classmates",
                "learning_goals": ["Reinforce understanding through teaching", "Develop communication skills", "Practice knowledge synthesis"],
              j,   "resources_needed": ["Presentation materials", "Teaching space", "Feedback forms"],
                "collaboration": "Individual preparation with group presentation",
                "assessment": "Assess content accuracy, presentation clarity, and engagement techniques"
            }
        ]
        
        # Case studies for deeper analysis
        case_studies = [
            {
                "title": "Real-World Application Case Study",
                "scenario": "Detailed scenario showing how the concepts apply in professional settings",
                "analysis_questions": [
                    "What factors contributed to the success or challenges in this case?",
                    "How could the approach have been modified for better outcomes?",
                    "What lessons can be applied to similar situations?"
                ],
                "key_lessons": [
                    "Practical implementation requires adaptation to specific contexts",
                    "Multiple factors influence successful application of theoretical concepts"
                ]
            }
        ]
        
        # Step-by-step processes for complex procedures
        step_by_step_processes = [
            {
                "process_name": "Comprehensive Learning Approach",
                "steps": [
                    {
                        "step": 1,
                        "action": "Initial content review and overview",
                        "rationale": "Provides context and prepares mind for detailed learning",
                        "common_errors": "Skipping overview and jumping into details too quickly"
                    },
                    {
                        "step": 2,
                        "action": "Active note-taking and concept identification",
                        "tips": "Use multiple formats: text, visual, and audio notes",
                        "checkpoints": "Can identify and list main concepts clearly"
                    },
                        clean_word = 
                    {
                        "step": 3clean_word,
                            "word_id": f"word_{i}_{j}",
                        "action": "Application and practice exercises",
                        "rationale": "Reinforces learning through active engagement",
                        "common_errors": "Passive reading without active application"
                    }
                ],
                "prerequisites": ["Basic study skills", "Access to learning materials"],
                "expected_outcomes": ["Deep understanding", "Practical application ability", "Long-term retention"]
            }
        ]
        
        # Detailed concepts for comprehensive understanding
        detailed_concepts = []
        if key_points:
            for i, point in enumerate(key_points[:3]):
                detailed_concepts.append({
                    "concept": f"Core Concept {i+1}",
                    "explanation": f"In-depth analysis: {point}",
                    "phrase_id": f"phrase_{i}",
                    "importance": "This concept forms a foundation for understanding the broader topic",
                    "applications": ["Academic study", "Professional development", "Personal growth"],
                    "prerequisites": ["Basic familiarity with the subject area"],
                    "connections": ["Links to related concepts in the field", "Builds upon previous learning"]
                })
        
        # Deep analysis features for comprehensive understanding
        word_by_word_analysis = []
        for sentence in sentences[:5]:  # Analyze first 5 sentences in detail
            if len(sentence) > 20:
                words = sentence.split()
                word_breakdown = []
                for word in words[:10]:  # Analyze first 10 words of each sentence
                    if len(word) > 3:  # Skip very short words
                        word_breakdown.append({
                            "word": word.strip('.,!?;:'),
                            "meaning": f"In this context, '{word}' refers to a key concept that requires detailed explanation",
                            "technical_definition": f"Academic definition: {word} represents a fundamental element in this field of study",
                            "why_important": f"This word is crucial because it establishes the foundation for understanding the broader concept",
                            "related_concepts": [f"Related concept 1 for {word}", f"Related concept 2 for {word}"]
                        })
                
                word_by_word_analysis.append({
                    "phrase": sentence,
                    "word_breakdown": word_breakdown[:5],  # Limit to first 5 words for brevity
                    "phrase_explanation": f"This sentence establishes a fundamental principle by explaining: {sentence[:100]}...",
                    "deeper_implications": f"The deeper meaning reveals how this concept connects to broader theoretical frameworks",
                    "research_context": f"Researchers in this field would interpret this as evidence of the systematic approach to understanding",
                    "clickable_details": [
                        {
                            "detail_id": f"phrase_deep_{i}",
                            "summary": "Click for deeper analysis of this phrase's theoretical implications",
                            "prompt_for_ai": f"Explain in detail why this phrase '{sentence[:50]}...' is theoretically significant and how it connects to broader academic frameworks"
                        },
                        {
                            "detail_id": f"phrase_practical_{i}",
                            "summary": "Click for practical applications of this concept",
                            "prompt_for_ai": f"Provide detailed practical applications and real-world examples of the concept expressed in: '{sentence[:50]}...'"
                        }
                    ]
                })
        
        concept_deep_dive = []
        for i, point in enumerate(key_points[:3]):
            concept_deep_dive.append({
                "concept": f"Core Concept {i+1}",
                "concept_id": f"concept_deep_{i}",
                "basic_explanation": f"For beginners: {point[:100]}... This means that the fundamental idea is accessible to newcomers",
                "intermediate_explanation": f"For intermediate learners: This concept builds upon basic knowledge by adding layers of complexity and real-world applications",
                "advanced_explanation": f"For advanced students: The nuanced understanding involves recognizing the interconnections, limitations, and edge cases",
                "research_level_explanation": f"For researchers: This concept represents a critical node in the theoretical framework with implications for methodology and analysis",
                "historical_context": f"This concept developed over time through the work of multiple researchers and theoretical evolution",
                "current_debates": f"Current scholarly discussions focus on the boundaries, applications, and future development of this concept",
                "future_directions": f"Research is moving toward more sophisticated understanding and practical applications",
                "mathematical_foundations": f"The logical and mathematical basis involves systematic analysis and quantitative approaches where applicable",
                "philosophical_implications": f"This concept raises fundamental questions about the nature of knowledge and understanding in this field",
                "sub_explanations": [
                    {
                        "aspect": "practical applications",
                        "explanation": f"How this concept is applied in real-world scenarios: {point[:50]}... demonstrates practical relevance",
                        "examples": [f"Industry application of concept {i+1}", f"Professional practice example for concept {i+1}"],
                        "clickable_id": f"concept_practical_{i}",
                        "interactive_prompts": [
                            f"How would this concept apply in different industries?",
                            f"What are the limitations of this concept in practice?",
                            f"Can you provide more specific examples of implementation?"
                        ]
                    },
                    {
                        "aspect": "theoretical foundations",
                        "explanation": f"The underlying theoretical principles that support this concept: {point[:50]}... has deep theoretical roots",
                        "examples": [f"Theoretical framework 1 for concept {i+1}", f"Academic foundation for concept {i+1}"],
                        "clickable_id": f"concept_theory_{i}",
                        "interactive_prompts": [
                            f"What are the philosophical assumptions behind this concept?",
                            f"How does this theory compare to alternative approaches?",
                            f"What evidence supports this theoretical foundation?"
                        ]
                    },
                    {
                        "aspect": "research implications",
                        "explanation": f"Current and future research directions related to this concept: {point[:50]}... opens new research avenues",
                        "examples": [f"Current research on concept {i+1}", f"Future research directions for concept {i+1}"],
                        "clickable_id": f"concept_research_{i}",
                        "interactive_prompts": [
                            f"What questions remain unanswered about this concept?",
                            f"How might future technology change our understanding?",
                            f"What interdisciplinary approaches could enhance research?"
                        ]
                    }
                ],
                "clickable_details": [
                    {
                        "detail_id": f"concept_expert_{i}",
                        "summary": "Click for expert-level analysis of this concept's implications",
                        "prompt_for_ai": f"Provide an expert-level analysis of this concept '{point[:50]}...' including cutting-edge research, unresolved questions, and implications for future development in the field"
                    },
                    {
                        "detail_id": f"concept_compare_{i}",
                        "summary": "Click for comparative analysis with related concepts",
                        "prompt_for_ai": f"Compare and contrast this concept '{point[:50]}...' with related concepts in the field, highlighting similarities, differences, and when to use each approach"
                    },
                    {
                        "detail_id": f"concept_history_{i}",
                        "summary": "Click for detailed historical development of this concept",
                        "prompt_for_ai": f"Provide a detailed historical analysis of how this concept '{point[:50]}...' developed over time, including key researchers, milestones, and paradigm shifts"
                    }
                ]
            })
        
        terminology_encyclopedia = []
        for definition in definitions[:3]:
            terminology_encyclopedia.append({
                "term": definition.get("term", "Key Term"),
                "pronunciation": f"Pronunciation guide for {definition.get('term', 'term')}",
                "definition_levels": {
                    "elementary": f"For young students: {definition.get('term', 'This term')} is like a simple concept that helps us understand basic ideas",
                    "high_school": f"For high school: {definition.get('term', 'This term')} represents a more complex idea that connects to other concepts",
                    "undergraduate": f"For college students: {definition.get('term', 'This term')} is a sophisticated concept requiring analytical thinking",
                    "graduate": f"For graduate students: {definition.get('term', 'This term')} involves complex theoretical understanding and research implications",
                    "expert": f"For experts: {definition.get('term', 'This term')} represents a nuanced concept with multiple interpretations and applications"
                },
                "etymology": f"The term '{definition.get('term', 'term')}' originates from academic discourse and has evolved through scholarly usage",
                "evolution": f"The meaning has developed from basic usage to sophisticated academic and professional applications",
                "field_specific_usage": f"Different disciplines may use this term with slightly different emphases and applications",
                "common_misconceptions": f"Students often misunderstand this term by oversimplifying or confusing it with related concepts",
                "related_terminology": f"This term connects to a network of related concepts that form the theoretical foundation",
                "usage_examples": [
                    {"context": "academic paper", "example": f"In research literature: '{definition.get('term', 'term')}' appears in theoretical discussions"},
                    {"context": "practical application", "example": f"In real-world contexts: this term guides practical decision-making and implementation"}
                ]
            })
        
        sentence_by_sentence_breakdown = []
        for sentence in sentences[:3]:  # Analyze first 3 sentences in detail
            if len(sentence) > 15:
                sentence_by_sentence_breakdown.append({
                    "sentence": sentence,
                    "grammatical_analysis": f"Subject-verb-object structure: This sentence follows standard academic discourse patterns with clear logical progression",
                    "content_analysis": f"Information conveyed: {sentence[:80]}... establishes foundational understanding",
                    "implicit_assumptions": f"The sentence assumes readers have basic familiarity with the field and its terminology",
                    "logical_structure": f"This sentence builds an argument by presenting evidence, reasoning, or establishing context",
                    "technical_terms_used": [word for word in sentence.split() if len(word) > 6][:5],
                    "connection_to_previous": f"This sentence connects to previous content by building upon established concepts",
                    "connection_to_following": f"This sentence prepares readers for more complex ideas that follow",
                    "alternative_phrasings": [f"Alternative 1: {sentence[:50]}... could be expressed differently", "Alternative 2: Using simpler language for broader accessibility"],
                    "complexity_level": f"This sentence requires {'undergraduate' if len(sentence) > 100 else 'high school'} level comprehension"
                })
        
        research_methodology_analysis = [{
            "concept": "Primary research concept",
            "methodology_explanation": "Researchers study this concept through systematic observation, data collection, and analysis",
            "data_collection_methods": "Methods include surveys, experiments, case studies, and observational research",
            "analysis_techniques": "Statistical analysis, qualitative coding, and theoretical modeling are commonly used",
            "limitations_and_challenges": "Research faces challenges in measurement, generalizability, and ethical considerations",
            "current_research_trends": "Current focus includes interdisciplinary approaches and technological integration",
            "future_research_directions": "Future research will likely explore new methodologies and expanded applications"
        }]
        
        cognitive_load_analysis = []
        for point in key_points[:2]:
            cognitive_load_analysis.append({
                "concept": f"Complex concept: {point[:30]}...",
                "intrinsic_load": "This concept has moderate inherent complexity requiring focused attention",
                "extraneous_load": "Unnecessary complexity can be reduced through better organization and clearer explanations",
                "germane_load": "Mental effort needed involves connecting new information to existing knowledge structures",
                "scaffolding_suggestions": "Break into smaller components, provide examples, use visual aids, and check understanding frequently",
                "prerequisite_knowledge": "Students need basic understanding of foundational concepts and terminology",
                "common_cognitive_barriers": "Students struggle with abstract thinking, making connections, and applying concepts"
            })
        
        expert_vs_novice_perspectives = []
        for point in key_points[:2]:
            expert_vs_novice_perspectives.append({
                "concept": f"Key concept: {point[:30]}...",
                "novice_understanding": "Beginners focus on surface features and memorization of basic facts",
                "expert_understanding": "Experts see deep patterns, connections, and can apply knowledge flexibly across contexts",
                "transition_pathway": "Understanding develops through practice, feedback, and gradual exposure to complexity",
                "common_misconceptions": "Novices often oversimplify or misapply concepts due to limited experience",
                "expert_shortcuts": "Experts use mental models and pattern recognition for efficient problem-solving",
                "teaching_implications": "Instruction should bridge gaps by making expert thinking visible and providing scaffolding"
            })
        
        linguistic_analysis = []
        for sentence in sentences[:2]:
            if len(sentence) > 20:
                linguistic_analysis.append({
                    "phrase": sentence,
                    "register_analysis": "Academic register with formal vocabulary and complex sentence structures",
                    "discourse_markers": "Words like 'however', 'therefore', 'furthermore' signal logical relationships",
                    "modal_verbs_analysis": "Use of 'can', 'should', 'must' indicates degrees of certainty and obligation",
                    "passive_vs_active_voice": "Voice choices reflect academic conventions and emphasis on objectivity",
                    "nominalization_analysis": "Complex noun phrases pack information densely but may challenge comprehension",
                    "cohesion_devices": "Pronouns, synonyms, and logical connectors link ideas across sentences",
                    "pragmatic_implications": "The speaker implies expertise and expects shared academic background"
                })
        
        metacognitive_guidance = [{
            "learning_stage": "Introduction to core concepts",
            "self_monitoring_questions": [
                "Do I understand the main idea?",
                "Can I explain this in my own words?",
                "What connections can I make to what I already know?",
                "Where am I getting confused?"
            ],
            "comprehension_checkpoints": [
                "Can identify key terms and their meanings",
                "Can summarize main points accurately",
                "Can provide examples or applications"
            ],
            "common_confusion_points": [
                "Abstract concepts without concrete examples",
                "Technical terminology used without definition",
                "Complex relationships between multiple concepts"
            ],
            "recovery_strategies": [
                "Re-read slowly and take notes",
                "Look up unfamiliar terms",
                "Seek additional examples or explanations",
                "Discuss with others or ask questions"
            ],
            "connection_prompts": [
                "How does this relate to what I learned before?",
                "What real-world examples can I think of?",
                "How might I use this information?"
            ],
            "application_readiness": [
                "Can explain concepts to someone else",
                "Can generate new examples",
                "Can identify when and how to apply knowledge"
            ]
        }]
        
        return {
            "title": title,
            "subtitle": subtitle,
            "summary": summary,
            "learning_objectives": learning_objectives,
            "key_points": key_points,
            "detailed_concepts": detailed_concepts,
            "word_by_word_analysis": word_by_word_analysis,
            "concept_deep_dive": concept_deep_dive,
            "terminology_encyclopedia": terminology_encyclopedia,
            "definitions": definitions,
            "sentence_by_sentence_breakdown": sentence_by_sentence_breakdown,
            "examples": examples,
            "case_studies": case_studies,
            "step_by_step_processes": step_by_step_processes,
            "questions": questions,
            "common_mistakes": common_mistakes,
            "visual_notes": visual_notes,
            "important_facts": important_facts,
            "mnemonics_and_memory_aids": mnemonics_and_memory_aids,
            "further_reading": further_reading,
            "assessment_criteria": assessment_criteria,
            "interdisciplinary_connections": interdisciplinary_connections,
            "practical_exercises": practical_exercises,
            "reflection_prompts": reflection_prompts,
            "extension_activities": extension_activities,
            "research_methodology_analysis": research_methodology_analysis,
            "cognitive_load_analysis": cognitive_load_analysis,
            "expert_vs_novice_perspectives": expert_vs_novice_perspectives,
            "linguistic_analysis": linguistic_analysis,
            "metacognitive_guidance": metacognitive_guidance,
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
You are an expert note-taker and educational content analyst. Your task is to extract comprehensive, detailed notes from the provided video transcript, then organize them into a rich mind map structure.

### PHASE 1: COMPREHENSIVE NOTE EXTRACTION
First, extract **detailed notes** from the transcript following these principles:

**NOTE EXTRACTION REQUIREMENTS:**
- **Minimum 20 notes** from ANY video, regardless of length
- **Extract EVERYTHING**: Every technique, method, concept, tip, insight, example, or piece of advice mentioned
- **Expand brief mentions**: If something is mentioned in passing, create a full explanatory note
- **Include context**: Each note should be self-contained and educational
- **Capture specifics**: Numbers, steps, processes, tools, examples, warnings, best practices

**NOTE CATEGORIES TO CAPTURE:**
- **Techniques & Methods**: How-to information, step-by-step processes
- **Tools & Resources**: Software, apps, books, websites mentioned
- **Examples & Case Studies**: Real-world applications and scenarios
- **Best Practices**: Recommended approaches and strategies  
- **Key Insights**: Important realizations, principles, or concepts
- **Common Mistakes**: Pitfalls to avoid, warnings given
- **Implementation Steps**: Specific actions to take
- **Tips & Tricks**: Practical advice and shortcuts
- **Background Context**: Why something matters, historical context
- **Quantitative Data**: Numbers, statistics, measurements mentioned

### PHASE 2: MIND MAP ORGANIZATION
After extracting comprehensive notes, organize them into a hierarchical mind map structure:

**ORGANIZATIONAL PRINCIPLES:**
- Group related notes into logical main topics (3-8 main topics)
- Create subtopics that contain 3-8 related notes each
- Add child nodes for detailed breakdowns when notes support it
- Ensure every note finds a place in the hierarchy
- Maintain the natural flow and order from the video

### INSTRUCTIONS FOR OUTPUT:
- Respond ONLY with **valid JSON** (no explanations, no extra text)
- Transform ALL extracted notes into the mind map structure
- Each note should become part of details, examples, or key_points arrays
- **No note left behind**: Every extracted insight must appear in the final mind map
- Create rich, educational content that serves as a complete study guide
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
### COMPREHENSIVE NOTE-BASED QUALITY REQUIREMENTS:

**NOTE EXTRACTION STANDARDS:**
- **Minimum 20 detailed notes** from any video, regardless of length (short videos may yield 20-30 notes, longer videos 40+ notes)
- **Maximum Coverage**: Extract every meaningful piece of information mentioned
- **Educational Expansion**: Transform brief mentions into full educational explanations
- **Self-Contained Notes**: Each note should be complete and understandable on its own
- **Actionable Content**: Focus on practical, implementable information

**NOTE QUALITY CRITERIA:**
- **Specific over General**: "Use 25-minute work blocks with 5-minute breaks" vs "Take breaks"
- **Complete Context**: Include why something matters, not just what it is
- **Implementation Details**: How to actually do something, not just that you should do it
- **Real Examples**: Concrete instances mentioned in the video, not generic examples
- **Quantitative Data**: Capture any numbers, percentages, timeframes, or measurements

**MIND MAP ORGANIZATION STANDARDS:**
- **Logical Grouping**: Related notes grouped into coherent main topics and subtopics
- **Hierarchical Structure**: 3-8 main topics, each with 3-8 subtopics, child nodes when appropriate
- **Complete Integration**: Every extracted note must appear somewhere in the final mind map
- **Natural Flow**: Maintain the order and progression from the original video
- **Rich Content Distribution**: 
  - `details`: Step-by-step processes, methodologies, explanations (2-6 per node)
  - `examples`: Specific instances, use cases, real scenarios mentioned (1-4 per node)
  - `key_points`: Critical insights, best practices, important facts (2-5 per node)

**CHILD NODES CREATION:**
- Create child nodes when a subtopic contains multiple distinct techniques, steps, or aspects
- Each child node should contain 3-8 notes from the extraction phase
- Target 2-6 child nodes per subtopic when content supports detailed breakdown
- Child nodes represent: specific implementations, detailed steps, variations, or specialized aspects

**CONTENT TRANSFORMATION RULES:**
- **Every note becomes content**: Transform each extracted note into details, examples, or key_points
- **No redundancy**: Don't repeat the same information across different arrays or levels
- **Educational value**: Each piece of content should teach something practical and actionable
- **Comprehensive coverage**: The final mind map should serve as a complete study guide for the video
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
        
        # For comprehensive mind maps, include more main topics for longer content
        # Allow up to 8 main topics for extensive educational coverage
        limited_content_structure = all_content_structure[:8]  # Max 8 main topics for comprehensive learning
        
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