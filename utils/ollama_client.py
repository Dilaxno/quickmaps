import requests
import json
import logging
from typing import Optional, Dict, Any, List
import asyncio
import aiohttp

logger = logging.getLogger(__name__)

class OllamaClient:
    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url
        self.session = None
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    def _get_session(self):
        if not self.session:
            raise RuntimeError("OllamaClient must be used as async context manager")
        return self.session
    
    async def check_connection(self) -> bool:
        """Check if Ollama server is running"""
        try:
            session = self._get_session()
            async with session.get(f"{self.base_url}/api/tags") as response:
                return response.status == 200
        except Exception as e:
            logger.error(f"Failed to connect to Ollama: {e}")
            return False
    
    async def list_models(self) -> List[Dict[str, Any]]:
        """List all available models"""
        try:
            session = self._get_session()
            async with session.get(f"{self.base_url}/api/tags") as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('models', [])
                else:
                    logger.error(f"Failed to list models: {response.status}")
                    return []
        except Exception as e:
            logger.error(f"Error listing models: {e}")
            return []
    
    async def pull_model(self, model_name: str) -> bool:
        """Pull a model if it doesn't exist"""
        try:
            session = self._get_session()
            payload = {"name": model_name}
            
            async with session.post(
                f"{self.base_url}/api/pull", 
                json=payload,
                timeout=aiohttp.ClientTimeout(total=300)  # 5 minutes timeout
            ) as response:
                if response.status == 200:
                    # Stream the response to handle progress
                    async for line in response.content:
                        if line:
                            try:
                                progress = json.loads(line.decode())
                                if progress.get('status') == 'success':
                                    logger.info(f"Successfully pulled model: {model_name}")
                                    return True
                                elif 'error' in progress:
                                    logger.error(f"Error pulling model: {progress['error']}")
                                    return False
                            except json.JSONDecodeError:
                                continue
                    return True
                else:
                    logger.error(f"Failed to pull model {model_name}: {response.status}")
                    return False
        except Exception as e:
            logger.error(f"Error pulling model {model_name}: {e}")
            return False
    
    async def generate_text(
        self, 
        model: str, 
        prompt: str, 
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stream: bool = False
    ) -> Optional[str]:
        """Generate text using Ollama model"""
        try:
            session = self._get_session()
            
            payload = {
                "model": model,
                "prompt": prompt,
                "stream": stream,
                "options": {
                    "temperature": temperature,
                }
            }
            
            if system_prompt:
                payload["system"] = system_prompt
            
            if max_tokens:
                payload["options"]["num_predict"] = max_tokens
            
            async with session.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=120)  # 2 minutes timeout
            ) as response:
                if response.status == 200:
                    if stream:
                        # Handle streaming response
                        full_response = ""
                        async for line in response.content:
                            if line:
                                try:
                                    chunk = json.loads(line.decode())
                                    if 'response' in chunk:
                                        full_response += chunk['response']
                                    if chunk.get('done', False):
                                        break
                                except json.JSONDecodeError:
                                    continue
                        return full_response
                    else:
                        # Handle single response
                        data = await response.json()
                        return data.get('response', '')
                else:
                    error_text = await response.text()
                    logger.error(f"Ollama API error {response.status}: {error_text}")
                    return None
        except Exception as e:
            logger.error(f"Error generating text with Ollama: {e}")
            return None
    
    async def chat_completion(
        self, 
        model: str, 
        messages: List[Dict[str, str]], 
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stream: bool = False
    ) -> Optional[str]:
        """Chat completion using Ollama model"""
        try:
            session = self._get_session()
            
            payload = {
                "model": model,
                "messages": messages,
                "stream": stream,
                "options": {
                    "temperature": temperature,
                }
            }
            
            if max_tokens:
                payload["options"]["num_predict"] = max_tokens
            
            async with session.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=120)
            ) as response:
                if response.status == 200:
                    if stream:
                        # Handle streaming response
                        full_response = ""
                        async for line in response.content:
                            if line:
                                try:
                                    chunk = json.loads(line.decode())
                                    if 'message' in chunk and 'content' in chunk['message']:
                                        full_response += chunk['message']['content']
                                    if chunk.get('done', False):
                                        break
                                except json.JSONDecodeError:
                                    continue
                        return full_response
                    else:
                        # Handle single response
                        data = await response.json()
                        return data.get('message', {}).get('content', '')
                else:
                    error_text = await response.text()
                    logger.error(f"Ollama chat API error {response.status}: {error_text}")
                    return None
        except Exception as e:
            logger.error(f"Error with Ollama chat completion: {type(e).__name__}: {str(e)}")
            logger.error(f"Model: {model}, Messages: {len(messages) if messages else 0}, Temperature: {temperature}")
            return None

