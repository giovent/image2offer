import os

from dotenv import load_dotenv
from openai import Client as LLM_Client

from graph.graph import I2OGraph
from graph.state import GraphState
# In this sample code, I use OpenAI APIs

load_dotenv()
# import variable OPENAI_API_KEY from environment
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

openai_client = LLM_Client(api_key=OPENAI_API_KEY)
usage_totals = {"input": 0, "output": 0, "usd": 0.0}
model_rates = {"gpt-5-nano": (0.05, 0.40), "gpt-5-mini": (0.25, 2.00), "gpt-5.2": (1.75, 14.00), "gpt-4o": (2.50, 10.00)}  # USD / 1M tokens
_orig_create = openai_client.responses.create
def tracked_create(*args, **kwargs):
    response = _orig_create(*args, **kwargs)
    usage = getattr(response, "usage", None)
    if usage:
        inp = getattr(usage, "input_tokens", 0) or 0; out = getattr(usage, "output_tokens", 0) or 0
        usage_totals["input"] += inp; usage_totals["output"] += out
        model = getattr(response, "model", kwargs.get("model", "")) or ""
        rates = next((v for k, v in model_rates.items() if str(model).startswith(k)), (0.0, 0.0))
        usage_totals["usd"] += (inp * rates[0] + out * rates[1]) / 1_000_000
    return response
openai_client.responses.create = tracked_create

if False: # Put to True to test the LLM client is working before running the graph
    result = openai_client.responses.create(
        model="gpt-5-nano",
        input="What is 3 + 1?",
    )
    print(result.output_text)

i2o = I2OGraph(llm_client=openai_client, CHECK_IMAGE_BEFORE_RUN=False, SEARCH_PRODUCT_IMAGE_ONLINE=False)

initial_state = GraphState(
    messages=[],
    warnings=[],
    product_image_urls=[],

    image=open("easy.png", "rb").read(),
    image_mime_type="image/png",
    offer_country="Italy",

    image_check_model_name="gpt-5-nano",
    image_decoding_model_name="gpt-5.2",
    product_enrichment_model_name="gpt-4o",
    final_offer_composition_model_name="gpt-5.2"
)

final_state = i2o.invoke(initial_state)
print(f"Product offers: {final_state['final_offers_info']}")
print(f"Total input tokens: {usage_totals['input']}")
print(f"Total output tokens: {usage_totals['output']}")
print(f"Estimated OpenAI cost (token-only): ${usage_totals['usd']:.6f}")


