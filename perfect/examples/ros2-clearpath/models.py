from sqlalchemy.ext.hybrid import hybrid_property

from perfect.app import models

def cost(self: models.Design):
    cost = 0
    for _c in self.components:
        cost += _c.specification.get("cost", 1)
    return cost

models.Design.cost = hybrid_property(cost)
