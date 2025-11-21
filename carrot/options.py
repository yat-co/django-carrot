from enum import Enum


MessageStatusPublished = "PUBLISHED"
MessageStatusInProgress = "IN_PROGRESS"
MessageStatusCompleted = "COMPLETED"
MessageStatusFailed = "FAILED"

MESSAGE_STATUS_CHOICES = (
    (MessageStatusPublished, 'Published'),
    (MessageStatusInProgress, 'In progress'),
    (MessageStatusFailed, 'Failed'),
    (MessageStatusCompleted, 'Completed'),
) # :tuple[tuple[str, str]]

class MessageStatus(Enum):
    PUBLISHED = MessageStatusPublished
    IN_PROGRESS = MessageStatusInProgress
    COMPLETED = MessageStatusCompleted
    FAILED = MessageStatusFailed
