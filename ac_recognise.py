import os
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def check_proof(image_url: str, quest: str, filename: str = ""):
    try:
        prompt = f"""
You are checking if a video/image proves the user completed this Animal Company challenge:

Challenge: {quest}

Reply with only one of these:
- YES
- NO - short reason
"""
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a strict proof checker for Animal Company quests."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=50,
            temperature=0.2
        )

        result = response.choices[0].message.content.strip().upper()

        if result.startswith("YES"):
            return True, "Looks good"
        else:
            reason = result.replace("NO -", "").replace("NO:", "").strip()
            return False, reason if reason else "Doesn't match the challenge"

    except Exception as e:
        print("Proof check error:", e)
        return False, "Could not check the proof"
