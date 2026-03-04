import os

from typing import List

from openai import Client as LLM_Client
from graph.state import GraphState
from graph.nodes import ImageCheckNode

class ImageOfferCheckEval():
    """Eval to check if the resutl generated from the image check node is correct."""
    def __init__(self, client: LLM_Client, model_name: str) -> None:
        self.client = client
        self.model_name = model_name
        self.node =  ImageCheckNode(client=client)

    def evaluate(self) -> List[float]:
        """Returns the percertage of correct responses
        
        Returns:
            List[float]: [success_rate, correct_positives, wrong_negatives, correct_negatives, wrong_positives]
        """
        
        # load pictures from Images folder under this python file's folder
        images_folder = os.path.join(os.path.dirname(__file__), "Images")
        offer_image_files = [f for f in os.listdir(images_folder) if os.path.isfile(os.path.join(images_folder, f)) and "1_" in f]
        no_offer_image_files = [f for f in os.listdir(images_folder) if os.path.isfile(os.path.join(images_folder, f)) and "0_" in f]

        correct_positives = 0
        correct_negatives = 0
        wrong_positives = 0
        wrong_negatives = 0

        # run the image_check node through the images containing offers and check the results
        for f in offer_image_files:
            with open(os.path.join(images_folder, f), "rb") as img_file:
                image_bytes = img_file.read()
                state = GraphState(
                    image=image_bytes,
                    image_mime_type="image/png",
                    offer_json={}, 
                    image_check_model_name=self.model_name
                )
                result_state = self.node.check_image_offer_node(state)
                if result_state["messages"][-1].content == "True":
                    correct_positives += 1
                else:
                    wrong_negatives += 1

        # run the image_check node through the images NOT containing offers and check the results
        for f in no_offer_image_files:
            with open(os.path.join(images_folder, f), "rb") as img_file:
                image_bytes = img_file.read()
                state = GraphState(
                    image=image_bytes,
                    image_mime_type="image/png",
                    offer_json={}, 
                    image_check_model_name=self.model_name
                )
                result_state = self.node.check_image_offer_node(state)
                if result_state["messages"][-1].content == "False":
                    correct_negatives += 1
                else:
                    wrong_positives += 1

        # Calculate useful metrics
        success_rate = (correct_positives + correct_negatives)/(correct_positives + correct_negatives + wrong_positives + wrong_negatives)
        correct_positives_rate = correct_positives/(correct_positives + wrong_negatives) if (correct_positives + wrong_negatives) > 0 else 0
        correct_negatives_rate = correct_negatives/(correct_negatives + wrong_positives) if (correct_negatives + wrong_positives) > 0 else 0
        wrong_negatives_rate = wrong_negatives/(correct_positives + wrong_negatives) if (correct_positives + wrong_negatives) > 0 else 0
        wrong_positives_rate = wrong_positives/(correct_negatives + wrong_positives) if (correct_negatives + wrong_positives) > 0 else 0
        
        print(f"Eval image check node. Model: {self.model_name}")
        print(f"Success rate: {success_rate:.2f}, Correct Positives: {correct_positives_rate:.2f}, Wrong Negatives: {wrong_negatives}, Correct Negatives: {correct_negatives_rate:.2f}, Wrong Positives: {wrong_positives_rate:.2f}")
        return [success_rate, correct_positives_rate, wrong_negatives_rate, correct_negatives_rate, wrong_positives_rate]