"""
Groq API client for LLaMA models with fallback support
Includes multiple model fallbacks for reliability
"""

import logging
import os
from typing import List, Dict, Any, Optional
import asyncio
from groq import Groq
import httpx

logger = logging.getLogger(__name__)

class GroqClient:
    """Async client for Groq API with LLaMA models and fallback support"""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        if not self.api_key:
            raise ValueError("GROQ_API_KEY environment variable is required")
        
        self.client = Groq(api_key=self.api_key)
        
        # Primary model and fallbacks (in order of preference)
        self.models = [
            "llama-3.1-70b-versatile", # Primary: LLaMA 3.1 70B (higher token limit)
            "llama-3.1-8b-instant",    # Fallback 1: LLaMA 3.1 8B
            "llama3-70b-8192",         # Fallback 2: LLaMA 3 70B
            "gemma2-9b-it"             # Fallback 3: Gemma 2 9B
        ]
        self.current_model = self.models[0]
        
    async def __aenter__(self):
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass
        
    async def check_connection(self) -> bool:
        """Test connection to Groq API with fallback models"""
        for i, model in enumerate(self.models):
            try:
                logger.info(f"🧪 Testing Groq API with model: {model}")
                
                response = self.client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "user", "content": "Test"}
                    ],
                    max_tokens=5,
                    temperature=0.1
                )
                
                if response.choices and response.choices[0].message.content:
                    self.current_model = model
                    logger.info(f"✅ Groq API connection successful with {model}")
                    return True
                    
            except Exception as e:
                logger.warning(f"❌ Model {model} failed: {str(e)}")
                if i < len(self.models) - 1:
                    logger.info(f"🔄 Trying fallback model...")
                continue
        
        logger.error("❌ All Groq models failed")
        return False
    
    async def generate_text(
        self,
        prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.7,
        **kwargs
    ) -> Optional[str]:
        """Generate text completion using Groq API with fallback support"""
        last_error = None
        
        for model in self.models:
            try:
                logger.info(f"🔄 Generating text with {model}")
                
                response = self.client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=max_tokens,
                    temperature=temperature,
                    **kwargs
                )
                
                if response.choices and response.choices[0].message:
                    content = response.choices[0].message.content
                    self.current_model = model  # Update successful model
                    logger.info(f"✅ Generated text with {model} ({len(content)} chars)")
                    return content
                    
            except Exception as e:
                logger.warning(f"❌ Model {model} failed: {str(e)}")
                last_error = e
                continue
        
        logger.error(f"❌ All models failed for text generation")
        return None
    
    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 512,
        temperature: float = 0.7,
        **kwargs
    ) -> Optional[str]:
        """Generate chat completion using Groq API with fallback support"""
        last_error = None
        
        for model in self.models:
            try:
                logger.info(f"🔄 Generating chat completion with {model}")
                
                response = self.client.chat.completions.create(
                    model=model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    **kwargs
                )
                
                if response.choices and response.choices[0].message:
                    content = response.choices[0].message.content
                    self.current_model = model  # Update successful model
                    logger.info(f"✅ Generated chat completion with {model} ({len(content)} chars)")
                    return content
                    
            except Exception as e:
                logger.warning(f"❌ Model {model} failed: {str(e)}")
                last_error = e
                continue
        
        logger.error(f"❌ All models failed for chat completion")
        return None


def sync_generate_text(
    model: str = None,  # Keep for compatibility but ignore
    prompt: str = "",
    max_tokens: int = 512,
    temperature: float = 0.7,
    **kwargs
) -> Optional[str]:
    """Synchronous text generation using Groq API with fallback models"""
    try:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            logger.error("GROQ_API_KEY not found in environment")
            return None
            
        client = Groq(api_key=api_key)
        
        # Fallback models (same as async version)
        models = [
            "llama-3.1-70b-versatile", # Primary: LLaMA 3.1 70B (higher token limit)
            "llama-3.1-8b-instant",    # Fallback 1: LLaMA 3.1 8B
            "llama3-70b-8192",         # Fallback 2: LLaMA 3 70B
            "gemma2-9b-it"             # Fallback 3: Gemma 2 9B
        ]
        
        last_error = None
        for test_model in models:
            try:
                logger.info(f"🔄 Trying sync text generation with {test_model}")
                
                response = client.chat.completions.create(
                    model=test_model,
                    messages=[
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=max_tokens,
                    temperature=temperature
                )
                
                if response.choices and response.choices[0].message:
                    content = response.choices[0].message.content
                    logger.info(f"✅ Sync text generation successful with {test_model}")
                    return content
                    
            except Exception as e:
                logger.warning(f"❌ Model {test_model} failed: {str(e)}")
                last_error = e
                continue
        
        logger.error(f"❌ All models failed for sync text generation")
        return None
        
    except Exception as e:
        logger.error(f"Groq sync_generate_text failed: {e}")
        return None


def sync_chat_completion(
    model: str = None,  # Keep for compatibility but ignore
    messages: List[Dict[str, str]] = None,
    max_tokens: int = 512,
    temperature: float = 0.7,
    **kwargs
) -> Optional[str]:
    """Synchronous chat completion using Groq API with fallback models"""
    try:
        if not messages:
            return None
            
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            logger.error("GROQ_API_KEY not found in environment")
            return None
            
        client = Groq(api_key=api_key)
        
        # Fallback models (same as async version)
        models = [
            "llama-3.1-70b-versatile", # Primary: LLaMA 3.1 70B (higher token limit)
            "llama-3.1-8b-instant",    # Fallback 1: LLaMA 3.1 8B
            "llama3-70b-8192",         # Fallback 2: LLaMA 3 70B
            "gemma2-9b-it"             # Fallback 3: Gemma 2 9B
        ]
        
        last_error = None
        for test_model in models:
            try:
                logger.info(f"🔄 Trying sync chat completion with {test_model}")
                
                response = client.chat.completions.create(
                    model=test_model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature
                )
                
                if response.choices and response.choices[0].message:
                    content = response.choices[0].message.content
                    logger.info(f"✅ Sync chat completion successful with {test_model}")
                    return content
                    
            except Exception as e:
                logger.warning(f"❌ Model {test_model} failed: {str(e)}")
                last_error = e
                continue
        
        logger.error(f"❌ All models failed for sync chat completion")
        return None
        
    except Exception as e:
        logger.error(f"Groq sync_chat_completion failed: {e}")
        return None


def test_groq_connection_sync() -> bool:
    """Test Groq connection synchronously"""
    try:
        result = sync_generate_text(
            prompt="Test connection",
            max_tokens=5,
            temperature=0.1
        )
        return bool(result)
    except Exception as e:
        logger.error(f"Groq connection test failed: {e}")
        return False


async def test_groq_connection() -> bool:
    """Test Groq connection asynchronously"""
    try:
        async with GroqClient() as client:
            return await client.check_connection()
    except Exception as e:
        logger.error(f"Groq async connection test failed: {e}")
        return False