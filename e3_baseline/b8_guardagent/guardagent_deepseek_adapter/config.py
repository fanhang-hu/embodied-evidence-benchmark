import _bootstrap  # Workspace paths and historical cross-script imports.
import os

def model_config(model):
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        raise RuntimeError("DEEPSEEK_API_KEY missing")

    base_url = os.environ.get(
        "DEEPSEEK_BASE_URL", "https://api.deepseek.com"
    )
    if not base_url.startswith("https://"):
        raise ValueError("HTTPS endpoint required")

    return {
        "model": model,
        "api_key": key,
        "base_url": base_url,
    }


def llm_config_list(seed, config_list):
    llm_config_list = {
        "functions": [
            {
                "name": "python",
                "description": "run the entire code and return the execution result. Only generate the code.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "cell": {
                            "type": "string",
                            "description": "Valid Python code to execute.",
                        }
                    },
                    "required": ["cell"],
                },
            },
        ],
        "config_list": config_list,
        "timeout": 120,
        "cache_seed": seed,
        "temperature": 0,
    }
    return llm_config_list