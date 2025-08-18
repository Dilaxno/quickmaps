"""
Quiz Generator for Learning Notes
Generates various types of quizzes from structured learning notes
"""

import logging
import json
import re
import random
from typing import Dict, List, Optional, Tuple
import os
import time
import threading
from groq import Groq
from config import GROQ_API_KEY, GROQ_MODEL

logger = logging.getLogger(__name__)

# Global throttling for quiz Groq calls (share with notes throttle interval if env set)
_QUIZ_THROTTLE_LOCK = threading.Lock()
_QUIZ_LAST_TS = 0.0
try:
    _QUIZ_MIN_INTERVAL = float(os.getenv("GROQ_MIN_INTERVAL_SECONDS", "1.0"))
except Exception:
    _QUIZ_MIN_INTERVAL = 1.0

class QuizGenerator:
    """Generate interactive quizzes from learning notes"""
    
    def __init__(self):
        if not GROQ_API_KEY:
            logger.warning("GROQ_API_KEY not set. Quiz generation will be disabled.")
            self.client = None
        else:
            self.client = Groq(api_key=GROQ_API_KEY)
            self._install_throttling()
    
    def _install_throttling(self):
        try:
            original_create = self.client.chat.completions.create
            def throttled_create(*args, **kwargs):
                global _QUIZ_LAST_TS
                with _QUIZ_THROTTLE_LOCK:
                    now = time.time()
                    elapsed = now - _QUIZ_LAST_TS
                    if elapsed < _QUIZ_MIN_INTERVAL:
                        sleep_for = _QUIZ_MIN_INTERVAL - elapsed
                        if sleep_for > 0:
                            time.sleep(sleep_for)
                    result = original_create(*args, **kwargs)
                    _QUIZ_LAST_TS = time.time()
                    return result
            self.client.chat.completions.create = throttled_create
            logger.info(f"Groq quiz throttling installed: min {_QUIZ_MIN_INTERVAL}s between requests")
        except Exception as e:
            logger.warning(f"Failed to install Groq throttling wrapper for quiz: {e}")

    def is_available(self) -> bool:
        """Check if quiz generation is available"""
        return self.client is not None
    
    def generate_quiz(self, notes_content: str, num_questions: int = 10) -> Optional[Dict]:
        """
        Generate a comprehensive quiz from learning notes
        
        Args:
            notes_content: The structured learning notes content
            num_questions: Number of questions to generate (default: 10)
            
        Returns:
            Dictionary containing quiz data with different question types
        """
        if not self.is_available():
            logger.warning("Quiz generation not available - Groq API not configured")
            return None
        
        if not notes_content or len(notes_content.strip()) < 100:
            logger.warning("Notes content too short for quiz generation")
            return None
        
        try:
            # Generate different types of questions
            quiz_data = {
                "title": self._extract_title(notes_content),
                "total_questions": num_questions,
                "questions": [],
                "max_score": num_questions * 10,  # 10 points per question
                "instructions": "Answer all questions to test your understanding of the material. Each question is worth 10 points."
            }
            
            # Generate mixed question types
            question_types = [
                ("multiple_choice", 4),
                ("true_false", 2), 
                ("fill_in_blank", 2),
                ("short_answer", 2)
            ]
            
            questions_generated = 0
            for question_type, count in question_types:
                if questions_generated >= num_questions:
                    break
                    
                remaining = min(count, num_questions - questions_generated)
                type_questions = self._generate_questions_by_type(
                    notes_content, question_type, remaining
                )
                
                if type_questions:
                    # Validate questions are answerable from notes
                    validated_questions = self._validate_questions_against_notes(
                        type_questions, notes_content
                    )
                    quiz_data["questions"].extend(validated_questions)
                    questions_generated += len(validated_questions)
            
            # Shuffle questions for variety
            random.shuffle(quiz_data["questions"])
            
            # Update actual question count
            quiz_data["total_questions"] = len(quiz_data["questions"])
            quiz_data["max_score"] = len(quiz_data["questions"]) * 10
            
            return quiz_data
            
        except Exception as e:
            logger.error(f"Error generating quiz: {e}")
            return None
    
    def _extract_title(self, notes_content: str) -> str:
        """Extract title from notes content"""
        lines = notes_content.split('\n')
        for line in lines:
            line = line.strip()
            if line.startswith('# '):
                return line[2:].strip()
            elif line.startswith('## ') and not line.startswith('### '):
                return line[3:].strip()
        return "Learning Quiz"
    
    def _generate_questions_by_type(self, notes_content: str, question_type: str, count: int) -> List[Dict]:
        """Generate questions of a specific type"""
        try:
            prompt = self._get_question_prompt(notes_content, question_type, count)
            
            response = self.client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert educational assessment creator. Generate high-quality quiz questions that test understanding, not just memorization. CRITICAL: You must ONLY create questions that can be answered using the provided learning notes. Do not include any external knowledge or information not present in the notes."
                    },
                    {
                        "role": "user", 
                        "content": prompt
                    }
                ],
                temperature=0.5,  # Reduced temperature for more focused responses
                max_tokens=2000,
                top_p=0.9
            )
            
            response_text = response.choices[0].message.content.strip()
            return self._parse_questions_response(response_text, question_type)
            
        except Exception as e:
            logger.error(f"Error generating {question_type} questions: {e}")
            return []
    
    def _get_question_prompt(self, notes_content: str, question_type: str, count: int) -> str:
        """Get prompt for specific question type"""
        
        base_prompt = f"""Based STRICTLY on the following learning notes, create {count} high-quality {question_type.replace('_', ' ')} questions.

CRITICAL REQUIREMENTS:
- ALL questions must be answerable using ONLY the information provided in the notes below
- Do NOT include questions about topics not covered in the notes
- Do NOT ask about external knowledge or information not present in the notes
- Focus on key concepts, definitions, and facts that are explicitly mentioned in the notes
- Ensure every correct answer can be found directly in the provided notes content

LEARNING NOTES:
{notes_content}

"""
        
        if question_type == "multiple_choice":
            return base_prompt + f"""Create {count} multiple choice questions. Each question should have:
- A clear question stem based ONLY on information in the notes
- 4 answer options (A, B, C, D) where the correct answer is found in the notes
- Only ONE correct answer that can be verified from the notes content
- Plausible distractors that are related but incorrect based on the notes

IMPORTANT: Every question and answer must be derivable from the notes above. Do not include external knowledge.

Format each question as:
QUESTION: [question text based on notes content]
A) [option A]
B) [option B] 
C) [option C]
D) [option D]
CORRECT: [A/B/C/D]
EXPLANATION: [brief explanation referencing the specific part of the notes that contains the answer]
---"""
        
        elif question_type == "true_false":
            return base_prompt + f"""Create {count} true/false questions that test key concepts from the notes.

IMPORTANT: Each statement must be verifiable as true or false based ONLY on the information in the notes.

Format each question as:
QUESTION: [statement to evaluate based on notes content]
CORRECT: [TRUE/FALSE]
EXPLANATION: [brief explanation referencing the specific part of the notes that supports the answer]
---"""
        
        elif question_type == "fill_in_blank":
            return base_prompt + f"""Create {count} fill-in-the-blank questions using key terms or concepts from the notes.

IMPORTANT: Use sentences directly from the notes or paraphrase them. The missing word/phrase must be explicitly mentioned in the notes.

Format each question as:
QUESTION: [sentence with _____ for the blank, based on notes content]
CORRECT: [correct answer that appears in the notes]
EXPLANATION: [brief explanation referencing where this information appears in the notes]
---"""
        
        elif question_type == "short_answer":
            return base_prompt + f"""Create {count} short answer questions that require 1-2 sentence responses based on the notes.

IMPORTANT: Questions must ask about concepts, definitions, or explanations that are covered in the notes. The sample answer must be derivable from the notes content.

Format each question as:
QUESTION: [question requiring brief explanation about content from the notes]
SAMPLE_ANSWER: [example of a good answer based on the notes content]
KEYWORDS: [key terms from the notes that should be in the answer]
---"""
        
        return base_prompt
    
    def _parse_questions_response(self, response_text: str, question_type: str) -> List[Dict]:
        """Parse the AI response into structured question data"""
        questions = []
        question_blocks = response_text.split('---')
        
        for i, block in enumerate(question_blocks):
            if not block.strip():
                continue
                
            try:
                question_data = {
                    "id": f"q_{question_type}_{i+1}",
                    "type": question_type,
                    "points": 10
                }
                
                if question_type == "multiple_choice":
                    question_data.update(self._parse_multiple_choice(block))
                elif question_type == "true_false":
                    question_data.update(self._parse_true_false(block))
                elif question_type == "fill_in_blank":
                    question_data.update(self._parse_fill_in_blank(block))
                elif question_type == "short_answer":
                    question_data.update(self._parse_short_answer(block))
                
                if "question" in question_data and question_data["question"]:
                    questions.append(question_data)
                    
            except Exception as e:
                logger.error(f"Error parsing question block: {e}")
                continue
        
        return questions
    
    def _parse_multiple_choice(self, block: str) -> Dict:
        """Parse multiple choice question block"""
        lines = [line.strip() for line in block.split('\n') if line.strip()]
        data = {}
        
        for line in lines:
            if line.startswith('QUESTION:'):
                data['question'] = line[9:].strip()
            elif line.startswith('A)'):
                data['options'] = data.get('options', {})
                data['options']['A'] = line[2:].strip()
            elif line.startswith('B)'):
                data['options'] = data.get('options', {})
                data['options']['B'] = line[2:].strip()
            elif line.startswith('C)'):
                data['options'] = data.get('options', {})
                data['options']['C'] = line[2:].strip()
            elif line.startswith('D)'):
                data['options'] = data.get('options', {})
                data['options']['D'] = line[2:].strip()
            elif line.startswith('CORRECT:'):
                data['correct_answer'] = line[8:].strip()
            elif line.startswith('EXPLANATION:'):
                data['explanation'] = line[12:].strip()
        
        return data
    
    def _parse_true_false(self, block: str) -> Dict:
        """Parse true/false question block"""
        lines = [line.strip() for line in block.split('\n') if line.strip()]
        data = {}
        
        for line in lines:
            if line.startswith('QUESTION:'):
                data['question'] = line[9:].strip()
            elif line.startswith('CORRECT:'):
                data['correct_answer'] = line[8:].strip().upper()
            elif line.startswith('EXPLANATION:'):
                data['explanation'] = line[12:].strip()
        
        return data
    
    def _parse_fill_in_blank(self, block: str) -> Dict:
        """Parse fill-in-the-blank question block"""
        lines = [line.strip() for line in block.split('\n') if line.strip()]
        data = {}
        
        for line in lines:
            if line.startswith('QUESTION:'):
                data['question'] = line[9:].strip()
            elif line.startswith('CORRECT:'):
                data['correct_answer'] = line[8:].strip()
            elif line.startswith('EXPLANATION:'):
                data['explanation'] = line[12:].strip()
        
        return data
    
    def _parse_short_answer(self, block: str) -> Dict:
        """Parse short answer question block"""
        lines = [line.strip() for line in block.split('\n') if line.strip()]
        data = {}
        
        for line in lines:
            if line.startswith('QUESTION:'):
                data['question'] = line[9:].strip()
            elif line.startswith('SAMPLE_ANSWER:'):
                sample_answer = line[14:].strip()
                data['sample_answer'] = sample_answer
                data['correct_answer'] = sample_answer  # Also set as correct_answer for consistency
            elif line.startswith('KEYWORDS:'):
                keywords = line[9:].strip()
                data['keywords'] = [k.strip() for k in keywords.split(',')]
            elif line.startswith('EXPLANATION:'):
                data['explanation'] = line[12:].strip()
        
        return data
    
    def _validate_questions_against_notes(self, questions: List[Dict], notes_content: str) -> List[Dict]:
        """
        Validate that questions can be answered from the notes content
        
        Args:
            questions: List of generated questions
            notes_content: The original notes content
            
        Returns:
            List of validated questions (may be fewer than input)
        """
        validated_questions = []
        notes_lower = notes_content.lower()
        
        for question in questions:
            try:
                question_text = question.get('question', '').lower()
                correct_answer = str(question.get('correct_answer', '')).lower()
                question_type = question.get('type', '')
                
                # Skip empty questions
                if not question_text:
                    logger.warning(f"Skipping question with missing text: {question.get('id', 'unknown')}")
                    continue
                
                # For short answer questions, check for sample_answer instead of correct_answer
                if question_type == "short_answer":
                    if not question.get('sample_answer', ''):
                        logger.warning(f"Skipping short answer question with missing sample answer: {question.get('id', 'unknown')}")
                        continue
                elif not correct_answer:
                    logger.warning(f"Skipping question with missing answer: {question.get('id', 'unknown')}")
                    continue
                
                # Basic validation: check if answer appears in notes
                is_valid = False
                
                if question_type == "multiple_choice":
                    # For MC, check if correct answer content is in notes
                    if correct_answer in ['a', 'b', 'c', 'd']:
                        option_key = correct_answer.upper()
                        if 'options' in question and option_key in question['options']:
                            option_text = question['options'][option_key].lower()
                            # Check if the option content appears in notes
                            is_valid = self._check_answer_in_notes(option_text, notes_lower)
                    
                elif question_type == "true_false":
                    # For T/F, check if the statement can be verified from notes
                    # Extract key terms from the question
                    key_terms = self._extract_key_terms(question_text)
                    is_valid = any(term in notes_lower for term in key_terms if len(term) > 3)
                    
                elif question_type == "fill_in_blank":
                    # For fill-in-blank, check if the answer appears in notes
                    is_valid = self._check_answer_in_notes(correct_answer, notes_lower)
                    
                elif question_type == "short_answer":
                    # For short answer, check if key concepts are in notes
                    keywords = question.get('keywords', [])
                    if keywords:
                        keyword_matches = sum(1 for kw in keywords if kw.lower() in notes_lower)
                        is_valid = keyword_matches >= len(keywords) * 0.7  # At least 70% of keywords must be in notes
                    else:
                        # Fallback: check if answer content is in notes
                        sample_answer = question.get('sample_answer', '').lower()
                        is_valid = self._check_answer_in_notes(sample_answer, notes_lower)
                
                if is_valid:
                    validated_questions.append(question)
                else:
                    logger.info(f"Filtered out question not answerable from notes: {question.get('id', 'unknown')}")
                    
            except Exception as e:
                logger.error(f"Error validating question {question.get('id', 'unknown')}: {e}")
                continue
        
        logger.info(f"Validated {len(validated_questions)} out of {len(questions)} questions")
        return validated_questions
    
    def _check_answer_in_notes(self, answer_text: str, notes_lower: str) -> bool:
        """Check if answer content appears in notes"""
        if not answer_text or len(answer_text) < 3:
            return False
            
        # Check for exact match
        if answer_text in notes_lower:
            return True
            
        # Check for partial matches with key terms
        answer_terms = self._extract_key_terms(answer_text)
        matches = sum(1 for term in answer_terms if term in notes_lower and len(term) > 3)
        
        # Require at least 60% of key terms to be present
        return matches >= len(answer_terms) * 0.6 if answer_terms else False
    
    def _extract_key_terms(self, text: str) -> List[str]:
        """Extract key terms from text for validation"""
        import re
        
        # Remove common words and extract meaningful terms
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 'been', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'can', 'this', 'that', 'these', 'those', 'what', 'which', 'who', 'when', 'where', 'why', 'how'}
        
        # Extract words (alphanumeric sequences)
        words = re.findall(r'\b[a-zA-Z]+\b', text.lower())
        
        # Filter out stop words and short words
        key_terms = [word for word in words if word not in stop_words and len(word) > 2]
        
        return key_terms
    
    def evaluate_quiz(self, quiz_data: Dict, user_answers: Dict) -> Dict:
        """
        Evaluate user answers and calculate score
        
        Args:
            quiz_data: The original quiz data
            user_answers: Dictionary of question_id -> user_answer
            
        Returns:
            Dictionary with evaluation results and score
        """
        if not quiz_data or not user_answers:
            return {"score": 0, "max_score": 0, "percentage": 0, "results": []}
        
        results = []
        total_score = 0
        max_score = 0
        
        for question in quiz_data.get("questions", []):
            question_id = question.get("id")
            question_type = question.get("type")
            points = question.get("points", 10)
            max_score += points
            
            user_answer = user_answers.get(question_id, "").strip()
            
            if question_type in ["multiple_choice", "true_false"]:
                is_correct = self._evaluate_exact_match(question, user_answer)
                score = points if is_correct else 0
            elif question_type == "fill_in_blank":
                score = self._evaluate_fill_in_blank(question, user_answer, points)
            elif question_type == "short_answer":
                score = self._evaluate_short_answer(question, user_answer, points)
            else:
                score = 0
            
            total_score += score
            
            result = {
                "question_id": question_id,
                "question": question.get("question", ""),
                "type": question_type,
                "user_answer": user_answer,
                "correct_answer": question.get("correct_answer", ""),
                "score": score,
                "max_points": points,
                "is_correct": score == points,
                "explanation": question.get("explanation", "")
            }
            
            results.append(result)
        
        percentage = (total_score / max_score * 100) if max_score > 0 else 0
        
        return {
            "score": total_score,
            "max_score": max_score,
            "percentage": round(percentage, 1),
            "results": results,
            "grade": self._get_grade(percentage)
        }
    
    def _evaluate_exact_match(self, question: Dict, user_answer: str) -> bool:
        """Evaluate exact match questions (multiple choice, true/false)"""
        correct = question.get("correct_answer", "").strip().upper()
        user = user_answer.strip().upper()
        return correct == user
    
    def _evaluate_fill_in_blank(self, question: Dict, user_answer: str, max_points: int) -> int:
        """Evaluate fill-in-the-blank questions with partial credit"""
        correct = question.get("correct_answer", "").strip().lower()
        user = user_answer.strip().lower()
        
        if user == correct:
            return max_points
        
        # Check for partial matches (synonyms, close answers)
        if len(user) > 0 and (user in correct or correct in user):
            return max_points // 2
        
        return 0
    
    def _evaluate_short_answer(self, question: Dict, user_answer: str, max_points: int) -> int:
        """Evaluate short answer questions based on keywords"""
        if not user_answer.strip():
            return 0
        
        keywords = question.get("keywords", [])
        if not keywords:
            # If no keywords provided, give partial credit for any answer
            return max_points // 2 if len(user_answer.strip()) > 10 else 0
        
        user_lower = user_answer.lower()
        matched_keywords = sum(1 for keyword in keywords if keyword.lower() in user_lower)
        
        if matched_keywords == 0:
            return 0
        elif matched_keywords == len(keywords):
            return max_points
        else:
            # Partial credit based on keyword matches
            return int((matched_keywords / len(keywords)) * max_points)
    
    def _get_grade(self, percentage: float) -> str:
        """Convert percentage to letter grade"""
        if percentage >= 90:
            return "A"
        elif percentage >= 80:
            return "B"
        elif percentage >= 70:
            return "C"
        elif percentage >= 60:
            return "D"
        else:
            return "F"

# Global instance
quiz_generator = QuizGenerator()