import os
from openai import OpenAI

# ============================================================
# OpenAI client
# ============================================================

api_key = os.getenv("OPENAI_API_KEY")

if not api_key:
    raise RuntimeError(
        "OPENAI_API_KEY environment variable is not set."
    )

client = OpenAI(api_key=api_key)


# ============================================================
# Check Animal Company proof
# ============================================================

async def check_proof(
    image_url: str,
    quest: str,
    filename: str = ""
):
    """
    Checks whether an image proves that an Animal Company
    challenge/quest was completed.

    Returns:
        (True, "Looks good")
        or
        (False, "reason")
    """

    try:
        prompt = f"""
You are checking proof for an Animal Company challenge.

Challenge:
{quest}

Your job is to carefully inspect the provided image and determine
whether the image gives sufficient visual evidence that the user
completed the challenge.

Be strict.

Do NOT assume that the challenge was completed if the image does
not clearly show evidence.

The image may contain gameplay footage, screenshots, characters,
objects, locations, UI, or other visual evidence.

Reply with ONLY one of these formats:

YES

or:

NO - short reason

Do not provide anything else.
"""

        # Add filename information if available
        if filename:
            prompt += f"\n\nUploaded filename: {filename}"

        response = client.responses.create(
            model="gpt-4o",
            input=[
                {
                    "role": "system",
                    "content": (
                        "You are a strict visual proof checker "
                        "for Animal Company quests. "
                        "Only approve proof when the image "
                        "provides sufficient visual evidence."
                    ),
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": prompt,
                        },
                        {
                            "type": "input_image",
                            "image_url": image_url,
                        },
                    ],
                },
            ],
            max_output_tokens=50,
        )

        # Get the model's text response
        result = response.output_text.strip()

        if not result:
            return False, "The AI returned an empty response"

        result_upper = result.upper()

        # ====================================================
        # Approved
        # ====================================================

        if result_upper.startswith("YES"):
            return True, "Looks good"

        # ====================================================
        # Rejected
        # ====================================================

        reason = result_upper

        if reason.startswith("NO -"):
            reason = reason[4:].strip()

        elif reason.startswith("NO:"):
            reason = reason[3:].strip()

        elif reason.startswith("NO"):
            reason = reason[2:].strip()

        return (
            False,
            reason if reason else "Doesn't match the challenge"
        )

    except Exception as e:
        print("Proof check error:", repr(e))
        return False, "Could not check the proof"


# ============================================================
# Example
# ============================================================

async def main():
    image_url = "https://example.com/proof.png"

    quest = "Climb to the highest point in the map"

    approved, reason = await check_proof(
        image_url=image_url,
        quest=quest,
        filename="proof.png"
    )

    if approved:
        print("✅ PROOF ACCEPTED")
        print(reason)
    else:
        print("❌ PROOF REJECTED")
        print(reason)


# ============================================================
# Run directly
# ============================================================

if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
