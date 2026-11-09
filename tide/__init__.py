"""Tide—— 给她装的一套"活着"的状态系统。

不是聊天机器人：情绪会衰减，肚子会饿，你太久不理她会委屈，
但你只是话题聊完了，她不记仇。

    from tide import TideCore
    core = TideCore.from_config("config/")
    core.observe(text="你终于回我了", speaker="other")
    core.tick()
    core.plan_reply()
"""
from .core import TideCore
from .version import __version__

__all__ = ["TideCore"]