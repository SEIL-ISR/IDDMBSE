from tradesx.ddo import design_components, campaign_commands, main


def test_design_id_decoding_matches_robustness_bash():
    # the seven hand-picked designs in examples/SEILR1/robustness.bash
    assert design_components(4234) == [1, 6, 10, 12]
    assert design_components(785) == [4, 5, 9, 13]
    assert design_components(549) == [4, 8, 11, 13]
    assert design_components(2185) == [2, 6, 10, 13]
    assert design_components(4370) == [1, 5, 9, 12]
    assert design_components(4) == [11]
    assert design_components(512) == [4]


def test_command_sequence_shape():
    cmds = campaign_commands([4234, 785], "2x2", "demo", 1, "navigate_to_goal_pose.json")
    groups = [(c[5], c[6]) for c in cmds]
    assert groups[:4] == [("db", "init"), ("db", "migrate"), ("db", "upgrade"),
                          ("components", "load_components")]
    assert groups.count(("designs", "create")) == 2
    assert groups.count(("environments", "create_from_template")) == 4
    assert groups[-2:] == [("experiments", "create"), ("experiments", "run")]


def test_start_grid_multiplies_environments():
    cmds = campaign_commands([1], "3x3", "demo", 1, "navigate_to_goal_pose.json",
                             start_grid="2x2")
    n = sum(1 for c in cmds if c[5:7] == ["environments", "create_from_template"])
    assert n == 36


def test_cli_dry_run(capsys):
    assert main(["--dry-run", "--designs", "1,2,3", "--grid", "2x2"]) == 0
    out = capsys.readouterr().out
    assert "designs create" in out
    assert "experiments run" in out
