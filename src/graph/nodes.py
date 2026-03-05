import re
import time
import json
import ast
import math
from typing import Any

import base64

from graph.prompts import *
from graph.state import GraphState
from langchain_core.messages import AIMessage
from openai import Client as LLM_Client

FINAL_OFFERS_RESPONSE_SCHEMA: dict[str, Any] = {
  "type": "object",
  "additionalProperties": False,
  "required": ["final_offers"],
  "properties": {
    "final_offers": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": False,
        "required": [
          "offer_currency",
          "offer_price",
          "original_price",
          "prices_per_quantities",
          "price_per_quantity_units",
          "offer_requirement",
          "country_of_origin",
          "offer_products",
        ],
        "properties": {
          "offer_currency": {"type": "string"},
          "offer_price": {"type": ["number", "null"]},
          "original_price": {"type": ["number", "null"]},
          "prices_per_quantities": {
            "type": ["array", "null"],
            "items": {"type": "number"},
          },
          "price_per_quantity_units": {
            "type": ["array", "null"],
            "items": {"type": "string"},
          },
          "offer_requirement": {
            "type": "array",
            "items": {"type": "string"},
          },
          "country_of_origin": {"type": "string"},
          "offer_products": {
            "type": "array",
            "items": {
              "type": "object",
              "additionalProperties": False,
              "required": [
                "country",
                "brand",
                "name",
                "image_url",
                "barcodes",
                "quantities",
                "units",
                "product_line",
                "category",
                "sub_category",
              ],
              "properties": {
                "country": {"type": "string"},
                "brand": {"type": "string"},
                "name": {"type": "string"},
                "image_url": {"type": "string"},
                "barcodes": {
                  "type": "object",
                  "additionalProperties": False,
                  "required": ["EAN", "UPC", "ASIN"],
                  "properties": {
                    "EAN": {
                      "anyOf": [
                        {"type": "array", "items": {"type": "string"}},
                        {"type": "null"},
                      ]
                    },
                    "UPC": {
                      "anyOf": [
                        {"type": "array", "items": {"type": "string"}},
                        {"type": "null"},
                      ]
                    },
                    "ASIN": {
                      "anyOf": [
                        {"type": "array", "items": {"type": "string"}},
                        {"type": "null"},
                      ]
                    },
                  },
                },
                "quantities": {
                  "type": "array",
                  "items": {"type": "number"},
                  "minItems": 1,
                  "maxItems": 1,
                },
                "units": {
                  "type": "array",
                  "items": {"type": "string"},
                  "minItems": 1,
                  "maxItems": 1,
                },
                "product_line": {"type": ["string", "null"]},
                "category": {"type": ["string", "null"]},
                "sub_category": {"type": ["string", "null"]},
              },
            },
          },
        },
      },
    }
  },
}

FINAL_OFFER_COMPOSITION_MAX_ATTEMPTS = 2

class ImageCheckNode:
  def __init__(self, client: LLM_Client) -> None:
    self.tools = []
    self.client = client
    
  def check_image_offer_node(self, state: GraphState) -> GraphState:
    """Extracts structured offers from image + metadata."""
    print("[🔍 Image Offer Check Node]: checking image to see if it contains an offer.")

    image_bytes = state.get("image")
    if not image_bytes:
      raise ValueError("GraphState['image'] must contain non-empty image bytes.")

    image_mime_type = state.get("image_mime_type")
    if not image_mime_type:
      raise ValueError("GraphState['image_mime_type'] must contain a valid MIME type such as 'image/png'.")

    model_name = state.get("image_check_model_name")
    if not model_name:
      raise ValueError("GraphState['image_check_model_name'] must be set.")
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    data_url = f"data:{image_mime_type};base64,{image_b64}"

    response = self.client.responses.create(
      model=model_name,
      input=[
        {
          "role": "system",
          "content": [
            {"type": "input_text", "text": IMAGE_CHECK_SYSTEM_PROMPT},
          ],
        },
        {
          "role": "user",
          "content": [
            {"type": "input_text", "text": IMAGE_CHECK_USER_PROMPT},
            {
              "type": "input_image",
              "image_url": data_url,
              "detail": "auto",
            },
          ],
        },
      ],
    )
    reply_content = response.output_text.strip()
    if reply_content not in {"True", "False"}:
      raise ValueError(f"Expected vision model to return 'True' or 'False', got: {reply_content!r}")

    print(f"[🔍 Image Offer Check Node] Result: {reply_content}")
    state["messages"] = list(state.get("messages", [])) + [AIMessage(content=reply_content)] # type: ignore
    return state

