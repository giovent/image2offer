from email.mime import image
import os

from typing import List

from openai import Client as LLM_Client
from graph.state import GraphState

from graph.nodes import ProductEnrichmentNode

class ProductInfoEnrichmentEval():
    """Eval to check if the result generated from the individual offer n node is correct."""
    def __init__(self, client: LLM_Client, model_name: str) -> None:
        self.client = client
        self.model_name = model_name
        self.node = ProductEnrichmentNode(client=client)

    def evaluate(self) -> list[float]:
        """Returns the percertage of correct responses
        
        Returns:
            list[float]: [success_rate, barcode_success_rate]
        """

        offers = []

        for f in os.listdir(os.path.join(os.path.dirname(__file__), "Input product info")):
            offers_filename = os.path.join(os.path.dirname(__file__), "Input product info", f)
            if os.path.isfile(offers_filename):
                # read the content of the file and use eval to decode it from str
                with open(offers_filename, "r", encoding="utf-8") as txt_file:
                    content = txt_file.read().strip().replace("null","None")
                    offer_country = f.split("_")[0]
                    offers.append((eval(content), offer_country))

        total_products = 0
        generally_enriched_products = 0
        barcode_enriched_products = 0
        for offer_set, offer_country in offers:
            state = GraphState(
                decoded_offers = offer_set,
                offer_info_verification_model_name=None,
                image_enrichment_model_name=self.model_name,
                offer_country=offer_country
            ) # type: ignore
            result_state = self.node.enrich_offer_info_node(state)
            offer_set_products = sum(1 for offer in offer_set for products in offer["offer_products_bundle"])
            total_products += offer_set_products
            generally_enriched = sum(1 for products in result_state["enriched_products_info"] for product in products if product is not [] and product is not None) # type: ignore
            generally_enriched_products += generally_enriched
            with_barcode = sum(1 for products in result_state["enriched_products_info"] for product in products if "barcodes" in product.keys() and len(product["barcodes"])>0) # type: ignore
            barcode_enriched_products += with_barcode

        success_rate = generally_enriched_products/total_products
        barcode_success_rate = barcode_enriched_products/generally_enriched_products
        print(f"Enrichment eval: Products: {total_products}. Enriched: {generally_enriched_products}. With barcode: {barcode_enriched_products}")
        print(f"Success rate: {success_rate}. Barcode success rate: {barcode_success_rate}")
        
        return [success_rate, barcode_success_rate]