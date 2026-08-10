import os
import tempfile
import subprocess
import base64
import aiohttp
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def check_proof(video_url: str, quest_text: str) -> tuple[bool, str]:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(video_url) as resp:
                if resp.status != 200:
                    return False, "Could not download the video."
                video_data = await resp.read()

        with tempfile.TemporaryDirectory() as tmp:
            video_path = os.path.join(tmp, "proof.mp4")
            with open(video_path, "wb") as f:
                f.write(video_data)

            frames = []
            for i, timestamp in enumerate(["00:00:01", "00:00:04", "00:00:07"]):
                frame_path = os.path.join(tmp, f"frame_{i}.jpg")
                cmd = [
                    "ffmpeg", "-y", "-ss", timestamp, "-i", video_path,
                    "-frames:v", "1", "-q:v", "2", frame_path
                ]
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if os.path.exists(frame_path):
                    frames.append(frame_path)

            if not frames:
                return False, "Could not extract frames from the video."

            content = [{
                "type": "text",
                "text": f"""You are verifying proof for an Animal Company VR quest.

Quest: "{quest_text}"

Look at the frames. Decide if this looks like a real attempt at completing the quest in Animal Company.

Reply in this exact format:
VALID: yes
REASON: short reason

or

VALID: no
REASON: short reason"""
            }]

            for frame in frames:
                with open(frame, "rb") as img:
                    b64 = base64.b64encode(img.read()).decode("utf-8")
                content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{b64}"}
                })

            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": content}],
                max_tokens=150
            )

            result = response.choices[0].message.content.strip().lower()

            if "valid: yes" in result:
                reason = result.split("reason:")[-1].strip() if "reason:" in result else "Looks valid"
                return True, reason
            else:
                reason = result.split("reason:")[-1].strip() if "reason:" in result else "Does not look valid"
                return False, reason

    except Exception as e:
        return False, f"Error: {str(e)}"
