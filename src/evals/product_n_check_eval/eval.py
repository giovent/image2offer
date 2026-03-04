from email.mime import image
import os

from typing import List

from openai import Client as LLM_Client
from graph.state import GraphState

from graph.nodes import OfferInfoExtractionNode

class IndividualOfferNEval():
    """Eval to check if the result generated from the individual offer n node is correct."""
    def __init__(self, client: LLM_Client, model_name: str, save_offers_to_txt: bool = False) -> None:
        self.client = client
        self.model_name = model_name
        self.node = OfferInfoExtractionNode(client=client, save_result_in_txt=save_offers_to_txt)

    def evaluate(self) -> float:
        """Returns the percertage of correct responses
        
        Returns:
            float: success_rate
        """

        images = []

        for f in os.listdir(os.path.join(os.path.dirname(__file__), "Images")):
            image_path = os.path.join(os.path.dirname(__file__), "Images", f)
            if os.path.isfile(image_path):
                with open(image_path, "rb") as img_file:
                    image_bytes = img_file.read()
                    number_of_offers = int(f.strip(".png")[-1])
                    offer_country = f.split("_")[2] # Assuming the filename format is "ex_Country_n.png", e.g. "e1_italy_3.png"
                    images.append((f, image_bytes, number_of_offers, offer_country))
        
        correct_results = 0
        total_images = 0
        for f, image, number_of_offers, offer_country in images:
            total_images += 1
            state = GraphState(
                image=image,
                image_mime_type="image/png",
                offer_json={}, 
                image_check_model_name=None,
                image_decoding_model_name=self.model_name,
                offer_country=offer_country
            ) # type: ignore
            result_state = self.node.extract_offer_info_node(state)
            result_offers_n = len(result_state["decoded_offers"]) if result_state is not None and "decoded_offers" in result_state and result_state["decoded_offers"] is not None else 0
            print(f"Image: {f[:5]}..., Expected number of offers: {number_of_offers}, Actual number of offers: {result_offers_n}")
            if result_offers_n == number_of_offers:
                correct_results += 1
        success_rate = correct_results/total_images if total_images > 0 else 0
        print(f"Eval individual offer n node. Model: {self.model_name}, Success rate: {success_rate:.2f}")
        return success_rate