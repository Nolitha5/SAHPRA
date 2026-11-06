"""Optional local-only bounded Ollama JSON extraction; cannot introduce unsupported citations."""
from __future__ import annotations
import json
import httpx

class OllamaClient:
    def __init__(self, model: str="llama3.1:8b", base_url: str="http://localhost:11434", timeout: float=120):
        # Default is localhost; nonlocal hosts require explicit approval in the team's deployment setup.
        self.model,self.base_url,self.timeout = model,base_url.rstrip("/"),timeout
    def json_completion(self, prompt: str) -> dict:
        with httpx.Client(timeout=self.timeout) as client:
            r = client.post(f"{self.base_url}/api/generate",
                json={"model":self.model,"prompt":prompt,"stream":False,"format":"json",
                      "options":{"temperature":0,"num_predict":512}})
            r.raise_for_status()
            reply = r.json().get("response", "")
            parsed = json.loads(reply)
            if not isinstance(parsed,dict): raise ValueError("Ollama JSON response must be an object")
            return parsed
