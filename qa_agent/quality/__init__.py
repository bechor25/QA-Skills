"""Intelligence layer.

Risk scoring, strategy planning, scenario generation, test critique,
selector/assertion validators, and the learning engine. The deterministic
parts live here as plain Python; the LLM-driven parts are split between
prompt templates (loaded from `prompts/`) and validators in this package
that gate LLM output before it is persisted.
"""
