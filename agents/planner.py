from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from agents.state import AgentState

load_dotenv()

llm = ChatOpenAI(model="gpt-4o-mini",temperature=0)

def planner_node(state:AgentState):

    query = state["query"]

    prompt = f"""
User query: {query}

Choose tool:

optimization
simulation
knowledge
"""

    decision = llm.invoke(prompt).content

    state["action"] = decision.strip().lower()

    return state