"""wall / slab 命令の描画。基礎の立上り(壁)・底盤/地中梁(スラブ)を配置する。

立上りは ``vs.Wall`` で壁オブジェクトを、底盤・地中梁は外形ポリゴンから
``vs.CreateSlab`` でスラブオブジェクトを生成する。いずれも高さ基準を
``SetObjectStoryBound`` でストーリレベルにバインドする(梁・柱と同じ規約)。
"""
from __future__ import annotations

import vs

from ..document import SlabCommand, WallCommand


def draw_wall(command: WallCommand) -> None:
    """wall 命令 1 件を壁オブジェクトとして描画する。

    壁厚を ``DoubLines`` で設定してから ``Wall`` で壁芯線から壁を生成し、
    下端(始端=0)・上端(終端=1)の高さ基準をストーリレベルにバインドする
    (boundType=2=Story)。壁が生成できない場合は壁芯の直線にフォールバックする。
    """
    x1, y1 = command['start']
    x2, y2 = command['end']

    vs.DoubLines(command['thickness'])
    vs.Wall(x1, y1, x2, y2)
    obj = vs.LNewObj()
    if obj != vs.Handle(0):
        vs.SetClass(obj, command['class'])
        bottom = command['bottom_bound']
        top = command['top_bound']
        vs.SetObjectStoryBound(
            obj, 0, 2, bottom['story_offset'], bottom['level'], bottom['offset'])
        vs.SetObjectStoryBound(
            obj, 1, 2, top['story_offset'], top['level'], top['offset'])
        vs.ResetObject(obj)
    else:
        # フォールバック: 壁芯の直線
        vs.MoveTo(x1, y1)
        vs.LineTo(x2, y2)
        fallback_line = vs.LNewObj()
        vs.SetClass(fallback_line, command['class'])


def draw_slab(command: SlabCommand) -> None:
    """slab 命令 1 件をスラブオブジェクトとして描画する。

    外形ポリゴンを閉じた多角形として作成し、``CreateSlab`` でスラブにする。
    スラブ厚を ``SetSlabHeight`` で設定し、天端の高さ基準を底盤天端レベルに
    バインドする。スラブが生成できない場合は外形ポリゴンにフォールバックする。
    """
    boundary = command['boundary']

    vs.ClosePoly()
    vs.BeginPoly()
    vs.MoveTo(boundary[0][0], boundary[0][1])
    for point in boundary[1:]:
        vs.LineTo(point[0], point[1])
    vs.EndPoly()
    poly_h = vs.LNewObj()

    slab = vs.CreateSlab(poly_h)
    if slab != vs.Handle(0):
        vs.SetClass(slab, command['class'])
        vs.SetSlabHeight(slab, command['thickness'])
        bound = command['bound']
        vs.SetObjectStoryBound(
            slab, 0, 2, bound['story_offset'], bound['level'], bound['offset'])
        vs.ResetObject(slab)
    else:
        # フォールバック: 外形ポリゴン
        vs.SetClass(poly_h, command['class'])


def execute_walls(commands: list[WallCommand]) -> int:
    """wall 命令のリストを描画し、配置数を返す。

    配置先レイヤが存在しない命令はスキップする(レイヤは story 命令が生成する)。
    """
    count = 0
    for command in commands:
        layer = command['layer']
        if vs.GetObject(layer) == vs.Handle(0):
            continue
        vs.Layer(layer)
        draw_wall(command)
        count += 1
    return count


def execute_slabs(commands: list[SlabCommand]) -> int:
    """slab 命令のリストを描画し、配置数を返す。

    配置先レイヤが存在しない命令はスキップする(レイヤは story 命令が生成する)。
    """
    count = 0
    for command in commands:
        layer = command['layer']
        if vs.GetObject(layer) == vs.Handle(0):
            continue
        vs.Layer(layer)
        draw_slab(command)
        count += 1
    return count