# Synchronous wrapper functions using hosted API endpoint
def sync_generate_text(
    model: str = "phi3:medium-128k", 
    prompt: str = "", 
    system_prompt: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: Optional[int] = None
) -> Optional[str]:
    """Synchronous wrapper for text generation using hosted API endpoint"""
    try:
        # Use new hosted API endpoint
        api_url = "https://phi3.quickmaps.pro/api/generate"
        
        # Build payload for new API format
        full_prompt = prompt
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n{prompt}"
        
        payload = {
            "model": model,
            "prompt": full_prompt,
            "stream": False
        }
        
        # Add temperature and max_tokens if specified
        if temperature != 0.7:
            payload["temperature"] = temperature
        if max_tokens:
            payload["max_tokens"] = max_tokens
        
        # Make API request
        response = requests.post(
            api_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=300  # 5 minutes timeout for complex prompts
        )
        
        if response.status_code == 200:
            data = response.json()
            response_text = data.get('response', '')
            
            # Clean up the response by removing any training artifacts
            if response_text:
                # Remove common training artifacts that might appear
                lines = response_text.split('\n')
                cleaned_lines = []
                for line in lines:
                    # Skip lines that look like training artifacts
                    if (line.strip().startswith('**Instruction') or 
                        line.strip().startswith('<|user|') or
                        line.strip().startswith('<|assistant|') or
                        line.strip().startswith('<|system|')):
                        break
                    cleaned_lines.append(line)
                
                response_text = '\n'.join(cleaned_lines).strip()
            
            return response_text if response_text else None
        else:
            logger.error(f"API request failed with status {response.status_code}: {response.text}")
            return None
        
    except Exception as e:
        logger.error(f"Error in sync_generate_text: {type(e).__name__}: {str(e)}")
        logger.error(f"Details - Model: {model}, Prompt length: {len(prompt) if prompt else 0}, Temperature: {temperature}, Max tokens: {max_tokens}")
        return None

def sync_chat_completion(
    model: str = "phi3:medium-128k",
    messages: List[Dict[str, str]] = None,
    temperature: float = 0.7,
    max_tokens: Optional[int] = None
) -> Optional[str]:
    """Synchronous wrapper for chat completion using hosted API endpoint"""
    if messages is None:
        messages = []
    
    try:
        # Use new hosted API endpoint (convert chat to generate format)
        api_url = "https://phi3.quickmaps.pro/api/generate"
        
        # Convert messages to a single prompt
        prompt_parts = []
        for message in messages:
            role = message.get('role', 'user')
            content = message.get('content', '')
            if role == 'system':
                prompt_parts.append(f"System: {content}")
            elif role == 'user':
                prompt_parts.append(f"User: {content}")
            elif role == 'assistant':
                prompt_parts.append(f"Assistant: {content}")
        
        full_prompt = "\n\n".join(prompt_parts)
        if full_prompt:
            full_prompt += "\n\nAssistant:"
        
        # Build payload for new API format
        payload = {
            "model": model,
            "prompt": full_prompt,
            "stream": False
        }
        
        # Add temperature and max_tokens if specified
        if temperature != 0.7:
            payload["temperature"] = temperature
        if max_tokens:
            payload["max_tokens"] = max_tokens
        
        # Make API request
        response = requests.post(
            api_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=300  # 5 minutes timeout for complex prompts
        )
        
        if response.status_code == 200:
            data = response.json()
            response_text = data.get('response', '')
            
            # Clean up the response by removing any training artifacts
            if response_text:
                # Remove common training artifacts that might appear
                lines = response_text.split('\n')
                cleaned_lines = []
                for line in lines:
                    # Skip lines that look like training artifacts
                    if (line.strip().startswith('**Instruction') or 
                        line.strip().startswith('<|user|') or
                        line.strip().startswith('<|assistant|') or
                        line.strip().startswith('<|system|')):
                        break
                    cleaned_lines.append(line)
                
                response_text = '\n'.join(cleaned_lines).strip()
            
            return response_text if response_text else None
        else:
            logger.error(f"Chat API request failed with status {response.status_code}: {response.text}")
            return None
        
    except Exception as e:
        logger.error(f"Error in sync_chat_completion: {type(e).__name__}: {str(e)}")
        logger.error(f"Details - Model: {model}, Messages: {len(messages) if messages else 0}, Temperature: {temperature}, Max tokens: {max_tokens}")
        return None

# Test function using hosted API endpoint
def test_ollama_connection_sync():
    """Test hosted Phi3 API connection and model"""
    try:
        logger.info("Testing hosted Phi3 API connection...")
        
        # Test text generation
        logger.info("\nTesting text generation...")
        test_response = sync_generate_text(
            model="phi3:medium-128k",
            prompt="What is 2+2?",
            temperature=0.7,
            max_tokens=50
        )
        
        if test_response:
            logger.info(f"✅ Hosted Phi3 API connection: Connected")
            logger.info(f"Test response: {test_response}")
            
            # Test chat completion
            logger.info("\nTesting chat completion...")
            chat_response = sync_chat_completion(
                model="phi3:medium-128k",
                messages=[{"role": "user", "content": "What is the capital of France?"}],
                temperature=0.5,
                max_tokens=50
            )
            
            if chat_response:
                logger.info(f"Chat response: {chat_response}")
                logger.info("✅ All tests passed - hosted Phi3 API is working correctly")
                return True
            else:
                logger.error("❌ Chat completion test failed")
        else:
            logger.error("❌ Text generation test failed")
            
        return False
        
    except Exception as e:
        logger.error(f"❌ Hosted Phi3 API connection test failed: {e}")
        return False

# Keep async version for backward compatibility
async def test_ollama_connection():
    """Test Ollama connection (async wrapper around sync version)"""
    return test_ollama_connection_sync()

if __name__ == "__main__":
    asyncio.run(test_ollama_connection())