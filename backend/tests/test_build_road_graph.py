"""Tests for turning OpenStreetMap ways into the Dijkstra road graph."""

import numpy as np
import pytest

from scripts.build_road_graph import (
    MAXSPEED_FACTOR,
    DrivableWayCollector,
    Way,
    build_graph,
    direction,
    is_drivable,
    parse_maxspeed,
)


@pytest.mark.parametrize(
    "tag,expected",
    [
        ("30", 30.0),
        ("20 mph", 32.18688),
        ("48 km/h", 48.0),
        ("none", None),
        ("GB:nsl_single", None),
        (None, None),
    ],
)
def test_parse_maxspeed(tag, expected) -> None:
    assert parse_maxspeed(tag) == pytest.approx(expected)


@pytest.mark.parametrize(
    "tags,expected",
    [
        ({"highway": "residential"}, True),
        ({"highway": "footway"}, False),
        ({"highway": "cycleway"}, False),
        ({"highway": "service"}, True),
        ({"highway": "service", "service": "parking_aisle"}, False),
        ({"highway": "residential", "access": "private"}, False),
        ({"highway": "residential", "access": "private", "motor_vehicle": "yes"}, True),
        ({"highway": "pedestrian", "area": "yes"}, False),
    ],
)
def test_is_drivable(tags, expected) -> None:
    assert is_drivable(tags) is expected


@pytest.mark.parametrize(
    "tags,expected",
    [
        ({"highway": "residential"}, 0),
        ({"highway": "residential", "oneway": "yes"}, 1),
        ({"highway": "residential", "oneway": "-1"}, -1),
        ({"highway": "primary", "junction": "roundabout"}, 1),
        ({"highway": "motorway"}, 1),
        ({"highway": "motorway", "oneway": "no"}, 0),
    ],
)
def test_direction(tags, expected) -> None:
    assert direction(tags) == expected


def way(ids, direction=0, speed=36.0, step=0.001):
    """A straight east-west way at latitude 51.5 through the given node ids."""
    return Way(
        node_ids=list(ids),
        lats=[51.5] * len(ids),
        lons=[-0.1 + i * step for i in range(len(ids))],
        direction=direction,
        speed_kmh=speed,
    )


def edges(graph) -> set[tuple[int, int]]:
    src = np.repeat(np.arange(len(graph["lat"])), np.diff(graph["indptr"]))
    return set(zip(src.tolist(), graph["indices"].tolist(), strict=True))


def test_shape_points_are_folded_into_one_edge() -> None:
    graph = build_graph([way([1, 2, 3, 4, 5])])

    assert len(graph["lat"]) == 2  # only the two ends survive
    assert edges(graph) == {(0, 1), (1, 0)}
    assert graph["length_m"] == pytest.approx([4 * 69.3] * 2, rel=0.01)
    assert graph["time_s"] == pytest.approx(graph["length_m"] / 10.0, rel=1e-4)  # 36 km/h is 10 m/s


def test_a_shared_node_becomes_a_junction() -> None:
    main = way([1, 2, 3])
    side = Way(node_ids=[2, 9], lats=[51.5, 51.501], lons=[-0.099, -0.099], direction=0, speed_kmh=36.0)
    graph = build_graph([main, side])
    assert len(graph["lat"]) == 4
    assert len(edges(graph)) == 6


def test_one_way_loop_only_has_forward_edges() -> None:
    loop = Way(
        node_ids=[1, 2, 3, 1],
        lats=[51.5, 51.5, 51.501, 51.5],
        lons=[-0.1, -0.099, -0.0995, -0.1],
        direction=1,
        speed_kmh=36.0,
    )
    side_a = Way([2, 3], [51.5, 51.501], [-0.099, -0.0995], 0, 36.0)
    graph = build_graph([loop, side_a])
    # Node 1 closes the loop; 2 and 3 are junctions with the two-way side street.
    assert len(graph["lat"]) == 3
    assert len(edges(graph)) == 4  # 1->2, 2->3, 3->1 one way, plus 3->2 from the side street


def test_reverse_one_way_points_against_the_node_order() -> None:
    forward = build_graph([way([1, 2]), way([2, 3], direction=1), way([3, 4]), way([4, 1])])
    backward = build_graph([way([1, 2]), way([2, 3], direction=-1), way([3, 4]), way([4, 1])])
    assert len(edges(forward)) == len(edges(backward)) == 7


def test_nodes_that_cannot_get_back_are_pruned() -> None:
    town = [way([1, 2, 3]), way([3, 4, 1])]  # a two-way ring
    trap = way([2, 7, 8], direction=1)  # one way into a dead end
    graph = build_graph([*town, trap])
    assert len(graph["lat"]) == 3  # nodes 1, 2 and 3; the dead end cannot reach the ring


OSM_XML = """<?xml version='1.0' encoding='UTF-8'?>
<osm version="0.6">
  <node id="1" lat="51.5000" lon="-0.1000"/>
  <node id="2" lat="51.5000" lon="-0.0990"/>
  <node id="3" lat="51.5000" lon="-0.0980"/>
  <node id="4" lat="51.5010" lon="-0.0990"/>
  <node id="5" lat="51.5020" lon="-0.0990"/>
  <way id="10"><nd ref="1"/><nd ref="2"/><nd ref="3"/>
    <tag k="highway" v="residential"/><tag k="maxspeed" v="20 mph"/></way>
  <way id="11"><nd ref="2"/><nd ref="4"/>
    <tag k="highway" v="tertiary"/></way>
  <way id="12"><nd ref="4"/><nd ref="5"/>
    <tag k="highway" v="footway"/></way>
</osm>
"""


def test_reads_an_osm_file(tmp_path) -> None:
    path = tmp_path / "tiny.osm"
    path.write_text(OSM_XML)

    collector = DrivableWayCollector()
    collector.apply_file(str(path), locations=True)

    assert [w.node_ids for w in collector.ways] == [[1, 2, 3], [2, 4]]  # the footway is skipped
    assert collector.ways[0].speed_kmh == pytest.approx(20 * 1.609344 * MAXSPEED_FACTOR)
    assert collector.ways[1].speed_kmh == 40

    graph = build_graph(collector.ways)
    assert len(graph["lat"]) == 4
    assert len(graph["indices"]) == 6