class OfferInfoExtractionNode:
  def __init__(self, client: LLM_Client, save_result_in_txt:bool = False) -> None:
    self.tools = []
    self.client = client
    self.save_result_in_txt = save_result_in_txt
    
  def extract_offer_info_node(self, state: GraphState) -> GraphState:
    """"Extracts structured offers from image + metadata."""
    print("[🔎 Offer Info Extraction Node]: extracting offer info.")

    image_bytes = state.get("image")
    if not image_bytes:
      raise ValueError("GraphState['image'] must contain non-empty image bytes.")

    image_mime_type = state.get("image_mime_type")
    if not image_mime_type:
      raise ValueError("GraphState['image_mime_type'] must contain a valid MIME type such as 'image/png'.")

    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    data_url = f"data:{image_mime_type};base64,{image_b64}"

    model_name = state.get("image_decoding_model_name")
    if not model_name:
      raise ValueError("GraphState['image_decoding_model_name'] must be set.")
    
    offer_country = state.get("offer_country", "Unknown")

    extraction_system_prompt = OFFER_INFO_EXTRACTION_SYSTEM_PROMPT
    extraction_user_prompt = OFFER_INFO_EXTRACTION_USER_PROMPT.format(offer_country=offer_country)
    response = self.client.responses.create(
      model=model_name,
      input=[
        {
          "role": "system",
          "content": [
            {"type": "input_text", "text": extraction_system_prompt},
          ],
        },
        {
          "role": "user",
          "content": [
            {"type": "input_text", "text": extraction_user_prompt},
            {
              "type": "input_image",
              "image_url": data_url,
              "detail": "auto",
            },
          ],
        },
      ],
    )

    reply_content = self._normalize_offer_reply(response.output_text)

    try:
      offers = self._parse_offers(reply_content)
    except (json.JSONDecodeError, ValueError, SyntaxError):
      warnings = list(state.get("warnings", []) or [])
      warnings.append("Offer info extraction output was not parseable.")
      state["warnings"] = warnings
      offers = []
    state["decoded_offers"] = offers   

    if self.save_result_in_txt:
      self.save_to_txt(offers)
    
    total_products = sum(len(offer.get("offer_products_bundle", [])) for offer in offers)
    print(f"[🔎 Offer Info Extraction Node] Offers decoded: {len(offers)}. Total products: {total_products}")
    state["messages"] = list(state.get("messages", [])) + [AIMessage(content=reply_content)] # pyright: ignore[reportArgumentType]
    return state

  def _normalize_offer_reply(self, reply_content: str) -> str:
    normalized = reply_content.strip("```").strip("json").strip()
    normalized = re.sub(r":\s*None\b", ": null", normalized)
    normalized = re.sub(r'([{,])\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:', r'\1"\2":', normalized)
    return normalized

  def _parse_offers(self, reply_content: str) -> list[dict[str, Any]]:
    try:
      parsed_offers = json.loads(reply_content)
    except json.JSONDecodeError:
      python_like = reply_content.replace("null", "None")
      parsed_offers = ast.literal_eval(python_like)

    if not isinstance(parsed_offers, list):
      raise ValueError("Decoded offers must be a list.")
    if not all(isinstance(offer, dict) for offer in parsed_offers):
      raise ValueError("Decoded offers list must contain dict items.")
    return parsed_offers
  
  def save_to_txt(self, offers: list[dict], txt_filename: str = ""):
    if txt_filename == "":
      txt_filename = str(int(time.time())) + ".txt"
    try:
        with open(txt_filename, "w", encoding="utf-8") as file:
            # Pretty-print JSON with indentation
            file.write(json.dumps(offers, indent=4, ensure_ascii=False))
        print(f"Offers decoded successfully written to '{txt_filename}'")
    except (OSError, IOError) as e:
        print(f"Error writing to file: {e}")

