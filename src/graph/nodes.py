import re
import time
import json

import base64

from graph.prompts import *
from graph.state import GraphState
from langchain_core.messages import AIMessage
from openai import Client as LLM_Client


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

    response = self.client.responses.create(
      model=model_name,
      input=[
        {
          "role": "system",
          "content": [
            {"type": "input_text", "text": OFFER_INFO_EXTRACTION_SYSTEM_PROMPT},
          ],
        },
        {
          "role": "user",
          "content": [
            {"type": "input_text", "text": OFFER_INFO_EXTRACTION_USER_PROMPT.format(offer_country=offer_country)},
            {
              "type": "input_image",
              "image_url": data_url,
              "detail": "auto",
            },
          ],
        },
      ],
    )
    reply_content = response.output_text.strip("```").strip("json").strip()
    reply_content = re.sub(r":\s*None\b", ": null", reply_content)
    reply_content = re.sub(r'([{,])\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:', r'\1"\2":', reply_content)
    try:
      offers = json.loads(reply_content)
    except json.JSONDecodeError:
      reply_content = reply_content.replace("null", "None")
      offers = eval(reply_content) # Convert the string representation of the list of dicts into an actual list of dicts
    state["decoded_offers"] = offers   

    if self.save_result_in_txt:
      self.save_to_txt(offers)
    
    print(f"[🔎 Offer Info Extraction Node] Offers decoded: {len(offers)}. Total products: {sum(len(offer["offer_products_bundle"]) for offer in offers)}")
    state["messages"] = list(state.get("messages", [])) + [AIMessage(content=reply_content)] # pyright: ignore[reportArgumentType]
    return state
  
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
    print(f"[🖼️ Product Image Search Node] Result: {product_image_urls}")
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

    final_offers_info = []
    response = self.client.responses.create(
      model=model_name,
      tools=[{"type": "web_search"}],  # Enable web search
      tool_choice="auto",  # Let the model decide when to search
      max_output_tokens=4096,
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
            {"type": "input_text", "text": FINAL_OFFER_COMPOSITION_USER_PROMPT.format(agent_2_info=state.get("decoded_offers"), agent_3_info=state.get("enriched_products_info"), agent_4_info=state.get("product_image_urls"))},
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
      final_offers_info = json.loads(reply_content)
    except json.JSONDecodeError:
      final_offers_info = []
      print(f"[✅ Final Offer Composition Node]: Error parsing JSON: {reply_content}")
    state["final_offers_info"] = final_offers_info
    print(f"[✅ Final Offer Composition Node] Result: {final_offers_info}")
    return state
