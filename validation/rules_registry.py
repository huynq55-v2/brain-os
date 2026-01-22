VALIDATION_RULES = []

def register_rule(fn):
    """Decorator để tự động đăng ký rule"""
    VALIDATION_RULES.append(fn)
    return fn