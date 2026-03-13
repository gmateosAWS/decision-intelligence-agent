import pickle

class SystemModel:

    def __init__(self):

        self.demand_model = pickle.load(
            open("models/demand_model.pkl","rb")
        )

        self.unit_cost = 10

    def evaluate(self, price, marketing):

        demand = self.demand_model.predict([[price,marketing]])[0]

        revenue = price * demand
        cost = demand * self.unit_cost
        profit = revenue - cost

        return {
            "price": price,
            "marketing": marketing,
            "demand": demand,
            "revenue": revenue,
            "cost": cost,
            "profit": profit
        }