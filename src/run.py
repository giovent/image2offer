import os

from dotenv import load_dotenv
from openai import Client as LLM_Client

from graph.graph import I2OGraph
from graph.state import GraphState

load_dotenv()

# In this sample code, I use OpenAI APIs
# import variable OPENAI_API_KEY from environment
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

openai_client = LLM_Client(api_key=OPENAI_API_KEY)

if False: # Put to True to test the LLM client is working before running the graph
    result = openai_client.responses.create(
        model="gpt-5-nano",
        input="What is 3 + 1?",
    )
    print(result.output_text)

i2o = I2OGraph(llm_client=openai_client, CHECK_IMAGE_BEFORE_RUN=True, SEARCH_PRODUCT_IMAGE_ONLINE=True)

initial_state = GraphState(
    messages=[],
    warnings=[],
    product_image_urls=[],

    image=open("offer_image_example_3.png", "rb").read(),
    image_mime_type="image/png",
    offer_country="italy",

    image_check_model_name="gpt-5-nano",
    image_decoding_model_name="gpt-5-mini",
    product_enrichment_model_name="gpt-4o",
    product_image_search_model_name="gpt-4o",
    final_offer_composition_model_name="gpt-5-mini"
)

final_state = i2o.invoke(initial_state)
print(f"Product offers: {final_state['final_offers_info']}")


