"""Issue tracker integration — bridges ospd-issue-tracker-api with the chat vertical."""

from issue_tracker_integration.client import IssueTrackerBridge
from issue_tracker_integration.orchestrator import IssueTrackerOrchestrator
from issue_tracker_integration.trello_adapter import TrelloClientAdapter

__all__ = ["IssueTrackerBridge", "IssueTrackerOrchestrator", "TrelloClientAdapter"]
