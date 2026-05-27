import ifcopenshell

import vs

from .grid import TARGET_LAYER, import_grids
from .story import import_stories

__all__ = ['run', 'import_grids', 'import_stories']


def run():
    ok, filepath = vs.GetFileN('IFCファイルを選択してください', '', 'ifc')
    if not ok:
        vs.AlrtDialog('キャンセルされました。')
        return

    try:
        vs.Message('IFCデータを解析中...')

        ifc_file = ifcopenshell.open(filepath)

        story_count, story_diagnostics = import_stories(ifc_file)
        grid_count = import_grids(ifc_file)

        vs.ClrMessage()

        # 診断: 実機での値が意図通り設定されているか表示
        diag_lines = []
        for story_name, intended, actual, layers in story_diagnostics:
            diag_lines.append(f'{story_name}: 指定={intended} / 実値={actual}')
            for lname, lz_intended, lz_actual in layers:
                diag_lines.append(f'  {lname}: 指定={lz_intended} / 実値={lz_actual}')

        msg = (
            f'読込完了: {story_count} 階のストーリ・ストーリレベル・デザインレイヤを設定し、'
            f'「{TARGET_LAYER}」レイヤに {grid_count} 本の通り芯を配置しました。\n\n'
            f'--- 高さ設定の診断 ---\n' + '\n'.join(diag_lines)
        )
        vs.AlrtDialog(msg)

    except Exception as e:
        vs.ClrMessage()
        vs.AlrtDialog(f'エラーが発生しました: {str(e)}')
