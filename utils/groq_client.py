"""
Groq API client for Mistral 7B integration
Replacement for Ollama client with similar interface
"""

import logging
import os
from typing import List, Dict, Any, Optional
import asyncio
from groq import Groq
import httpx

logger = logging.getLogger(__name__)

class GroqClient:
    """Async client for Groq API with Mistral 7B"""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        if not self.api_key:
            raise ValueError("GROQ_API_KEY environment variable is required")
        
        self.client = Groq(api_key=self.api_key)
        self.model = "llama-3.1-8b-instant"  # Using LLaMA 3.1 8B (similar to Mistral 7B)
        
    async def __aenter__(self):
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass
        
    async def check_connection(self) -> bool:
        """Test connection to Groq API"""
        try:
            # Test with a simple completion
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "user", "content": "Test"}
                ],
                max_tokens=5,
                temperature=0.1
            )
            return bool(response.choices[0].message.content)
        except Exception as e:
            logger.error(f"Groq connection test failed: {e}")
            return False
    
    async def generate_text(
        self,
        prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.7,
        **kwargs
    ) -> Optional[str]:
        """Generate text completion using Groq API"""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "user", "content": prompt}
                ],
                max_tokens=max_tokens,
                temperature=temperature,
                **kwargs
            )
            
            if response.choices and response.choices[0].message:
                return response.choices[0].message.content
            return None
            
        except Exception as e:
            logger.error(f"Groq generate_text failed: {e}")
            return None
    
    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 512,
        temperature: float = 0.7,
        **kwargs
    ) -> Optional[str]:
        """Generate chat completion using Groq API"""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                **kwargs
            )
            
            if response.choices and response.choices[0].message:
                return response.choices[0].message.content
            return None
            
        except Exception as e:
            logger.error(f"Groq chat_completion failed: {e}")
            return None


def sync_generate_text(
    model: str = None,  # Keep for compatibility but ignore
    prompt: str = "",
    max_tokens: int = 512,
    temperature: float = 0.7,
    **kwargs
) -> Optional[str]:
    """Synchronous text generation using Groq API"""
    try:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            logger.error("GROQ_API_KEY not found in environment")
            return None
            
        client = Groq(api_key=api_key)
        
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "user", "content": prompt}
            ],
            max_tokens=max_tokens,
            temperature=temperature
        )
        
        if response.choices and response.choices[0].message:
            return response.choices[0].message.content
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
    """Synchronous chat completion using Groq API"""
    try:
        if not messages:
            return None
            
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            logger.error("GROQ_API_KEY not found in environment")
            return None
            
        client = Groq(api_key=api_key)
        
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature
        )
        
        if response.choices and response.choices[0].message:
            return response.choices[0].message.content
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