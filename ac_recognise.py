import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def check_proof(file_url: str, quest_text: str, filename: str = "") -> tuple[bool, str]:
    try:
        prompt = f"""
You are verifying proof for an Animal Company quest.

Quest: "{quest_text}"
Filename: {filename}

The player uploaded a file as proof.
Be reasonably lenient. If it seems like they tried to complete the quest, accept it.

Reply in this exact format:
VALID: yes
REASON: short reason

or

VALID: no
REASON: short reason
"""

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=100
        )

        result = response.choices[0].message.content.strip().lower()

        if "valid: yes" in result:
            reason = result.split("reason:")[-1].strip() if "reason:" in result else "Accepted"
            return True, reason
        else:
            reason = result.split("reason:")[-1].strip() if "reason:" in result else "Rejected"
            return False, reason

    except Exception as e:
        return False, f"Error: {str(e)}"
