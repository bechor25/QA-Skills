from qa_agent.agent.lifecycle import Phase
from qa_agent.agent.planner import plan_analyze, plan_full_run, plan_rerun


def test_full_run_default_includes_every_phase():
    plan = plan_full_run()
    assert plan.phases == list(Phase.ordered())


def test_full_run_no_llm_skips_execute():
    plan = plan_full_run(no_llm=True)
    assert Phase.EXECUTE not in plan.phases
    assert Phase.INSTALL not in plan.phases
    assert Phase.GENERATE in plan.phases  # generation still runs


def test_plan_analyze_skips_generation():
    plan = plan_analyze()
    assert Phase.GENERATE not in plan.phases
    assert Phase.STRATEGY in plan.phases


def test_plan_rerun_minimal():
    plan = plan_rerun("failed")
    assert plan.phases == [Phase.EXECUTE, Phase.REPORT]
    assert any("failed" in n for n in plan.notes)