class ProductEnrichmentNode:
  def __init__(self, client: LLM_Client) -> None:
    self.tools = []
    self.client = client
    
  def enrich_offer_info_node(self, state: GraphState) -> GraphState:
    print("[✨ Product Enrichment Node]: starting enrichment of products info.")

    image_bytes = state.get("image")
    if not image_bytes:
      raise ValueError("GraphState['image'] must contain non-empty image bytes.")

    image_mime_type = state.get("image_mime_type")
    if not image_mime_type:
      raise ValueError("GraphState['image_mime_type'] must contain a valid MIME type such as 'image/png'.")

    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    data_url = f"data:{image_mime_type};base64,{image_b64}"

    model_name = state.get("product_enrichment_model_name")
    if not model_name:
      raise ValueError("GraphState['product_enrichment_model_name'] must be set.")
    
    offer_country = state.get("offer_country", "Unkown")
    
    decoded_offers = state.get("decoded_offers")
    if not decoded_offers:
      raise ValueError("GraphState['decoded_offers'] must contain the list of decoded offers to enrich.")

    enriched_info = [] # Must contain a list of products for each offer
    for offer in decoded_offers:
      offer_enriched_info = [] # The info enriched of THIS offer products (usually just one, but in some cases there could be multiple products in the same offer)
      offer_products = offer.get("offer_products_bundle", [])
      if offer_products == []:
        enriched_info.append(offer_enriched_info)
        continue
      for offer_product_n, offer_product in enumerate(offer_products):
        offer_reference_price = offer["offer_price"] if offer.get("offer_price") is not None else "Unknown"
        response = self.client.responses.create(
          model=model_name,
          tools=[{"type": "web_search"}],  # Enable web search
          tool_choice="auto",  # Let the model decide when to search
          max_output_tokens=4096,
          input=[
            {
              "role": "system",
              "content": [
                {"type": "input_text", "text": PRODUCT_ENRICHMENT_SYSTEM_PROMPT},
              ],
            },
            {
              "role": "user",
              "content": [
                {"type": "input_text", "text": PRODUCT_ENRICHMENT_USER_PROMPT.format(origin_country=offer_country,
                                                                                      reference_price=offer_reference_price,
                                                                                      product_info=offer_product)},
                # {"type": "input_image", "image_url": data_url, "detail": "auto",}, # I decided not to use the image in the prompt, since it might be counterproductive
              ],
            },
          ]
          )
        reply_content = response.output_text.strip("```").strip("json").strip()
        reply_content = re.sub(r"\bTrue\b", "true", reply_content)
        reply_content = re.sub(r"\bFalse\b", "false", reply_content)
        reply_content = re.sub(r'\(true,', "[true,", reply_content)
        reply_content = re.sub(r'\(false,', "[false,", reply_content)
        reply_content = re.sub(r'\)\s*$', "]", reply_content)
        reply_content = re.sub(r'^\s*\(', "[", reply_content)
        reply_content = re.sub(r'\'', '"', reply_content)
        reply_content = re.sub(r'([{,\[])\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:', r'\1"\2":', reply_content)
        try:
          enriched_product = json.loads(reply_content)
        except json.JSONDecodeError:
          enriched_product = [False, None]
          print(f"[✨ Product Enrichment Node]: Error parsing JSON: {reply_content}")
        enrichement_successful = enriched_product[0] if enriched_product else False
        if enrichement_successful and len(enriched_product) > 1 and enriched_product[1]:
          offer_enriched_info.append(enriched_product[1])
        state["messages"] = list(state.get("messages", [])) + [AIMessage(content=reply_content)] # pyright: ignore[reportArgumentType]
      enriched_info.append(offer_enriched_info) # pyright: ignore[reportArgumentType]
    state["enriched_products_info"] = enriched_info # pyright: ignore[reportArgumentType]
    print(f"[✨ Product Enrichment Node] Result enriched: {len(enriched_info)} offers. Total products: {sum(len(offer) for offer in enriched_info)}") # pyright: ignore[reportArgumentType]
    return state # pyright: ignore[reportArgumentType]

