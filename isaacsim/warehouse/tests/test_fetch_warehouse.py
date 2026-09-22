from pxr import Sdf

import fetch_warehouse as fw

SCENARIO = "Isaac/Samples/ROS2/Scenario"
ROBOTS = "Isaac/Samples/ROS2/Robots"


def test_the_four_sample_paths():
    root = "/assets/Isaac/6.0"
    assert fw.rebase("../../../Environments/Simple_Warehouse/warehouse_with_forklifts.usd", SCENARIO, root) == \
        root + "/Isaac/Environments/Simple_Warehouse/warehouse_with_forklifts.usd"
    assert fw.rebase("../../../Environments/Simple_Warehouse/Stage/warehouse_extras.usd", SCENARIO, root) == \
        root + "/Isaac/Environments/Simple_Warehouse/Stage/warehouse_extras.usd"
    assert fw.rebase("../Robots/Nova_Carter_ROS.usd", SCENARIO, root) == "./Nova_Carter_ROS.usd"
    assert fw.rebase("../../../Robots/NVIDIA/NovaCarter/nova_carter.usd", ROBOTS, root) == \
        root + "/Isaac/Robots/NVIDIA/NovaCarter/nova_carter.usd"


def test_authored_layer_paths():
    root = "https://example.com/Assets/Isaac/6.0"
    assert fw.rebase("${ISAACSIM_ASSET_ROOT}/Isaac/People/Characters/a/a.usd", None, root) == root + "/Isaac/People/Characters/a/a.usd"
    assert fw.rebase("carter_warehouse_maze.usda", None, root) == "carter_warehouse_maze.usda"
    url = "https://omniverse-content-staging.s3.us-west-2.amazonaws.com/Assets/x.usd"
    assert fw.rebase(url, None, root) == url
    assert fw.rebase(url, SCENARIO, root) == url


def fake_asset_root(tmp_path):
    """The two sample files with the relative paths NVIDIA's have, and empty files for everything they and the layers point at."""
    root = tmp_path / "Isaac" / "6.0"
    targets = [
        "Isaac/Environments/Simple_Warehouse/warehouse_with_forklifts.usd",
        "Isaac/Environments/Simple_Warehouse/Stage/warehouse_extras.usd",
        "Isaac/Robots/NVIDIA/NovaCarter/nova_carter.usd",
        "Isaac/People/Characters/female_adult_police_02/female_adult_police_02.usd",
        "Isaac/People/Characters/original_male_adult_construction_05/male_adult_construction_05.usd",
        "Isaac/People/Characters/female_adult_police_03_new/female_adult_police_03_new.usd",
        "Isaac/People/Characters/original_male_adult_medical_01/male_adult_medical_01.usd",
    ]
    for rel in targets:
        Sdf.Layer.CreateNew(str(root / rel)).Save()
    nav = Sdf.Layer.CreateNew(str(root / SCENARIO / "carter_warehouse_navigation.usd"))
    world = Sdf.CreatePrimInLayer(nav, "/World/warehouse")
    world.referenceList.Prepend(Sdf.Reference("../../../Environments/Simple_Warehouse/warehouse_with_forklifts.usd"))
    extras = Sdf.CreatePrimInLayer(nav, "/World/warehouse_extras")
    extras.referenceList.Prepend(Sdf.Reference("../../../Environments/Simple_Warehouse/Stage/warehouse_extras.usd"))
    carter = Sdf.CreatePrimInLayer(nav, "/World/Nova_Carter_ROS")
    carter.payloadList.Prepend(Sdf.Payload("../Robots/Nova_Carter_ROS.usd"))
    nav.Save()
    robot = Sdf.Layer.CreateNew(str(root / ROBOTS / "Nova_Carter_ROS.usd"))
    sensors = Sdf.CreatePrimInLayer(robot, "/nova_carter_ros2_sensors")
    sensors.payloadList.Prepend(Sdf.Payload("../../../Robots/NVIDIA/NovaCarter/nova_carter.usd"))
    robot.Save()
    return root


def test_build_on_a_fake_asset_root(tmp_path, capsys):
    root = str(fake_asset_root(tmp_path))
    out = tmp_path / "generated"
    fw.build(root, out)
    assert fw.check(out) == 0
    nav = sorted(fw.asset_paths(Sdf.Layer.FindOrOpen(str(out / "carter_warehouse_navigation.usd"))))
    assert nav == sorted([
        "./Nova_Carter_ROS.usd",
        root + "/Isaac/Environments/Simple_Warehouse/Stage/warehouse_extras.usd",
        root + "/Isaac/Environments/Simple_Warehouse/warehouse_with_forklifts.usd",
    ])
    robot = fw.asset_paths(Sdf.Layer.FindOrOpen(str(out / "Nova_Carter_ROS.usd")))
    assert robot == [root + "/Isaac/Robots/NVIDIA/NovaCarter/nova_carter.usd"]
    for name in fw.LAYERS:
        text = (out / name).read_text()
        assert fw.TOKEN not in text
    people = [p for p in fw.asset_paths(Sdf.Layer.FindOrOpen(str(out / "carter_warehouse_animated.usda"))) if "Characters" in p]
    assert len(people) == 4 and all(p.startswith(root + "/Isaac/People/Characters/") for p in people)
    assert (out / "clutter_layout.json").exists()
    assert "differs from the Isaac Sim 6.0 sample" in capsys.readouterr().out
