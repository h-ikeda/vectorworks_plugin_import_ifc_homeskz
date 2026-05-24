import vs
import re

def import_ifc_grid_with_layers_and_classes():
    # 1. ファイル選択
    ok, filepath = vs.GetFileN("IFCファイルを選択してください", "", "ifc")
    if not ok:
        vs.AlrtDialog("キャンセルされました。")
        return

    try:
        # ファイルの読み込み
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
            
        vs.Message("IFCデータを解析中...")
        
        content = content.replace('\n', '').replace('\r', '')
        statements = content.split(';')
        
        points = {}
        polylines = {}
        grid_axes = {}

        pt_pattern = re.compile(r'#(\d+)\s*=\s*IFCCARTESIANPOINT\(\((.*?)\)\)')
        poly_pattern = re.compile(r'#(\d+)\s*=\s*IFCPOLYLINE\(\((.*?)\)\)')
        axis_pattern = re.compile(r"#(\d+)\s*=\s*IFCGRIDAXIS\('(.*?)',#(\d+),.*\)")

        # 2. データの紐付け解析
        for stmt in statements:
            if 'IFCCARTESIANPOINT' in stmt:
                match = pt_pattern.search(stmt)
                if match:
                    id_val = int(match.group(1))
                    coords = match.group(2).split(',')
                    try:
                        x = float(coords[0].strip())
                        y = float(coords[1].strip())
                        points[id_val] = (x, y)
                    except ValueError:
                        pass
            
            elif 'IFCPOLYLINE' in stmt:
                match = poly_pattern.search(stmt)
                if match:
                    id_val = int(match.group(1))
                    pt_ids_str = match.group(2).replace('#', '').split(',')
                    pt_ids = [int(p.strip()) for p in pt_ids_str if p.strip().isdigit()]
                    polylines[id_val] = pt_ids
            
            elif 'IFCGRIDAXIS' in stmt:
                match = axis_pattern.search(stmt)
                if match:
                    id_val = int(match.group(1))
                    name = match.group(2)
                    poly_id = int(match.group(3))
                    grid_axes[id_val] = {'name': name, 'poly_id': poly_id}

        # 3. 描画予定の線リストを作成し、全体の最小・最大座標（境界）を計算
        lines_to_draw = []
        drawn_keys = set()
        
        min_x, max_x = float('inf'), float('-inf')
        min_y, max_y = float('inf'), float('-inf')

        for axis_id, axis_data in grid_axes.items():
            name = axis_data['name']
            poly_id = axis_data['poly_id']
            
            if poly_id in polylines:
                pt_ids = polylines[poly_id]
                
                for i in range(len(pt_ids) - 1):
                    pt1_id = pt_ids[i]
                    pt2_id = pt_ids[i+1]
                    
                    if pt1_id in points and pt2_id in points:
                        x1, y1 = points[pt1_id]
                        x2, y2 = points[pt2_id]
                        
                        line_key = tuple(sorted(((x1, y1), (x2, y2))))
                        if line_key in drawn_keys:
                            continue
                        drawn_keys.add(line_key)
                        
                        min_x = min(min_x, x1, x2)
                        max_x = max(max_x, x1, x2)
                        min_y = min(min_y, y1, y2)
                        max_y = max(max_y, y1, y2)
                        
                        lines_to_draw.append((x1, y1, x2, y2, name))

        if lines_to_draw:
            center_x = (min_x + max_x) / 2.0
            center_y = (min_y + max_y) / 2.0
        else:
            center_x = 0.0
            center_y = 0.0

        # --- 【新規】レイヤの設定 ---
        target_layer = '共通'
        layer_handle = vs.GetObject(target_layer)
        if layer_handle == vs.Handle(0):
            # レイヤが存在しない場合は新規作成（1 = デザインレイヤ）
            layer_handle = vs.CreateLayer(target_layer, 1)
        # 「共通」レイヤをアクティブにする（これ以降の描画はこのレイヤに入ります）
        vs.Layer(target_layer)

        # --- 【新規】クラス名の定義 ---
        class_x = '01作図-01線-01基準線-01通り芯-X通り'
        class_y = '01作図-01線-01基準線-01通り芯-Y通り'

        # 4. グリッド線（GridAxis）ツールとして描画
        count = 0
        for x1, y1, x2, y2, name in lines_to_draw:
            cx1, cy1 = x1 - center_x, y1 - center_y
            cx2, cy2 = x2 - center_x, y2 - center_y
            
            # --- 【新規】X通り・Y通りのクラス判定ロジック ---
            if name.upper().startswith('X'):
                current_class = class_x
            elif name.upper().startswith('Y'):
                current_class = class_y
            else:
                # 名前で判定できない場合：垂直に近い線（X座標の差が小さい線）をX通りとする
                if abs(cx1 - cx2) < abs(cy1 - cy2):
                    current_class = class_x
                else:
                    current_class = class_y
            
            # パス（基準となる線）の作成
            vs.BeginPoly()
            vs.MoveTo(cx1, cy1)
            vs.LineTo(cx2, cy2)
            vs.EndPoly()
            path_handle = vs.LNewObj()
            
            # プロファイル（空のグループ）
            vs.BeginGroup()
            vs.EndGroup()
            profile_handle = vs.LNewObj()
            
            # グリッド線（GridAxis）オブジェクトの生成
            grid_obj = vs.CreateCustomObjectPath('GridAxis', path_handle, profile_handle)
            
            if grid_obj != vs.Handle(0):
                # オブジェクトにクラスを適用（クラスが存在しない場合は自動生成されます）
                vs.SetClass(grid_obj, current_class)
                
                # プロパティ（レコード）に名前などを書き込む
                vs.SetRField(grid_obj, 'GridAxis', 'Label', name)
                vs.SetRField(grid_obj, 'GridAxis', 'ShowBubbleAt', 'Start Point')
                
                vs.ResetObject(grid_obj)
                count += 1
            else:
                # フォールバック（単なる線）
                vs.MoveTo(cx1, cy1)
                vs.LineTo(cx2, cy2)
                fallback_line = vs.LNewObj()
                vs.SetClass(fallback_line, current_class)
                count += 1
        
        vs.ClrMessage()
        vs.AlrtDialog(f"読込完了: 「{target_layer}」レイヤに、{count} 本の通り芯をそれぞれのクラスに振り分けて配置しました。")
        
    except Exception as e:
        vs.ClrMessage()
        vs.AlrtDialog(f"エラーが発生しました: {str(e)}")

# 実行
import_ifc_grid_with_layers_and_classes()
