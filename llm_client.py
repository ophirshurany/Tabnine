
import json
import requests
from typing import Optional, Dict, Any, List
from config import settings
import logging

# Configure logging
logger = logging.getLogger(__name__)

class LLMClient:
    """
    Client for interacting with LLMs via OpenRouter.
    """
    
    BASE_URL = "https://openrouter.ai/api/v1"
    
    @staticmethod
    def call_chat(
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.0,
        max_tokens: int = 4000,
        top_p: float = 1.0,
        frequency_penalty: float = 0.0,
        presence_penalty: float = 0.0,
        response_format: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Call OpenRouter chat completions API.
        """
        headers = {
            "Authorization": f"Bearer {settings.openrouter_api_key}",
            "HTTP-Referer": "https://antigravity.dev", # Optional
            "X-Title": "Antigravity Agent", # Optional
            "Content-Type": "application/json"
        }
        
        data = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "top_p": top_p,
            "frequency_penalty": frequency_penalty,
            "presence_penalty": presence_penalty
        }
        
        if response_format:
            data["response_format"] = response_format
        
        url = f"{LLMClient.BASE_URL}/chat/completions"
        
        if settings.verbose:
            print(f"Calling OpenRouter model={model}")
            
        try:
            response = requests.post(url, headers=headers, json=data, timeout=60)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 400:
                print(f"LLM 400 Error: {e.response.text}")
            raise e
        except Exception as e:
            print(f"Error calling LLM: {e}")
            raise e

    @staticmethod
    def generate_json(
        model: str,
        prompt: str,
        temperature: float = 0.0
    ) -> Dict[str, Any]:
        """
        Generate a JSON response from the LLM.
        """
        messages = [{"role": "user", "content": prompt}]
        
        # Use config settings for defaults, but allow override via params if needed
        # (Using specific params here for consistency with original judges.py)
        response = LLMClient.call_chat(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=settings.llm_max_tokens, 
            top_p=settings.llm_top_p,
            frequency_penalty=settings.llm_frequency_penalty,
            presence_penalty=settings.llm_presence_penalty,
            response_format={"type": "json_object"}
        )
        
        content = response['choices'][0]['message']['content']
        # Clean up potential markdown fences
        clean_content = content.replace("```json", "").replace("```", "").strip()
        return json.loads(clean_content)

    @staticmethod
    def generate_text(
        model: str,
        prompt: str,
        temperature: float = 0.0
    ) -> str:
        """
        Generate a text response from the LLM.
        """
        messages = [{"role": "user", "content": prompt}]
        
        response = LLMClient.call_chat(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=2000, # Default for code generation?
            top_p=1.0
        )
        
        return response['choices'][0]['message']['content']

def generate_model_output(
    original_file: str,
    user_prompt: str,
    model_name: str
) -> str:
    """
    Generate the 'model_output' (suggested code change) using an LLM.
    
    This simulates the 'Code Model' in the system.
    """
    system_prompt = """You are a coding assistant. 
Your task is to generate the code change based on the user's request.
You must output ONLY the code block that should be applied. 
Do not include explanation, thinking, or markdown fences around the code unless requested.
Just raw python code.
"""
    
    user_msg = f"""
Original File:
{original_file}

Request: {user_prompt}

Provide the code snippet that should replace the relevant part (or the whole file if needed) to satisfy the request. 
The format should be a valid python function or code block that can be swapped in.
"""
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_msg}
    ]
    
    try:
        response = LLMClient.call_chat(
            model=model_name,
            messages=messages,
            temperature=0.2, # Low temp for code
            max_tokens=2000
        )
        content = response['choices'][0]['message']['content']
        
        # Remove markdown fences if present (models love adding them)
        if content.startswith("```python"):
            content = content[len("```python"):].strip()
        elif content.startswith("```"):
            content = content[len("```"):].strip()
        
        if content.endswith("```"):
            content = content[:-3].strip()
            
        return content
    except Exception as e:
        print(f"Failed to generate model output: {e}")
        return ""
