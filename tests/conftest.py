import sys
import os

# VectorWorks 公式スタブ (vs.py) を tests/ ディレクトリからインポートできるようにする。
# CI 環境では GitHub Actions ワークフローが curl でダウンロードする。
sys.path.insert(0, os.path.dirname(__file__))

# クラッシュ診断用トレース (tracing.py) はテスト中は無効化する(ホームディレクトリへ
# ログを書き込まないようにする)。トレース自体の動作は tests/test_trace.py が
# 一時ディレクトリに切り替えた上で検証する。
from vectorworks_plugin_import_ifc_homeskz import tracing as _trace  # noqa: E402

_trace.TRACE_ENABLED = False
