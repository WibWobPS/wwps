from __future__ import annotations

import pytest

from wwps import managers
from wwps.managers import ConditionType, MissionCompleteStatus, MissionNewStatus
from wwps.rows import YwpUserMission, YwpUserStage, parser_for


@pytest.mark.parametrize("score,money,exp", [
    (0, 0, 0),
    (50_000, 53, 260),
    (19_503, 29, 142),
    (98_886, 79, 390),
])
def test_reward_curves_hit_known_anchors(score, money, exp):
    assert managers.score_to_money(score) == money
    assert managers.score_to_exp(score) == exp


def test_reward_curves_fall_back_out_of_range():
    assert managers.score_to_money(3_000_000_000) == 1000
    assert managers.score_to_exp(3_000_000_000) == 10000


def test_soul_level_thresholds():
    assert [managers._soul_points(n) for n in range(7)] == [
        0, 1000, 3000, 7000, 13000, 22000, 34000]
    assert managers._soul_level(999) == 1
    assert managers._soul_level(1000) == 2
    assert managers._soul_level(33_999) == 6
    assert managers._soul_level(34_000) == 7


def test_add_exp_to_skill_caps_at_seven():
    from wwps.rows import YwpUserYoukaiSkill
    parser = parser_for(YwpUserYoukaiSkill, "2235000|7|34000|12000|0|0")
    result = managers.add_exp_to_skill(parser, 2235000, 5000)
    assert result["isMaxLevel"] is True
    assert result["after"]["level"] == 7


def test_add_exp_to_skill_levels_up():
    from wwps.rows import YwpUserYoukaiSkill
    parser = parser_for(YwpUserYoukaiSkill, "2235000|1|0|1000|0|0")
    result = managers.add_exp_to_skill(parser, 2235000, 1500)
    assert result["before"]["level"] == 1
    assert result["after"]["level"] == 2
    assert result["after"]["exp"] == 1500


def _stage(num_clear=0):
    return YwpUserStage(StageId=1001001, NumClear=num_clear)


@pytest.mark.parametrize("ctype,payload,expected", [
    (ConditionType.MinScore, {"score": 5000}, True),
    (ConditionType.MinScore, {"score": 5}, False),
    (ConditionType.MaxClearTime, {"clearTimeSec": 8}, True),
    (ConditionType.MaxClearTime, {"clearTimeSec": 120}, False),
    (ConditionType.MinCombo, {"comboMax": 25}, True),
    (ConditionType.MinCombo, {"comboMax": 3}, False),
    (ConditionType.CompleteStage, {}, True),
    (ConditionType.MinBonusBalls, {"bonusBlockNum": 12}, True),
])
def test_stage_conditions(ctype, payload, expected):
    assert managers.compute_stage_condition(ctype, payload, _stage(), 10, 0, 0) is expected


def test_clear_n_times_condition_reads_the_stage():
    assert managers.compute_stage_condition(
        ConditionType.ClearStageNTimes, {}, _stage(num_clear=12), 10, 0, 0) is True
    assert managers.compute_stage_condition(
        ConditionType.ClearStageNTimes, {}, _stage(num_clear=2), 10, 0, 0) is False


def test_used_youkai_condition():
    payload = {"userYoukaiResultList": [{"youkaiId": 10}, {"youkaiId": 2235000}]}
    assert managers.compute_stage_condition(
        ConditionType.UsedYoukai, payload, _stage(), 2235000, 0, 0) is True
    assert managers.compute_stage_condition(
        ConditionType.UsedYoukai, payload, _stage(), 999, 0, 0) is False


def test_finish_with_soult_uses_the_last_defeated_enemy():
    payload = {"enemyYoukaiResultList": [
        {"deadEndOrder": 1, "deadEndType": 0},
        {"deadEndOrder": 3, "deadEndType": 2235000},
    ]}
    assert managers.compute_stage_condition(
        ConditionType.FinishWithSoult, payload, _stage(), 0, 0, 0) is True
    assert managers.compute_stage_condition(
        ConditionType.FinishWithSpecificYoukaiSoult, payload, _stage(),
        2235000, 0, 0) is True
    assert managers.compute_stage_condition(
        ConditionType.FinishWithSpecificYoukaiSoult, payload, _stage(),
        1, 0, 0) is False


def test_lot_patterns_scale_with_befrienders():
    none = managers.generate_lot_youkai([(0, 0)] * 5, managers.RarityType.RarityE,
                                        False, False)
    one = managers.generate_lot_youkai([(0, 0), (0, 0), (0, 0), (0, 0), (0, 0)],
                                       managers.RarityType.RarityE, False, False)
    assert len(none) == 1 and len(one) == 1


def test_autobefriend_always_succeeds():
    entries = managers.generate_lot_youkai([(0, 0)] * 5,
                                           managers.RarityType.RarityS, False, True)
    assert entries[0]["lotResult"] == "11111"


def test_mission_sorting_order():
    parser = parser_for(YwpUserMission,
                        "1|10|1|5|5|2|1|0*2|20|1|3|0|0|0|0*3|30|1|1|1|1|2|0")
    managers.sort_user_mission(parser, 0, True)
    assert [m.MissionID for m in parser.items] == [10, 20, 30]
    assert parser.items[2].IsAppear == 0
    assert all(m.NewStatus == MissionNewStatus.NONE for m in parser.items)


def test_item_add_and_remove():
    from wwps.rows import YwpUserItem
    parser = parser_for(YwpUserItem, "10|3")
    managers.item_add(parser, 10, 2)
    assert parser.items[0].Count == 5
    managers.item_add(parser, 20, 1)
    assert len(parser.items) == 2
    managers.item_remove(parser, 20, 1)
    assert len(parser.items) == 1


def test_stage_edit_only_improves():
    parser = parser_for(YwpUserStage, "1001001|1|1|0|0|500|2|0")
    managers.MasterStageData._stage_items = [
        {"StageId": 1001001, "StageType": 1, "BossFlag": 0, "StarCondIDs": [0, 0, 0],
         "UseActionID": 0, "UseActionPoint": 1, "UseActionType": 0, "BattleType": 0}]
    managers.stage_edit(parser, 1001001, 1, 100, 0, 1, 0, 1)
    item = parser.items[0]
    assert item.Score == 500
    assert item.Star1 == 1 and item.Star2 == 1
    assert item.NumClear == 2
    managers.MasterStageData._stage_items = None
