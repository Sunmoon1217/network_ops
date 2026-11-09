import itertools


def to_bool(arg: str | None = None):
    if arg is None:
        return bool(False)
    if arg.lower() in ["false", "no", "0", "off"]:
        return bool(False)
    if arg.lower() in ["true", "yes", "1", "on"]:
        return bool(True)


def create_dict_combinations(**kwargs):
    valid_items = {k: v for k, v in kwargs.items() if v}

    if not valid_items:
        raise

    keys = valid_items.keys()
    values = valid_items.values()

    combinations = itertools.product(*values)

    result = []
    for combo in combinations:
        result.append(dict(zip(keys, combo)))

    return result
