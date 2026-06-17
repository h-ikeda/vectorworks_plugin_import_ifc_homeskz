"""診断用: 選択中の柱・間柱オブジェクトの全レコード・全フィールドと値を出力する。

使い方:
1. VW で柱頭金物・柱脚金物を UI で設定した柱・間柱を 1 本配置する。
2. そのオブジェクトを 1 つだけ選択する。
3. このスクリプトを実行する。ホームフォルダの ``pillar_fields_dump.txt`` に
   レコード名・フィールド名・現在値の一覧が書き出される。
   金物関連(名前か値に '金物' / 'Hard' / 'ほぞ' を含む)行は AlrtDialog でも表示する。
"""
import os

import vs


def _dump() -> None:
    obj = vs.FSActLayer()
    if obj == vs.Handle(0):
        vs.AlrtDialog('柱・間柱オブジェクトを 1 つ選択してから実行してください。')
        return

    lines: list[str] = []
    highlights: list[str] = []

    num_records = vs.NumRecords(obj)
    lines.append(f'NumRecords = {num_records}')
    for ri in range(1, num_records + 1):
        rec = vs.GetRecord(obj, ri)
        rec_name = vs.GetName(rec)
        num_fields = vs.NumFields(rec)
        lines.append(f'--- Record[{ri}] "{rec_name}" ({num_fields} fields) ---')
        for fi in range(1, num_fields + 1):
            fld_name = vs.GetFldName(rec, fi)
            value = vs.GetRField(obj, rec_name, fld_name)
            entry = f'{fi}: {fld_name} = {value!r}'
            lines.append(entry)
            joined = f'{fld_name}{value}'
            if any(k in joined for k in ('金物', 'Hard', 'ほぞ', 'プレート', 'かど')):
                highlights.append(f'[{rec_name}] {entry}')

    out_path = os.path.join(os.path.expanduser('~'), 'pillar_fields_dump.txt')
    with open(out_path, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(lines))

    summary = '\n'.join(highlights) if highlights else '(金物らしきフィールドが見つかりませんでした)'
    vs.AlrtDialog(f'出力: {out_path}\n\n--- 金物候補 ---\n{summary}')


_dump()
