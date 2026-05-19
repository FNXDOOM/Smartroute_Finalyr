import numpy as np
from scipy.optimize import linear_sum_assignment


def assign_vehicles(cost_matrix: list) -> list:
    """
    Assign vehicles to routes using the Hungarian Algorithm.
    cost_matrix[i][j] = cost of assigning vehicle i to route j.
    Returns list of (vehicle_idx, route_idx) assignments.
    """
    cost_array = np.array(cost_matrix)
    row_ind, col_ind = linear_sum_assignment(cost_array)
    return list(zip(row_ind.tolist(), col_ind.tolist()))
