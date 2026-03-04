from typing import Any
# from dotenv import load_dotenv
# from langchain_core.messages import BaseMessage, ToolMessage, SystemMessage
from openai import Client as LLM_Client
# from langchain_core.tools import tool
# from langgraph.graph.message import add_messages
from langgraph.graph import StateGraph, START, END
# from langgraph.prebuilt import ToolNode


from graph.state import GraphState
from graph.nodes import ImageCheckNode, OfferInfoExtractionNode, ProductEnrichmentNode, ProductImageSearchNode, FinalOfferCompositionNode

class I2OGraph:
    def __init__(self, llm_client: LLM_Client, CHECK_IMAGE_BEFORE_RUN: bool= False, SEARCH_PRODUCT_IMAGE_ONLINE: bool= False) -> None:
        self.image_check_node = ImageCheckNode(client=llm_client)
        self.offer_info_extraction_node = OfferInfoExtractionNode(client=llm_client)
        self.product_info_enrichment_node = ProductEnrichmentNode(client=llm_client)
        self.product_image_search_node = ProductImageSearchNode(client=llm_client)
        self.final_offer_composition_node = FinalOfferCompositionNode(client=llm_client)
        self.CHECK_IMAGE_BEFORE_RUN = CHECK_IMAGE_BEFORE_RUN
        self.SEARCH_PRODUCT_IMAGE_ONLINE = SEARCH_PRODUCT_IMAGE_ONLINE
        self._compiled_graph = self._build_graph()

    def _build_graph(self) -> Any:
        """Constructs the LangGraph state machine."""
        builder = StateGraph(GraphState)
        
        builder.add_node("Image Check", self.image_check_node.check_image_offer_node)

        builder.add_node("Extract Offer Info", self.offer_info_extraction_node.extract_offer_info_node)

        if self.CHECK_IMAGE_BEFORE_RUN:
            builder.add_edge(START, "Image Check")
            builder.add_conditional_edges("Image Check",
                                        path=lambda state: "Extract Offer Info" if state["messages"][-1].content=="True" else END)
        else:
            builder.add_edge(START, "Extract Offer Info")

        builder.add_node("Product Info Enrichment", self.product_info_enrichment_node.enrich_offer_info_node) # Placeholder for future node
        builder.add_edge("Extract Offer Info", "Product Info Enrichment")

        builder.add_node("Product Image Search", self.product_image_search_node.search_product_image_node)
        builder.add_node("Final Offer Composition", self.final_offer_composition_node.compose_final_offer_node)
        if self.SEARCH_PRODUCT_IMAGE_ONLINE:
            builder.add_edge("Product Info Enrichment", "Product Image Search")
            builder.add_edge("Product Image Search", "Final Offer Composition")
        else:
            builder.add_edge("Product Info Enrichment", "Final Offer Composition")

        builder.add_edge("Product Image Search", "Final Offer Composition")
        builder.add_edge("Final Offer Composition", END)

        graph = builder.compile()
        print("Graph compiled successfully.")

        return graph
    
    def invoke(self, initial_state: GraphState) -> GraphState:
        """Invokes the graph on the initial state."""
        final_state = self._compiled_graph.invoke(initial_state)
        print("Graph invocation end.")
        return final_state