# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## このリポジトリについて

**ホームズ君構造EX** から出力した木造軸組工法建築物の IFC ファイルをパースし、VectorWorks のオブジェクトに変換して配置することに特化した VectorWorks プラグインスクリプトです。

現在実装済みの機能は以下の通りです。

- グリッド線（通り芯）のインポート
- ストーリ・ストーリレベル・デザインレイヤの自動生成

今後以下の要素のインポートも追加する予定です。

- 柱・梁
- 筋交い・面材

## パッケージ構造

```
src/
    vectorworks_plugin_import_ifc_homeskz/   # pip インストール可能なパッケージ本体
        __init__.py           # run() を公開 (ファイル選択 → ストーリ／通り芯の順で実行)
        grid.py               # グリッド線インポートのロジック
        story.py              # ストーリ・ストーリレベル・デザインレイヤ生成のロジック
main.py                      # VectorWorks から呼び出すラッパースクリプト
tests/                       # pytest 用テスト (CI は vs.py スタブを GitHub からダウンロード)
pyproject.toml               # パッケージメタデータ
```

## スクリプトの実行方法

このスクリプトは単独の Python プログラムとして動作しません。**VectorWorks 内でプラグインスクリプトとして実行する必要があります**。`vs` モジュールは VectorWorks 独自の Python スクリプト API であり、pip でインストールすることはできません。

テストは VectorWorks の公式 `vs.py` スタブをモック対象として `pytest` で実行します（`.github/workflows/test.yml` 参照）。

## 外部ライブラリの利用方法

VectorWorks の組み込み Python は pip パッケージを標準では参照しませんが、Python Externals フォルダは VectorWorks が自動的に `sys.path` に追加します。このため以下の手順だけで外部ライブラリを利用できます。

1. `pip install --target <Python Externals フォルダ> .` でパッケージ（および依存ライブラリ）を Python Externals フォルダにインストールする。
2. VectorWorks から呼び出される `main.py`（ラッパー）が `vectorworks_plugin_import_ifc_homeskz.run()` を呼び出す。

Python Externals フォルダのパスは OS・VectorWorks のバージョンによって異なります（詳細は `README.md` 参照）。新しい外部ライブラリへの依存を追加するときは `pyproject.toml` の `[project] dependencies` に記載してください。

## IFC 解析の方針

IFC の解析には **`ifcopenshell`** を利用します。生の STEP テキストの正規表現マッチではなく、エンティティと属性を辿る形でデータを抽出します。

## スクリプトの処理フロー

`vectorworks_plugin_import_ifc_homeskz.run()` は以下の順で処理を行います。

1. **ファイル選択** — `vs.GetFileN()` でファイルダイアログを開き `.ifc` を選択。
2. **IFC オープン** — `ifcopenshell.open(filepath)` でファイルを読み込む。
3. **ストーリ・レイヤ設定** — `story.import_stories(ifc_file)` を呼び、ストーリ・ストーリレベル・デザインレイヤを生成。
4. **通り芯描画** — `grid.import_grids(ifc_file)` を呼び、`共通` レイヤに `GridAxis` オブジェクトを配置。
5. **完了ダイアログ** — `vs.AlrtDialog` で結果を表示。

### grid.py: 通り芯インポート

- `IfcGridAxis` を走査し `AxisCurve`（`IfcPolyline`）の端点を取得。
- ソート済みタプルキーで同一ジオメトリの重複線を除去。
- バウンディングボックスの中心 `(center_x, center_y)` でセンタリングし VectorWorks 原点付近に描画。
- 各線を `vs.CreateCustomObjectPath('GridAxis', ...)` で生成。失敗時は通常の線にフォールバック。
- レイヤ: `共通`（存在しなければ作成）。クラスは `X` 始まりなら `X通り`、`Y` 始まりなら `Y通り`、それ以外は線の方向で判定。

### story.py: ストーリ・レイヤ設定

ホームズ君 IFC の高さ表現ルールを利用してストーリを構築します。

- `IfcBuildingStorey.Elevation` がそのまま VectorWorks の**ストーリ高さ**になります（例: `1FL=473.0`, `2FL=3273.0`, `RFL=5973.0`）。
- 最上階以外の階では、`IfcRelContainedInSpatialStructure` を辿って `IfcColumn` または `IfcSlab` を 1 つ見つけ、そのローカル配置の Z 座標（負値、例: `-48.0`, `-36.0`）を**横架材天端**の相対オフセットとして使用します。
- ストーリ名は `1階`, `2階`, ..., `屋根`（最上階は常に `屋根`）。
- デザインレイヤ名は `1-FL`, `1-横架材天端`, `2-FL`, `2-横架材天端`, ..., `屋根-軒高`。
- ストーリレベル: 一般階は `FL`(0) と `横架材天端`(負値)、最上階は `軒高`(0) のみ。

レイヤとストーリの紐付け順序が結果に影響するため、`create_story_layer()` は次の順で呼び出します（順序変更不可）。

1. `vs.CreateLayer`
2. `vs.SetLayerLevelType`
3. `vs.AssociateLayerWithStory`（ここでレイヤの座標系がストーリ基準に切り替わる）
4. `vs.AddStoryLevel`
5. `vs.SetLayerElevation`（**最後**に呼んで相対高さを強制上書き）

## VectorWorks のレイヤとクラスの規則

- **通り芯のレイヤ**: すべて `共通` レイヤに配置。存在しない場合はスクリプトが自動作成。
- **通り芯のクラス**（X 通り・Y 通りの判定）:
  - 名前が `X` で始まる（大文字小文字不問）→ クラス `01作図-01線-01基準線-01通り芯-X通り`
  - 名前が `Y` で始まる（大文字小文字不問）→ クラス `01作図-01線-01基準線-01通り芯-Y通り`
  - それ以外: `|Δx| < |Δy|` の線（垂直に近い）を X 通り、それ以外を Y 通りとして扱う
- **GridAxis レコードフィールド**: `Label`（IFC から取得した軸名）、`ShowBubbleAt` = `"Start Point"`
