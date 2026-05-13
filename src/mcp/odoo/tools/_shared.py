"""Shared types used across domain tool modules."""

from enum import Enum


class ResponseFormat(str, Enum):
    MARKDOWN = "markdown"
    JSON = "json"
