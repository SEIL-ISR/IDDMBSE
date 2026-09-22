import json

from pxr import Sdf

import fetch_warehouse as fw
from conftest import WAREHOUSE

LAYERS = WAREHOUSE / "layers"
CLUTTER = "/World/CbaseWarehouseMaze/ClutterV2"


def open_layer(name):
    layer = Sdf.Layer.FindOrOpen(str(LAYERS / name))
    assert layer is not None, name
    return layer


def test_every_layer_parses_and_the_chain_is_sublayered():
    assert open_layer("carter_warehouse_clutter_v2.usda").subLayerPaths == ["carter_warehouse_animated.usda"]
    assert open_layer("carter_warehouse_animated.usda").subLayerPaths == ["carter_warehouse_maze.usda"]
    assert open_layer("carter_warehouse_people.usda").subLayerPaths == ["carter_warehouse_maze.usda"]
    assert open_layer("carter_warehouse_maze.usda").subLayerPaths == ["carter_warehouse_navigation.usd"]


def test_asset_paths_are_urls_the_asset_root_or_a_sibling_layer():
    local = set(fw.LAYERS) | set(fw.SAMPLES)
    for name in fw.LAYERS:
        for path in fw.asset_paths(open_layer(name)):
            ok = path.startswith("https://") or path.startswith(fw.TOKEN + "/Isaac/") or path in local
            assert ok, (name, path)
            assert not path.startswith("/") and ".." not in path


def test_clutter_groups_match_the_layout():
    layer = open_layer("carter_warehouse_clutter_v2.usda")
    layout = json.loads((LAYERS / "clutter_layout.json").read_text())
    groups = layer.GetPrimAtPath(CLUTTER).nameChildren
    assert [g.name for g in groups] == [g["name"] for g in layout["groupings"]]
    assert len(groups) == 17
    for spec, g in zip(groups, layout["groupings"]):
        assert spec.referenceList.prependedItems[0].assetPath == layout["assets"][g["asset"]]["url"]
        assert [round(v, 4) for v in spec.attributes["xformOp:translate"].default] == g["translation_m"]
        assert round(float(spec.attributes["xformOp:rotateZ"].default), 4) == g["yaw_deg"]


def test_old_rack_grid_off_and_no_saved_carter_state():
    layer = open_layer("carter_warehouse_clutter_v2.usda")
    assert layer.GetPrimAtPath("/World/CbaseWarehouseMaze/StaticProps").active is False
    assert [c.name for c in layer.GetPrimAtPath("/World/Nova_Carter_ROS").nameChildren] == ["differential_drive"]
