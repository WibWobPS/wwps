from __future__ import annotations


def _mk(name: str, fields: list[tuple[str, type]]):
    def __init__(self, **kw):
        for fname, conv in fields:
            setattr(self, fname, kw.get(fname, "" if conv is str else 0))

    cls = type(name, (), {"__init__": __init__})
    cls.FIELDS = [(fname, conv) for fname, conv in fields]
    return cls


def parser_for(cls, src: str | None = "", prefix: str = "", delimiter: str = "|"):
    from .table_parser import TypedTableParser
    return TypedTableParser(cls, cls.FIELDS, src, prefix, delimiter)


YwpUserDictionary = _mk("YwpUserDictionary", [
    ("YoukaiId", int), ("IsBefriend", int), ("IsSeen", int)])

YwpUserEvent = _mk("YwpUserEvent", [
    ("EventId", int), ("EventNo", int), ("GeneralIntValue1", int),
    ("GeneralIntValue2", int), ("GeneralIntValue3", int), ("GeneralIntValue4", int),
    ("GeneralIntValue5", int), ("ChanceTimeSec", str), ("ChanceTimeOpenFlg", str),
    ("GeneralStringValue1", str), ("GeneralStringValue2", str),
    ("GeneralStringValue3", str), ("GeneralStringValue4", str),
    ("GeneralStringValue5", str), ("FreeBattleCount", int)])

YwpUserIcon = _mk("YwpUserIcon", [("IconId", int)])

YwpUserItem = _mk("YwpUserItem", [("ItemId", int), ("Count", int)])

YwpUserItemRemainCnt = _mk("YwpUserItemRemainCnt", [
    ("ItemId", int), ("RemainCount", int)])

YwpUserMap = _mk("YwpUserMap", [
    ("MapId", int), ("IsUnlocked", int), ("FriendCount", int)])

YwpUserMenufunc = _mk("YwpUserMenufunc", [("AppId", int), ("AppFlg", int)])

YwpUserStage = _mk("YwpUserStage", [
    ("StageId", int), ("StageStatus", int), ("Star1", int), ("Star2", int),
    ("Star3", int), ("Score", int), ("NumClear", int), ("Unk2", int)])

YwpUserYoukaiDeck = _mk("YwpUserYoukaiDeck", [
    ("Unk1", int), ("MiddleYoukaiId", int), ("MiddleLeftYoukaiId", int),
    ("MiddleRightYoukaiId", int), ("FarLeftYoukaiId", int),
    ("FarRightYoukaiId", int), ("Unk2", int), ("WatchId", int)])

YwpUserYoukai = _mk("YwpUserYoukai", [
    ("YoukaiId", int), ("Level", int), ("Exp", int), ("Hp", int), ("Atk", int),
    ("ExpDenominator", int), ("ExpNumerator", int), ("Percentage", int),
    ("IsLockedLevel", int), ("BefriendDate", int), ("BreakLimitCount", int)])

YwpUserYoukaiSkill = _mk("YwpUserYoukaiSkill", [
    ("YoukaiId", int), ("Level", int), ("Points", int),
    ("PercentageDenominator", int), ("PercentageNumerator", int),
    ("Percentage", int)])

YwpUserMission = _mk("YwpUserMission", [
    ("SeqNo", int), ("MissionID", int), ("IsAppear", int),
    ("MissionParamTarget", int), ("MissionParamProgress", int),
    ("MissionCompleteStatus", int), ("NewStatus", int), ("Unk", int)])

YwpUserShopItemUnlock = _mk("YwpUserShopItemUnlock", [("ItemID", int)])

YwpUserShopItemRemainCnt = _mk("YwpUserShopItemRemainCnt", [
    ("ItemID", int), ("AlreadyBought", int)])

YwpUserYoukaiBonusEffect = _mk("YwpUserYoukaiBonusEffect", [
    ("YoukaiID", int), ("BonusEffectLevel", int),
    ("BonusEff2ActivatedFlg", int), ("BonusEff3ActivatedFlg", int)])

YwpUserYoukaiLegendReleaseHistory = _mk("YwpUserYoukaiLegendReleaseHistory", [
    ("LegendYokaiID", int)])

PuniMstStageItem = _mk("PuniMstStageItem", [
    ("StageId", int), ("MapId", int), ("StageName", str), ("StageType", int),
    ("StageNo", int), ("FirstStageFlag", int), ("BossFlag", int),
    ("UseActionPoint", int), ("StarCond1", int), ("StarCond2", int),
    ("StarCond3", int), ("Unk1", int), ("EnemySetID", int),
    ("StoreReviewFlag", int), ("BackgroundName", str),
    ("NextStageRelationCode", str), ("HideStageRelationCode", str),
    ("RecommendLevel", int), ("UseActionType", int), ("UseActionId", int),
    ("StageObjectType", int), ("BgmFileName", str), ("Unk2", int),
    ("Unk3", str), ("Unk4", int), ("DeckForbidFlags", str), ("Unk5", str),
    ("Unk6", str), ("Unk7", int), ("Unk8", int), ("Unk9", int)])

StageConditionItem = _mk("StageConditionItem", [
    ("ConditionId", int), ("ConditionType", int), ("Description", str),
    ("ConditionVal1", int), ("ConditionVal2", int), ("ConditionVal3", int)])

