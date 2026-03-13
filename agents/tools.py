from knowledge.retriever import retrieve_knowledge
from optimization.optimizer import optimize_price
from simulation.scenario_runner import run_scenario
from system.system_model import SystemModel

system_model = SystemModel()


def optimization_tool(query):
    result = optimize_price(system_model)

    return str(result)


def simulation_tool(query):
    result = run_scenario(system_model, 30, 10)

    return str(result)


def knowledge_tool(query):
    return retrieve_knowledge(query)
