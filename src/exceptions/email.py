class BaseEmailError(Exception):
    def __init__(self, message="An email error occurred."):
        super().__init__(message)