class ProductImageSearchNode:
  def __init__(self, client: LLM_Client) -> None:
    self.tools = []
    self.client = client
    
  def search_product_image_node(self, state: GraphState) -> GraphState:
    print("[🖼️ Product Image Search Node]: Starting search for product image.")
    
    image_bytes = state.get("image")
    if not image_bytes:
      raise ValueError("GraphState['image'] must contain non-empty image bytes.")

    image_mime_type = state.get("image_mime_type")
    if not image_mime_type:
      raise ValueError("GraphState['image_mime_type'] must contain a valid MIME type such as 'image/png'.")

    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    data_url = f"data:{image_mime_type};base64,{image_b64}"
    
    model_name = state.get("product_image_search_model_name")
    if not model_name:
      raise ValueError("GraphState['product_image_search_model_name'] must be set.")
    
    decoded_products_info = state.get("decoded_offers")
    if not decoded_products_info:
      raise ValueError("GraphState['decoded_offers'] must contain the list of decoded products info to search for images.")

    enriched_products_info = state.get("enriched_products_info")
    if not enriched_products_info:
      raise ValueError("GraphState['enriched_products_info'] must contain the list of enriched products info to search for images.")

    offer_country = state.get("offer_country", "Unkown")
    product_image_urls = []

    response = self.client.responses.create(
      model=model_name,
      tools=[{"type": "web_search"}],  # Enable web search
      tool_choice="auto",  # Let the model decide when to search
      max_output_tokens=4096,
      input=[
        {
          "role": "system",
          "content": [
            {"type": "input_text", "text": PRODUCT_IMAGE_SEARCH_SYSTEM_PROMPT},
          ],
        },
        {
          "role": "user",
          "content": [
            {"type": "input_text", "text": PRODUCT_IMAGE_SEARCH_USER_PROMPT.format(country_of_origin=offer_country, agent_1_info=decoded_products_info, agent_2_info=enriched_products_info)},
            {"type": "input_image", "image_url": data_url, "detail": "auto",}, # I decided not to use the image in the prompt, since it might be counterproductive
          ],
        },
      ],
    ) 

    reply_content = response.output_text.strip()
    reply_content = re.sub(r"\bTrue\b", "true", reply_content)
    reply_content = re.sub(r"\bFalse\b", "false", reply_content)
    reply_content = re.sub(r'\(true,', "[true,", reply_content)
    reply_content = re.sub(r'\(false,', "[false,", reply_content)
    reply_content = re.sub(r'\)\s*$', "]", reply_content)
    reply_content = re.sub(r'^\s*\(', "[", reply_content)
    reply_content = re.sub(r'\'', '"', reply_content)
    reply_content = re.sub(r'([{,\[])\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:', r'\1"\2":', reply_content)
    try:
      product_image_urls = json.loads(reply_content)
    except json.JSONDecodeError:
      product_image_urls = []
      print(f"[🖼️ Product Image Search Node]: Error parsing JSON: {reply_content}")
    
    state["product_image_urls"] = product_image_urls
    print(f"[🖼️ Product Image Search Node] Finished.")
    return state

