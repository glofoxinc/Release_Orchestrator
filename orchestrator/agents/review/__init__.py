"""Daily Review Agent — optional 6 PM fetch + Teams review scheduling."""

from daily_review_agent.bootstrap import bootstrap

bootstrap()

from daily_review_agent.config_loader import load_agent_config, readiness_report
from daily_review_agent.demo_call import run_demo_call
from daily_review_agent.runner import run_daily_agent
from daily_review_agent.slack_notify import run_slack_delivery, slack_readiness

__all__ = [
    "load_agent_config",
    "readiness_report",
    "run_daily_agent",
    "run_demo_call",
    "run_slack_delivery",
    "slack_readiness",
]
