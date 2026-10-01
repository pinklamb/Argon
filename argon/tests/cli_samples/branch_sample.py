def classify(value):
    if value < 0:
        return "negative"
    elif value == 0:
        return "zero"
    match value:
        case 1:
            return "one"
        case _:
            pass
    return "positive" if value > 0 else "unknown"
