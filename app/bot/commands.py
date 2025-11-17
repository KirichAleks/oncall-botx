"""
Bot command collectors and handlers.

Note: Commands via @collector.command are not functional in this architecture
because the bot runs in Docker and Express cannot reach it back.
HTTP endpoints (/api/oncall/*) should be used instead for external integrations.
"""
import logging
from pybotx import HandlerCollector

logger = logging.getLogger(__name__)

collector = HandlerCollector()