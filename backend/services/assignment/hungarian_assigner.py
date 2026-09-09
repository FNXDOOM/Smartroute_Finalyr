import numpy as np
from scipy.optimize import linear_sum_assignment


def assign_vehicles(cost_matrix: list) -> list:
    """Assign vehicles to routes via Hungarian."""
    cost_array = np.array(cost_matrix)
    row_ind, col_ind = linear_sum_assignment(cost_array)
    return list(zip(row_ind.tolist(), col_ind.tolist()))