class FinalOfferCompositionNode:
  def __init__(self, client: LLM_Client) -> None:
    self.tools = []
    self.client = client
    
  def compose_final_offer_node(self, state: GraphState) -> GraphState:
    print("[✅ Final Offer Composition Node]: organizing and composing final offers information.")

    model_name = state.get("final_offer_composition_model_name")
    if not model_name:
      raise ValueError("GraphState['final_offer_composition_model_name'] must be set.")

    decoded_offers = state.get("decoded_offers")
    if not decoded_offers:
      raise ValueError("GraphState['decoded_offers'] must contain the list of decoded offers to compose the final offer.")

    enriched_products_info = state.get("enriched_products_info")
    if not enriched_products_info:
      raise ValueError("GraphState['enriched_products_info'] must contain the list of enriched products info to compose the final offer.")

    product_image_urls = state.get("product_image_urls")
    if not product_image_urls:
      product_image_urls = []

    offer_country = state.get("offer_country", "Unkown")

    base_user_prompt = FINAL_OFFER_COMPOSITION_USER_PROMPT.format(
      agent_2_info=decoded_offers,
      agent_3_info=enriched_products_info,
      agent_4_info=product_image_urls,
      offer_country=offer_country,
    )
    final_offers_info: list[dict[str, Any]] = []
    parse_successful = False
    last_reply_content = ""
    validation_error = ""
    for attempt in range(FINAL_OFFER_COMPOSITION_MAX_ATTEMPTS):
      retry_instruction = ""
      if attempt > 0:
        retry_instruction = (
          "\n\nRetry reason: your previous answer failed parsing/validation. "
          f"{validation_error} "
          "Return only the JSON payload that matches the strict schema."
        )
      response = self.client.responses.create(
        model=model_name,
        tools=[{"type": "web_search"}],  # Enable web search
        tool_choice="auto",  # Let the model decide when to search
        text={
          "format": {
            "type": "json_schema",
            "name": "final_offers_info",
            "schema": FINAL_OFFERS_RESPONSE_SCHEMA,
            "strict": True,
          }
        },
        input=[
          {
            "role": "system",
            "content": [
              {"type": "input_text", "text": FINAL_OFFER_COMPOSITION_SYSTEM_PROMPT},
            ],
          },
          {
            "role": "user",
            "content": [
              {"type": "input_text", "text": base_user_prompt + retry_instruction},
            ],
          },
        ],
      )
      last_reply_content = response.output_text.strip()
      parsed_final_offers = self._parse_final_offers_response(last_reply_content)
      if parsed_final_offers is not None:
        try:
          final_offers_info = self._normalize_single_quantity_per_product(parsed_final_offers)
          parse_successful = True
          break
        except ValueError as exc:
          validation_error = str(exc)
      else:
        validation_error = "JSON payload could not be parsed."
      print(f"[✅ Final Offer Composition Node]: schema JSON parsing failed, retry {attempt + 1}/{FINAL_OFFER_COMPOSITION_MAX_ATTEMPTS}.")

    if parse_successful:
      state["final_offers_info"] = final_offers_info
    else:
      warnings = list(state.get("warnings", []) or [])
      warnings.append("Final offer composition failed schema JSON parsing. Returned empty list.")
      state["warnings"] = warnings
      state["final_offers_info"] = []
      print(f"[✅ Final Offer Composition Node]: Error parsing JSON after retries. Last reply: {last_reply_content!r}")
    print(f"[✅ Final Offer Composition Node] Final offers are composed successfully.")
    return state

  def _normalize_single_quantity_per_product(self, offers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for offer_idx, offer in enumerate(offers):
      offer_products = offer.get("offer_products")
      if not isinstance(offer_products, list):
        raise ValueError(f"Offer {offer_idx} is missing a valid offer_products list.")
      for product_idx, product in enumerate(offer_products):
        if not isinstance(product, dict):
          raise ValueError(f"Offer {offer_idx}, product {product_idx} is not an object.")
        quantities = product.get("quantities")
        units = product.get("units")
        if not isinstance(quantities, list) or not isinstance(units, list):
          raise ValueError(f"Offer {offer_idx}, product {product_idx} must contain list quantities/units.")
        if len(quantities) == 0 or len(units) == 0 or len(quantities) != len(units):
          raise ValueError(f"Offer {offer_idx}, product {product_idx} has invalid quantities/units length.")

        grouped_totals: dict[str, float] = {}
        display_units: dict[str, str] = {}
        for quantity, unit in zip(quantities, units):
          if not isinstance(quantity, (int, float)):
            raise ValueError(f"Offer {offer_idx}, product {product_idx} has non-numeric quantity.")
          if not isinstance(unit, str) or unit.strip() == "":
            raise ValueError(f"Offer {offer_idx}, product {product_idx} has empty unit.")
          canonical_key, canonical_display, multiplier = self._canonicalize_unit(unit)
          grouped_totals[canonical_key] = grouped_totals.get(canonical_key, 0.0) + (float(quantity) * multiplier)
          display_units[canonical_key] = canonical_display

        if len(grouped_totals) != 1:
          raise ValueError(
            f"Offer {offer_idx}, product {product_idx} has incompatible units {list(display_units.values())}."
          )

        normalized_key = next(iter(grouped_totals))
        total_quantity = grouped_totals[normalized_key]
        normalized_quantity: float | int
        if math.isfinite(total_quantity) and total_quantity.is_integer():
          normalized_quantity = int(total_quantity)
        else:
          normalized_quantity = round(total_quantity, 6)
        product["quantities"] = [normalized_quantity]
        product["units"] = [display_units[normalized_key]]
    return offers

  def _canonicalize_unit(self, unit: str) -> tuple[str, str, float]:
    cleaned = unit.strip()
    lowered = cleaned.casefold()
    direct_map: dict[str, tuple[str, str, float]] = {
      "g": ("mass_g", "g", 1.0),
      "gram": ("mass_g", "g", 1.0),
      "grams": ("mass_g", "g", 1.0),
      "gr": ("mass_g", "g", 1.0),
      "kg": ("mass_g", "g", 1000.0),
      "kilogram": ("mass_g", "g", 1000.0),
      "kilograms": ("mass_g", "g", 1000.0),
      "ml": ("volume_ml", "ml", 1.0),
      "milliliter": ("volume_ml", "ml", 1.0),
      "milliliters": ("volume_ml", "ml", 1.0),
      "millilitre": ("volume_ml", "ml", 1.0),
      "millilitres": ("volume_ml", "ml", 1.0),
      "l": ("volume_ml", "ml", 1000.0),
      "lt": ("volume_ml", "ml", 1000.0),
      "liter": ("volume_ml", "ml", 1000.0),
      "liters": ("volume_ml", "ml", 1000.0),
      "litre": ("volume_ml", "ml", 1000.0),
      "litres": ("volume_ml", "ml", 1000.0),
      "bottle": ("count_bottle", "bottle", 1.0),
      "bottles": ("count_bottle", "bottle", 1.0),
      "flacone": ("count_bottle", "flacone", 1.0),
      "flaconi": ("count_bottle", "flacone", 1.0),
      "piece": ("count_piece", "piece", 1.0),
      "pieces": ("count_piece", "piece", 1.0),
      "pc": ("count_piece", "piece", 1.0),
      "pcs": ("count_piece", "piece", 1.0),
      "pack": ("count_pack", "pack", 1.0),
      "packs": ("count_pack", "pack", 1.0),
      "組": ("count_pack", "組", 1.0),
      "個": ("count_piece", "個", 1.0),
      "條": ("count_piece", "條", 1.0),
      "条": ("count_piece", "條", 1.0),
    }
    if lowered in direct_map:
      return direct_map[lowered]
    return (f"raw:{lowered}", cleaned, 1.0)

  def _parse_final_offers_response(self, reply_content: str) -> list[dict[str, Any]] | None:
    try:
      parsed_payload = json.loads(reply_content)
    except json.JSONDecodeError:
      return None

    if isinstance(parsed_payload, list):
      if all(isinstance(offer, dict) for offer in parsed_payload):
        return parsed_payload
      return None

    if isinstance(parsed_payload, dict):
      offers = parsed_payload.get("final_offers")
      if isinstance(offers, list) and all(isinstance(offer, dict) for offer in offers):
        return offers

    return None
