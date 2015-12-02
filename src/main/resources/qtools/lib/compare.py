"""
Methods that can be used as the argument to cmp=
in sorted(sequence, **cmp) or sequence.sort(**cmp)
"""
def pct_diff(attr):
    def cmp(tups):
        o1, o2 = tups
        a1 = getattr(o1, attr)
        a2 = getattr(o2, attr)
        if not a1:
            if not a2:
                return 0
            else:
                # hack to avoid nan (compare NaNs as well)
                return 1
        elif a2 is None:
            return -1
        else:
            return float(a2-a1)/a1
    return cmp

def abs_diff(attr):
    def cmp(tups):
        o1, o2 = tups
        a1 = getattr(o1, attr)
        a2 = getattr(o2, attr)
        if a1 is None:
            if a2 is None:
                return 0
            else:
                return a2
        elif a2 is None:
            return a1
        else:
            return getattr(o2, attr) - getattr(o1, attr)
    return cmp

def compare_closer_to_one(attr):
    def cmp(tups):
        o1, o2 = tups
        a1 = getattr(o1, attr)
        a2 = getattr(o2, attr)
        if a1 is None or a2 is None:
            return 0
        else:
            return abs(a2-1) - abs(a1-1)
    return cmp

def compare_closer_to_zero(attr):
    def cmp(tups):
        o1, o2 = tups
        a1 = getattr(o1, attr)
        a2 = getattr(o2, attr)
        if a1 is None or a2 is None:
            return 0
        else:
            return abs(a2) - abs(a1)
    return cmp

def compare_zero_nonzero(attr):
    def cmp(tups):
        o1, o2 = tups
        a1 = getattr(o1, attr)
        a2 = getattr(o2, attr)
        if a1 is None or a2 is None:
            return 0
        if a1 != 0 and a2 != 0:
            return 0
        elif a1 == 0:
            return 1
        else:
            return -1
    return cmp

def compare_anydiff(attr):
    def cmp(tups):
        o1, o2 = tups
        a1 = getattr(o1, attr)
        a2 = getattr(o2, attr)
        if a1 == a2:
            return 0
        else:
            return 1
    return cmp
