# PERFECT reads this file on top of perfect/app/config.py for this project.
#
# A campaign run on several runners has one RQ worker per runner, and every worker
# writes its trials' updates into the one SQLite database while the server may be
# committing the campaign's experiments. SQLite's default busy timeout is 5 s, which
# a worker can outwait at the start of a campaign and then fail its trial with
# "database is locked"; a worker now waits up to a minute for the lock instead.
SQLALCHEMY_ENGINE_OPTIONS = {"connect_args": {"timeout": 60}}
