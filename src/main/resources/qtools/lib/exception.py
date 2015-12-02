class ReturnWithCaveats(Exception):
    """
    This is probably crap Python, but return a valid result with
    some caveat that you want to bubble up to the user.  There
    is undoubtedly a better way of doing this, but it may not
    be thread-safe (singletons are out), and I don't want to
    rely on external machinery for just decorating an exception.
    """
    def __init__(self, explanations, return_value):
        """
        Constructs a return with a dictionary of explanations.
        """
        super(ReturnWithCaveats, self).__init__("Operation completed with warnings")
        self.explanations = explanations or {}
        self.return_value = return_value or None