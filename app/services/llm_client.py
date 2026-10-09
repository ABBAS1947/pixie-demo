"""Review helpers: one provider retry owner, strict complete JSON results."""
import json
from app.services.llm_registry import get_provider

async def llm_chat(messages:list[dict],*,temperature:float=0.7,max_tokens:int|None=None,json_mode:bool=False)->str:
    result=await get_provider('extraction').complete(messages,temperature=temperature,max_tokens=max_tokens,json_mode=json_mode)
    if result.get('finish_reason')=='length':raise ValueError('Provider output truncated')
    return result['content']

async def llm_json(messages:list[dict],*,temperature:float=0.3,max_tokens:int|None=None)->dict:
    result=await get_provider('extraction').complete(messages,temperature=temperature,max_tokens=max_tokens,json_mode=True)
    if result.get('finish_reason')=='length':raise ValueError('Provider output truncated')
    content=result['content'].strip()
    if content.startswith('```'):
        lines=content.splitlines()[1:]
        if lines and lines[-1].strip()=='```':lines.pop()
        content='\n'.join(lines)
    value=json.loads(content)
    if not isinstance(value,dict):raise ValueError('Provider result must be an object')
    return value
