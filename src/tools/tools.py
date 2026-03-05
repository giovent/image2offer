"""Tools used by graph nodes."""

from __future__ import annotations

import base64
import json
from typing import Any

from openai import Client as LLM_Client

from tools.prompts import VERIFY_INFO_SYSTEM_PROMPT, VERIFY_INFO_USER_PROMPT


def verify_info(
    extracted_offers: list[dict[str, Any]] | dict[str, Any] | str,
    offer_country: str | None,
    image_bytes: bytes,
    image_mime_type: str,
    client: LLM_Client,
    model_name: str,
) -> str:
    """An AI tool that checks extracted offers against the source image and returns plain-text feedback."""
    if not image_bytes:
        raise ValueError("verify_info requires non-empty image_bytes.")
    if not image_mime_type:
        raise ValueError("verify_info requires image_mime_type.")
    if not model_name:
        raise ValueError("verify_info requires model_name.")

    if isinstance(extracted_offers, str):
        extracted_offers_text = extracted_offers
    else:
        extracted_offers_text = json.dumps(extracted_offers, ensure_ascii=False)
    offer_country_text = offer_country or "Unknown"

    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    data_url = f"data:{image_mime_type};base64,{image_b64}"
    print(f"[🔧 Verify Info Tool] Starting analysis")
    response = client.responses.create(
        model=model_name,
        input=[
            {
                "role": "system",
                "content": [
                    {"type": "input_text", "text": VERIFY_INFO_SYSTEM_PROMPT},
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": VERIFY_INFO_USER_PROMPT.format(
                            offer_country=offer_country_text,
                            extracted_offers=extracted_offers_text,
                        ),
                    },
                    {
                        "type": "input_image",
                        "image_url": data_url,
                        "detail": "auto",
                    },
                ],
            },
        ],
    )

    feedback = response.output_text.strip()
    print(f"[🔧 Verify Info Tool] Result: {feedback}")
    if not feedback:
        return "Verification failed: empty feedback."
    return feedback
