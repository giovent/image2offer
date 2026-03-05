"""LangGraph state definitions for OID pipeline execution."""

from __future__ import annotations

from typing import Any, TypedDict, Annotated, Sequence, List
from langgraph.graph.message import add_messages, BaseMessage


class GraphState(TypedDict):
    """State carried between LangGraph nodes."""
    messages: Annotated[Sequence[BaseMessage], add_messages] | None
    warnings: List[str] | None

    image: bytes | None
    image_mime_type: str | None
    offer_country: str | None

    image_check_model_name: str | None
    image_decoding_model_name: str | None
    offer_info_verification_model_name: str | None
    product_enrichment_model_name: str | None
    product_image_search_model_name: str | None
    final_offer_composition_model_name: str | None

    does_it_contain_offer: bool | None
    decoded_offers: List[dict[str, Any]] | None
    enriched_products_info: List[List[dict[str, Any]]] | None
    product_image_urls: List[str] | None

    final_offers_info: List[dict[str, Any]] | None