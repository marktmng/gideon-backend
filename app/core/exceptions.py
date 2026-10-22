"""Custom domain exceptions for clean separation of concerns."""


class GideonException(Exception):
    """Base domain exception."""
    pass


class EntityNotFoundError(GideonException):
    """Raised when a requested resource does not exist."""
    def __init__(self, entity_name: str, entity_id: str):
        super().__init__(f"{entity_name} with ID '{entity_id}' was not found.")
        self.entity_name = entity_name
        self.entity_id = entity_id


class AIProviderError(GideonException):
    """Raised when an AI provider fails to generate a response."""
    pass
