import os

from dotenv import load_dotenv
from openai import Client as LLM_Client

from graph.graph import I2OGraph
from graph.state import GraphState

from evals.image_check_eval.eval import ImageOfferCheckEval
from evals.product_n_check_eval.eval import IndividualOfferNEval
from evals.product_info_enrichment_eval.eval import ProductInfoEnrichmentEval

load_dotenv()

# Decide weather to test LLM API first
TEST_APIS = False

# Decide which evals to run
EVAL_IMAGE_CHECK = False
EVAL_NUMBER_OF_OFFERS = False
EVAL_INFO_ENRICHMENT = True

# import variable OPENAI_API_KEY from environment
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
# Initialize the OpenAI client
openai_client = LLM_Client(api_key=OPENAI_API_KEY)

if TEST_APIS: # Put to True to test the LLM client is working before running the graph
  result = openai_client.responses.create(
    model="gpt-5-nano",
    input="Hello!",
  )
  print(result.output_text)

i2o = I2OGraph(llm_client=openai_client)

if EVAL_IMAGE_CHECK:
  img_chk_eval = ImageOfferCheckEval(client=openai_client, model_name="gpt-5-nano")
  img_chk_eval.evaluate()

if EVAL_NUMBER_OF_OFFERS:
  offer_n_eval = IndividualOfferNEval(client=openai_client, model_name="gpt-5-nano", save_offers_to_txt=False)
  offer_n_eval.evaluate()

if EVAL_INFO_ENRICHMENT:
  offer_n_eval = ProductInfoEnrichmentEval(client=openai_client, model_name="gpt-5-nano")
  offer_n_eval.evaluate()



