import sys
import os

# VectorWorks 公式スタブ (vs.py) を tests/ ディレクトリからインポートできるようにする。
# CI 環境では GitHub Actions ワークフローが curl でダウンロードする。
sys.path.insert(0, os.path.dirname(__file__))