YwpMstYoukai = _mk("YwpMstYoukai", [
    ("YoukaiId", int), ("YoukaiName", str), ("YoukaiType", int),
    ("YoukaiRarity", int), ("YoukaiKind", int), ("LevelType", int),
    ("FoodType", int), ("MaxLevel", int), ("BaseHp", int), ("MaxHp", int),
    ("BaseAtk", int), ("MaxAtk", int), ("EvolutionYoukaiId", int),
    ("EvolutionLevel", int), ("DictionaryId", int), ("YoukaiDescription", str),
    ("TextPuzzle", str), ("TextGasha", str), ("TextMission", str),
    ("TextGift", str), ("UnusedName", str), ("SkillEffectColorR", int),
    ("SkillEffectColorG", int), ("SkillEffectColorB", int),
    ("ScaleBattleFriend", int), ("ScaleBattleEnemy", int), ("YoukaiSize", int),
    ("Width", int), ("Height", int), ("X", int), ("Y", int),
    ("ReadingName", str), ("FriendOffsetX", int), ("FriendOffsetY", int),
    ("EffectType", int), ("OpenDt", str), ("YoukaiEffectBack", str),
    ("YoukaiEffectFront", str), ("ScaleOffsetDeck", int)])

YwpMstYoukaiLevel = _mk("YwpMstYoukaiLevel", [
    ("LevelTtype", int), ("Level", int), ("BaseExp", int), ("MaxExp", int)])

YwpMstConflate = _mk("YwpMstConflate", [
    ("ConflateID", int), ("YMoneyCost", int), ("FuseObject1Type", int),
    ("FuseObject1ID", int), ("FuseObject2Type", int), ("FuseObject2ID", int),
    ("ResultType", int), ("ResultID", int)])

YwpMstGachaYoukaiChoice = _mk("YwpMstGachaYoukaiChoice", [
    ("GachaID", int), ("YokaiID", int)])

YwpMstItem = _mk("YwpMstItem", [
    ("ItemID", int), ("ItemType", int), ("ItemName", str), ("ItemParam", int),
    ("Unk0", int), ("ItemDescription", str), ("ItemIconPath", str),
    ("Unk1", int), ("Unk2", int)])

YwpMstYoukaiBonusEffect = _mk("YwpMstYoukaiBonusEffect", [("YoukaiID", int)])

YwpMstYoukaiEnemyParam = _mk("YwpMstYoukaiEnemyParam", [
    ("EnemySetID", int), ("YoukaiID", int), ("YoukaiHP", int),
    ("YoukaiAttack", int), ("YoukaiActionTurn", int)])

YwpMstYoukaiLegendRelease = _mk("YwpMstYoukaiLegendRelease", [
    ("LegendYokaiID", int), ("Yokai1ID", int), ("Yokai2ID", int),
    ("Yokai3ID", int), ("Yokai4ID", int), ("Yokai5ID", int), ("Yokai6ID", int),
    ("Yokai1Hint", str), ("Yokai2Hint", str), ("Yokai3Hint", str),
    ("Yokai4Hint", str), ("Yokai5Hint", str), ("Yokai6Hint", str)])

YwpMstYoukaiLevelOpen = _mk("YwpMstYoukaiLevelOpen", [
    ("Level", int), ("RarityType", int), ("YmoneyCost", int),
    ("YpointCost", int), ("DiscountId", int)])

YwpMstYoukaiSkill = _mk("YwpMstYoukaiSkill", [
    ("SoultID", int), ("SoultName", str), ("SoultType", int),
    ("SoultDescription", str), ("SoultProperty1", int), ("SoultProperty2", int),
    ("Soult3DAnimName", str), ("Soult2DAnimName", str)])

YwpMstYoukaiSkillLevel = _mk("YwpMstYoukaiSkillLevel", [
    ("YoukaiID", int), ("SoultLevel", int), ("DisplayName", str),
    ("Unk0", int), ("SoultPt", int), ("MaxUseCount", int), ("Unk1", int),
    ("Unk2", int), ("Unk3", int), ("Unk4", int), ("Unk5", int),
    ("SoultStatsDict", str), ("Unk7", float)])

YwpMstMission = _mk("YwpMstMission", [
    ("MissionID", int), ("Unk1", int), ("MissionName", str),
    ("MissionDescription", str), ("Unk2", str), ("Unk3", str), ("Unk4", int),
    ("Unk5", int), ("Unk6", int), ("Unk7", int), ("Unk8", int),
    ("MissionType", int), ("Unk9", int), ("Unk10", int), ("Unk11", int),
    ("RewardName", str), ("RewardType", int), ("RewardID", int),
    ("YMoneySpiritCount", int), ("Unk14", int)])

YwpMstShopHitodamaRow = _mk("YwpMstShopHitodamaRow", [
    ("BonusCount", int), ("Description", str), ("GoodsID", int),
    ("LimitCount", int), ("Name", str), ("Price", int), ("SellCount", int),
    ("Sort", int)])

LotYoukaiInfoRow = _mk("LotYoukaiInfoRow", [
    ("LotPattern", str), ("LotResult", str)])

TutorialEntryRow = _mk("TutorialEntryRow", [
    ("TutorialType", int), ("TutorialId", int), ("TutorialStatus", int),
    ("FirstClear", int)])


def skill_level_get_befriender_pt(entry) -> int:
    if not entry.SoultStatsDict:
        return entry.SoultPt
    return int(dict_parse(entry.SoultStatsDict)["friendlyUpProb"])


def dict_parse(inp: str) -> dict[str, str]:
    out = {}
    for pair in inp.split(','):
        if not pair:
            continue
        kv = pair.split(':', 1)
        if len(kv) == 2:
            out[kv[0].strip()] = kv[1].strip()
    return out
