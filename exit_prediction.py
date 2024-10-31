import numpy as np

def model_call(response):
    global q_values, actions, mapped_layout, environment_columns, environment_rows, paths, original_layout
    mapping = {
    "S": 100, 
    "F": -10, 
    "0": -100,
    ".": -1,   
    "P": -1,
    "U": -1,
    }

    value_to_symbol = {
    100: "S",
    -10: "F",
    -100: "0",
    -1: ".",
    -5: "Z"
    }

    q_values = np.load("q_values.npy")
    user_position = [(i, j) for i, row in enumerate(response['layout']) for j, val in enumerate(row) if val == "U"]
    exit_position = [(i, j) for i, row in enumerate(response['layout']) for j, val in enumerate(row) if val == "S"]
    mapped_layout = np.array([[mapping[cell] for cell in row] for row in response['layout']])
    environment_columns = len(mapped_layout[0])
    environment_rows = len(mapped_layout)
    actions = ['up', 'right', 'down', 'left']
    fire_zones = []
    paths = []
    danger_zones = set()

    for i, row in enumerate(mapped_layout):
        for j, cell in enumerate(row):
            if cell == -10:
                fire_zones.append((i, j))

    for row, col in fire_zones:
        for adj_row, adj_col in [(row-1, col), (row+1, col), (row, col-1), (row, col+1)]:
            if 0 <= adj_row < environment_rows and 0 <= adj_col < environment_columns:
                if mapped_layout[adj_row, adj_col] != -10 and mapped_layout[adj_row, adj_col] != 100 and mapped_layout[adj_row, adj_col] != -100:
                    danger_zones.add((adj_row, adj_col))

    for row, col in danger_zones:
        mapped_layout[row, col] = -5.
    
    paths.append(get_shortest_path(user_position[0][0], user_position[0][1]))

    original_layout = (np.vectorize(value_to_symbol.get)(mapped_layout))

    for x in paths[0]:
        original_layout[x[0], x[1]] = "P"
    original_layout[user_position[0]] = "U"
    original_layout[exit_position[0]] = "S"
    original_layout = original_layout.tolist()
    
    return original_layout

def is_terminal_state(current_row_index, current_column_index):
    if (mapped_layout[current_row_index, current_column_index] == -1.) or (mapped_layout[current_row_index, current_column_index] == -10.) or (mapped_layout[current_row_index, current_column_index] == -5.):
        return False
    else:
        return True

def get_next_action(current_row_index, current_column_index, epsilon):

    if np.random.random() < epsilon:
        return np.argmax(q_values[current_row_index, current_column_index])
    else:
        return np.random.randint(4)
    
def get_next_location(current_row_index, current_column_index, action_index):

    new_row_index = current_row_index
    new_column_index = current_column_index
    if actions[action_index] == 'up' and current_row_index > 0:
        new_row_index -= 1
    elif actions[action_index] == 'right' and current_column_index < environment_columns - 1:
        new_column_index += 1
    elif actions[action_index] == 'down' and current_row_index < environment_rows - 1:
        new_row_index += 1
    elif actions[action_index] == 'left' and current_column_index > 0:
        new_column_index -= 1
    return new_row_index, new_column_index

def get_shortest_path(start_row_index, start_column_index):

    if is_terminal_state(start_row_index, start_column_index):
        return []
    else: 
        current_row_index, current_column_index = start_row_index, start_column_index
        shortest_path = []
        shortest_path.append([current_row_index, current_column_index])
        while not is_terminal_state(current_row_index, current_column_index):
            action_index = get_next_action(current_row_index, current_column_index, 1.)
            current_row_index, current_column_index = get_next_location(current_row_index, current_column_index, action_index)
            shortest_path.append([current_row_index, current_column_index])
        return shortest_path

