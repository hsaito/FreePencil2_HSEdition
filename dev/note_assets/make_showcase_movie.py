"""いろんな系統のモデルを並べて、線画の出来を見せる動画を作る。

自動しきい値の分類(メカ/有機/交差/リグ/滑面)がばらけるように選び、
同じ高さに揃えて台の上へ一列に置き、カメラが横に流しながら進む。
各モデルの足元に系統名と採用された角度を立体文字で出す。

  blender -b --factory-startup --python make_showcase_movie.py -- \
      --out <dir> [--frames 450] [--res 1920] [--fps 15]
"""
from __future__ import annotations

import json
import math
import re
import sys
import time
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "batch"))
import fp_batch      # noqa: E402
import scan_models   # noqa: E402

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(n, d=None):
    return ARGV[ARGV.index(n) + 1] if n in ARGV else d


OUT = Path(arg("--out", str(HERE / "out" / "showcase"))).resolve()
OUT.mkdir(parents=True, exist_ok=True)
FRAMES = int(arg("--frames", "450"))
RES = int(arg("--res", "1920"))
SS = int(arg("--ss", "2"))        # 2倍で描いて箱縮小(アドオンの細線化は使わない)
SAMPLE = int(arg("--sample", "0"))   # >0 なら等間隔にN枚だけ描いて終わる
ONLY = int(arg("--only", "0"))       # >0 ならそのフレームだけ描いて終わる
LOGO_RU = int(arg("--logo-ru", "3"))
LOGO_EXTRUDE = float(arg("--logo-extrude", "0.30"))
LOGO_BEVEL = float(arg("--logo-bevel", "0.055"))
LOGO_SEG = int(arg("--logo-seg", "0"))
      # 縁に段差を刻むベベルモディファイア。試したが逆効果だったので既定は
      # 0(無効)。角が丸まって二面角がしきい値を下回り、線が全部消えた
LOGO_SIDE = float(arg("--logo-side", "4.2"))    # 最後に横へ回り込む量(m)
LOGO_DEG = float(arg("--logo-deg", "20.0"))     # ロゴだけ手動で使う角度
MIN_FACES = int(arg("--min-faces", "15000"))    # これ未満は線が出ないので外す
LOGO_BEVEL_W = float(arg("--logo-bevel-w", "0.04"))
FPS = int(arg("--fps", "15"))
RELIEF = float(arg("--relief", "0.5"))
FLOOR = float(arg("--floor", "0.25"))
LIMIT = int(arg("--limit", "40"))
PICK = int(arg("--pick", "14"))
LIGHT_W = float(arg("--light", "400.0"))   # 頭上エリアライト(W)
FILL_W = float(arg("--fill", "260.0"))     # 通路照明1灯あたり(W)
TURNS = float(arg("--turns", "1.0"))       # 尺の間に何回転させるか
SHADOW_N = int(arg("--shadow-lights", "6"))  # 影を落とす灯の数
T0 = time.time()

# 奥へ向かって左右交互に並べ、カメラは中央を前進する。横スクロールだと
# 全身が入らないうえ、先にあるものが見えない。奥行き方向に並べると
# 「いま見ているもの」を正面から全身で捉えつつ、その先も画に入る。
STEP = float(arg("--step", "9.0"))     # 奥行き方向の間隔
SIDE = float(arg("--side", "3.3"))     # 中央からの左右オフセット
TARGET_SIZE = float(arg("--size", "3.6"))
                    # 最大辺を揃える(高さではなく最大辺。細長い車と
                    # 背の高いメカが同じ大きさに見えるようにする)
PED_H = 0.5         # 台の高さ
# ホールの寸法は照明の高さと連動するのでここに置く。天井を下げたのに
# ライトの高さを直さず、灯が梁の中に埋まっていた
HALL_W = float(arg("--hall-w", "7.5"))    # 通路の半幅
HALL_H = float(arg("--hall-h", "6.0"))    # 天井高
LIGHT_Z = HALL_H - 1.3                    # 梁(天井から0.7m)より下に吊る
LABEL_W = float(arg("--label-w", "2.4"))
                    # ラベルの最大幅。台が 2.3m 角なので、それに揃える。
                    # 4.2m にしていたら実測 3.9m が素通りして画面を横切った


def say(m):
    print(f"@@@ {time.time() - T0:7.1f}s  {m}", flush=True)


# 必ず入れたいもの / 外したいもの。
# kaino-mech はこの案件で「メカの基準」として使ってきたモデル
# (HANDOFF.md「メカ(kaino-mech)」、回帰の基準 ink 0.03767)。
SKIP = ("012_batmobile",)          # 面が粗く、線画の見本にならない

# 展示するモデルは手で選ぶ。自動分類のバランスで機械的に選んでいたら、
# 靴・エアコン・ドア・ベッド2台・サッカーボールなど地味な小物が14体中7体を
# 占めた。線画の見本なので「線が多くて、一目で何か分かる」ものを並べる。
# 順番がそのまま奥行きの並び順(先頭がカメラに一番近い)
SHOWCASE = [
    "053_kaino-school-military-mech",   # 主役のメカ
    "055_lamborghini-revuelto",         # スーパーカー
    "052_jnr-c62-1-steam-locomotive",   # 蒸気機関車(配管の線が濃い)
    "004_anime-girl",                   # キャラクター
    "047_heavy-zaku-mkll",              # もう1体メカ
    "032_dutch_ship_medium",            # 帆船(索具の線が効く)
    "063_mclaren_720s",                 # スーパーカー
    # 034_eiffel_tower_1892 は中身が塔ではなく古い電話機のような機械だった
    # (アセット側の名前違い)。ラベルと合わないので使わない
    "088_tank",                         # 戦車
    "082_space_scavenger",              # SFキャラ
    "046_heavy-light-cargo-plane",      # 輸送機
    "076_robot-kuka-quantec",           # 産業用ロボット
    "040_full-skeleton-human",          # 骨格
    "048_hollowbody_electrig_guitar",   # ギター
    # 以下は予備。上のどれかが面数不足や配置失敗で弾かれたときに繰り上がる
    "051_jnr-c58-steam-locomotive",
    "056_lancia-delta-integrale-evo",
    "086_stylized-male-character-model-frank",
    "049_hyundai-veloster-sport-car",
    "058_loli_anime_girl",
    "041_futuristic_ct___mrt_machine_doctor",
]


def choose(models, autotype_json: Path):
    """SHOWCASE の並び順どおりに選ぶ。分類名は表示に使わないので "" を返す。"""
    # ここでは PICK 件に絞らない。面数不足や配置失敗で弾かれる分があるので、
    # 候補は全部返して、実際に置けた数を build 側で数える
    have = {m["name"]: m["name"] for m in models}
    picked, missing = [], []
    for want in SHOWCASE:
        hit = next((n for n in have if n.startswith(want)), None)
        if hit is None or hit.startswith(SKIP):
            missing.append(want)
            continue
        picked.append((hit, ""))
    if missing:
        say(f"見つからず飛ばした: {', '.join(missing)}")
    say(f"候補 {len(picked)} 体 (このうち置けた先頭 {PICK} 体を展示)")
    return picked


def load_and_place(models, name, branch, px, py, phase=0.0):
    entry = next((m for m in models.values() if m["name"].startswith(name)),
                 None)
    if entry is None:
        return None
    meshes, others = fp_batch.append_objects(Path(entry["path"]))
    if not meshes:
        return None
    objs = meshes + others
    faces0 = sum(len(o.data.polygons) for o in meshes)
    if faces0 < MIN_FACES:
        # 面が少ないモデルは線が出ず、白い塊にしかならない。実測: 輸送機は
        # 3,759面で、画面の真ん中に何も描かれない白い物体として写った
        say(f"  {name[:30]:<32} 面が少ないので外す ({faces0:,}面)")
        for o in objs:
            bpy.data.objects.remove(o, do_unlink=True)
        return None
    # append 直後は matrix_world が未評価のことがあり、親子付きのモデルで
    # 寸法を取り違える。必ず評価してから測る
    bpy.context.view_layer.update()
    pts = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
    mn = Vector((min(p[i] for p in pts) for i in range(3)))
    mx = Vector((max(p[i] for p in pts) for i in range(3)))
    size = mx - mn
    # 最大辺で揃える。高さで揃えると、長い車が横に大きくはみ出す
    k = TARGET_SIZE / max(max(size.x, size.y, size.z), 1e-6)

    root = bpy.data.objects.new(f"SHOW_{name[:12]}", None)
    bpy.context.scene.collection.objects.link(root)
    for o in objs:
        if o.parent is None:
            o.parent = root
            o.matrix_parent_inverse = root.matrix_world.inverted()
    root.scale = (k, k, k)
    root.location = (px - (mn.x + mx.x) * 0.5 * k,
                     py - (mn.y + mx.y) * 0.5 * k,
                     PED_H - mn.z * k)
    # 台の上でゆっくり回す。全部が同じ向きだと機械的に見えるので、
    # 開始角を1体ずつずらす
    # Blender の「前」は -Y(正面図が +Y 方向から見る)。カメラは +Y 側から
    # 来るので、180 足さないと全モデルが背中を向ける
    base = math.radians(180) + math.radians(-28 if px > 0 else 28) + phase
    turns = TURNS * (1.0 if px > 0 else -1.0)      # 左右で逆回り
    root.rotation_euler = (0.0, 0.0, base)
    for f, frac in ((1, 0.0), (FRAMES, 1.0)):
        root.rotation_euler = (0.0, 0.0,
                               base + turns * 2.0 * math.pi * frac)
        root.keyframe_insert("rotation_euler", frame=f)
    if root.animation_data and root.animation_data.action:
        for fc in root.animation_data.action.fcurves:
            for kp in fc.keyframe_points:
                kp.interpolation = "LINEAR"   # 等速。加減速すると目に付く

    # 置いた結果を測り直して検証する。エッフェル塔が台を空にしたまま天井へ
    # 巨大化して浮いていた。原因を1体ずつ潰すより、置いた後に実寸を見て
    # 合わないものを外すほうが確実
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    wp = []
    for o in meshes:
        ev = o.evaluated_get(dg)
        wp += [ev.matrix_world @ Vector(c) for c in ev.bound_box]
    wmn = Vector((min(p[i] for p in wp) for i in range(3)))
    wmx = Vector((max(p[i] for p in wp) for i in range(3)))
    got = max((wmx - wmn).x, (wmx - wmn).y, (wmx - wmn).z)
    cx, cy = (wmn.x + wmx.x) * 0.5, (wmn.y + wmx.y) * 0.5
    bad = (got > TARGET_SIZE * 1.6 or got < TARGET_SIZE * 0.4
           or abs(cx - px) > 3.0 or abs(cy - py) > 3.0
           or wmn.z < -0.5 or wmn.z > PED_H + 2.0)
    if bad:
        say(f"  {name[:30]:<32} 配置に失敗したので外す "
            f"(最大辺 {got:.1f}m 中心 {cx:.1f},{cy:.1f} 底 {wmn.z:.1f})")
        for o in objs:
            bpy.data.objects.remove(o, do_unlink=True)
        bpy.data.objects.remove(root, do_unlink=True)
        return None

    # 台
    bpy.ops.mesh.primitive_cube_add(size=1)
    ped = bpy.context.object
    ped.name = f"PED_{name[:10]}"
    ped.scale = (2.3, 2.3, PED_H)
    ped.location = (px, py, PED_H * 0.5)

    say(f"  {name[:30]:<32} {faces0:>8,}面  ({px:>5.1f}, {py:>6.1f}) "
        f"最大辺 {got:.1f}m")
    return faces0


def display_name(folder):
    """"006_audi_r8_v10_2K_64ad961c-47..." → "AUDI R8 V10"。

    先頭の連番と、末尾の解像度タグ・UUID を落として読める名前にする。
    """
    s = re.sub(r"^\d+_", "", folder)
    parts = []
    for w in re.split(r"[_\-]", s):
        if not w:
            continue
        if re.fullmatch(r"[0-9a-f]{6,}", w):    # UUID の断片
            break
        if re.fullmatch(r"\d+[kK]", w):         # 2K / 1K
            continue
        parts.append(w)
    return " ".join(parts).upper()[:22] or folder[:22]


def add_label(text, px, py, size=0.5):
    cur = bpy.data.curves.new("lbl", type="FONT")
    cur.body = text
    cur.align_x = "CENTER"
    cur.align_y = "BOTTOM"
    cur.extrude = 0.05
    cur.bevel_depth = 0.012
    o = bpy.data.objects.new(f"LBL_{text[:8]}", cur)
    bpy.context.scene.collection.objects.link(o)
    # 台(2.3m角)の手前の縁に置く。2.6m 手前だとカメラに近すぎて大写しになる
    o.location = (px, py + 1.3, PED_H + 0.06)
    # カメラは +Y から -Y へ進むので、文字は +Y を向かせる。X に +90 だけだと
    # 法線が -Y になり、カメラは裏面を見る(押し出し文字は裏から見ると鏡像に
    # なる)。Z に 180 を足して向きだけ反転させる(X だけ符号を変えると
    # 上下がひっくり返る)
    o.rotation_euler = (math.radians(74), 0.0, math.radians(180))
    o.scale = (size, size, size)
    bpy.context.view_layer.objects.active = o
    bpy.ops.object.select_all(action="DESELECT")
    o.select_set(True)
    bpy.ops.object.convert(target="MESH")
    o = bpy.context.object

    # 台の幅に収める。固定サイズ 0.5 は「メカ」など2〜4文字向けで、
    # "KAINO SCHOOL MILITARY MECH" だと画面を横切っていた。実寸を測って
    # から縮める(文字数で割ると書体差で外す)。FONT カーブのままだと
    # bound_box が空なので、必ずメッシュ化した後で測る
    bpy.context.view_layer.update()
    pts = [o.matrix_world @ Vector(c) for c in o.bound_box]
    w = max(p.x for p in pts) - min(p.x for p in pts)
    if w > LABEL_W:
        k = size * LABEL_W / w
        o.scale = (k, k, k)
    return o


def add_logo(py, height=3.2):
    cur = bpy.data.curves.new("LogoText", type="FONT")
    cur.body = "FreePencil2"
    cur.align_x = "CENTER"
    cur.align_y = "BOTTOM"
    # なめらかな押し出し文字は内部に面の変化が無く、塗り分ける対象が輪郭
    # しかない。曲線分割を 3→16 まで振っても輪郭線しか出ず、白い塊のまま
    # だった(実測 ink: ru3 0.0125 / ru12 0.0065 / ru16深 0.0085 ―― 細かく
    # するほど減る。ru3 が多いのはポリゴンのガタつきが線になっていただけで
    # 見た目は粗い)。形はきれいなまま、段差を刻んで線を作る。
    cur.extrude = LOGO_EXTRUDE
    cur.bevel_depth = LOGO_BEVEL
    cur.bevel_resolution = 0        # 0 = 平面の面取り(丸めない)
    cur.offset = -0.004             # わずかに痩せさせて面取りを効かせる
    cur.resolution_u = LOGO_RU
    o = bpy.data.objects.new("FP_LOGO", cur)
    bpy.context.scene.collection.objects.link(o)
    # +Y を向ける(add_label と同じ理由。X 90 だけだと裏面=鏡像になる)
    o.rotation_euler = (math.radians(90), 0.0, math.radians(180))
    bpy.context.view_layer.objects.active = o
    bpy.ops.object.select_all(action="DESELECT")
    o.select_set(True)
    bpy.ops.object.convert(target="MESH")
    o = bpy.context.object

    # 輪郭に沿って段差を刻む。1段ごとに面の向きが変わるので、文字の縁に
    # 平行な線が LOGO_SEG+1 本並ぶ。形は元のまま崩れない
    if LOGO_SEG > 0:
        bm = o.modifiers.new("LogoBevel", type="BEVEL")
        bm.width = LOGO_BEVEL_W
        bm.segments = LOGO_SEG
        bm.limit_method = "ANGLE"
        bm.angle_limit = math.radians(25.0)
        bm.miter_outer = "MITER_ARC"    # 角の潰れを防ぐ
        bpy.context.view_layer.objects.active = o
        bpy.ops.object.modifier_apply(modifier=bm.name)

    pts = [o.matrix_world @ Vector(c) for c in o.bound_box]
    mn = Vector((min(p[i] for p in pts) for i in range(3)))
    mx = Vector((max(p[i] for p in pts) for i in range(3)))
    # 高さで合わせると "FreePencil2" は幅 18.6m になり、通路(15m)より広くて
    # 両端が側壁に埋まっていた。幅の上限でも抑える
    k = height / max(mx.z - mn.z, 1e-6)
    w_max = HALL_W * 2.0 * 0.78
    k = min(k, w_max / max(mx.x - mn.x, 1e-6))
    o.scale = (k, k, k)
    bpy.context.view_layer.update()
    pts = [o.matrix_world @ Vector(c) for c in o.bound_box]
    mn2 = Vector((min(p[i] for p in pts) for i in range(3)))
    mx2 = Vector((max(p[i] for p in pts) for i in range(3)))
    o.location = (0.0, py, PED_H + 0.6 - mn2.z)
    w = mx2.x - mn2.x
    say(f"ロゴを y={py:.1f} に配置 ({len(o.data.polygons):,}面, 幅 {w:.1f}m)")
    return o, w


def add_area_light(px, py, watts, size=3.4, height=None,
                   shadow=True):
    """モデルの頭上に1灯ずつ。真下を向いた矩形ライト。

    太陽光1灯だと全体が均一に飛んで陰影が出ない(実測: 前回のフレームは
    75%の画素が 250 以上だった)。1体ずつ上から当てると、台の周りだけが
    明るくなって奥行きも出る。
    """
    data = bpy.data.lights.new(f"AREA_{px:.0f}_{py:.0f}", type="AREA")
    data.energy = watts
    data.shape = "RECTANGLE"
    data.size = size
    data.size_y = size
    # 15灯すべてに影を持たせると EEVEE の影バッファが溢れる
    # (実測 2579 / 2048)。影は主役の陰影づけに要るだけなので、
    # 光量の弱い灯は影を落とさない設定にして数を絞る
    data.use_shadow = shadow
    lt = bpy.data.objects.new(data.name, data)
    bpy.context.scene.collection.objects.link(lt)
    lt.location = (px, py, LIGHT_Z if height is None else height)
    lt.rotation_euler = (0.0, 0.0, 0.0)     # 既定で -Z を向く
    return lt


def add_hall(logo_y):
    """未来の博物館っぽい外装。線画で映えるよう、面は大きく数は少なく。

    細かい装飾を入れても縮小すると潰れるだけなので、
    「大きな面 + はっきりした段差」で構成する。段差の稜線がそのまま線になる。
    """
    scene = bpy.context.scene
    span = abs(logo_y) + STEP * 3.0
    y_mid = logo_y * 0.5 + STEP
    # 3m のモデルに対して幅26m・高さ10mは広すぎ、被写体が米粒になっていた。
    # 通路を絞ると、同じ画角でモデルが大きく写り、壁の稜線も近くに来る
    W = HALL_W
    H = HALL_H
    made = []

    def box(name, loc, scale, rot_z=0.0):
        bpy.ops.mesh.primitive_cube_add(size=1)
        o = bpy.context.object
        o.name = name
        o.location = loc
        o.scale = scale
        o.rotation_euler = (0.0, 0.0, rot_z)
        made.append(o)
        return o

    # 側壁。内側に一段へこませた帯を作って、水平の線を出す
    for side in (-1, 1):
        box(f"WALL_{side}", (side * W, y_mid, H * 0.5), (0.6, span, H))
        box(f"WALLBAND_{side}", (side * (W - 0.7), y_mid, H * 0.62),
            (0.5, span, 1.1))
        box(f"WALLBASE_{side}", (side * (W - 0.5), y_mid, 0.45),
            (0.7, span, 0.9))

    # 天井と、等間隔の梁。梁の間が明かり取りに見える
    box("CEIL", (0.0, y_mid, H + 0.3), (W * 2, span, 0.6))
    n_beam = int(span / (STEP * 0.5))
    for i in range(n_beam):
        y = y_mid + span * 0.5 - i * (STEP * 0.5)
        box(f"BEAM_{i:02d}", (0.0, y, H - 0.35), (W * 2, 0.55, 0.7))

    # 通路脇の柱。モデルの間に立てて、奥行きのリズムを作る
    n_col = int(span / STEP) + 1
    for i in range(n_col):
        y = y_mid + span * 0.5 - i * STEP - STEP * 0.5
        for side in (-1, 1):
            box(f"COL_{i:02d}_{side}", (side * (W - 1.8), y, H * 0.5),
                (0.7, 0.7, H))

    # 突き当たりの壁(ロゴの背面)
    box("ENDWALL", (0.0, logo_y - STEP * 1.2, H * 0.5), (W * 2, 0.6, H))
    box("ENDBAND", (0.0, logo_y - STEP * 1.15, H * 0.66), (W * 1.5, 0.5, 1.4))

    say(f"ホールを作った: {len(made)} 個 (幅 {W * 2:.0f}m / 高さ {H:.0f}m / "
        f"奥行き {span:.0f}m)")
    return made


def build(models):
    bpy.ops.wm.read_homefile(use_empty=True)
    scene = bpy.context.scene
    picked = choose(list(models.values()),
                    HERE / "out" / "autotype" / "result.json")
    total = 0
    ys = []
    # 弾かれたモデルの分だけ並びに穴が空かないよう、置けたときだけ前へ進める
    i = 0
    for name, branch in picked:
        if i >= PICK:
            break
        py = -i * STEP
        px = SIDE if i % 2 == 0 else -SIDE     # 左右交互
        f = load_and_place(models, name, branch, px, py,
                           phase=i * 0.7)
        if f is None:
            continue
        i += 1
        total += f
        ys.append(py)
        # ラベルは自動しきい値の内部分岐名(メカ/有機/rig/人工分割)を出して
        # いたが、Audi R8 が「有機」、帆船が「メカ」になり誤解を招く。
        # 分岐名は二面角分布の呼び名でしかないので、モデル名を出す
        add_label(display_name(name), px, py)
        # 影付きは先頭から数体だけ。奥は光だけ届けば十分
        add_area_light(px, py, LIGHT_W, shadow=(i < SHADOW_N))
    logo_y = (ys[-1] if ys else 0.0) - STEP * 1.5
    _, logo_w = add_logo(logo_y)

    # 床
    bpy.ops.mesh.primitive_plane_add(size=1)
    fl = bpy.context.object
    fl.name = "FLOOR"
    span = abs(logo_y) + STEP * 3
    fl.scale = (30.0, span, 1.0)
    fl.location = (0.0, logo_y * 0.5 + STEP, 0.0)

    add_hall(logo_y)

    add_area_light(0.0, logo_y, LIGHT_W * 1.4, size=6.0)

    # 通路照明。太陽1灯で補助していたが、ホールは壁・天井・突き当たりで
    # 完全に閉じているので日光は一切入らない(実測: 太陽を 0.35→1.2 に
    # 上げても平均輝度が小数4桁まで同一だった)。天井に沿って灯を並べる。
    # 影は落とさない — EEVEE の影バッファは既に満杯で、かつ間接照明の
    # 代わりなので影は不要
    n_fill = int((abs(logo_y) + STEP * 2) / (STEP * 0.75)) + 1
    for i in range(n_fill):
        y = STEP - i * STEP * 0.75
        add_area_light(0.0, y, FILL_W, size=HALL_W * 1.6, shadow=False)

    meshes = [o for o in scene.objects if o.type == "MESH"]
    say(f"並べ終わり: モデル {len(ys)} / メッシュ {len(meshes)} / "
        f"面 {total:,} / ロゴ y={logo_y:.1f} / 間隔 {STEP}m")
    return {"logo_y": logo_y, "logo_w": logo_w, "n": len(ys)}


def add_camera(info):
    """中央通路を前進する。横スクロールではないので、いま見ているものは
    正面から全身で入り、その先に並ぶものも同じ画に収まる。"""
    scene = bpy.context.scene
    cd = bpy.data.cameras.new("ShowCam")
    cd.lens = 35.0            # 広めにして全身と奥行きを同時に入れる
    cd.clip_end = 800.0
    cam = bpy.data.objects.new("ShowCam", cd)
    scene.collection.objects.link(cam)
    scene.camera = cam

    logo_y = info["logo_y"]
    LAST = 0.16
    y0 = STEP * 1.4                  # 1体目の手前から
    # ロゴが画面に収まる距離で止める。STEP*1.15(=10.4m)固定だと、幅 11m の
    # ロゴが画角 10.3m に入らず両端が切れていた。実寸から逆算する
    half_fov = math.atan(0.5 * cd.sensor_width / cd.lens)
    need = (info["logo_w"] * 0.5 * 1.18) / math.tan(half_fov)
    y1 = logo_y + max(need, STEP * 1.15)
    for f in range(FRAMES):
        t = f / max(FRAMES - 1, 1)
        y = y0 + (y1 - y0) * t
        # 通路の中央を、わずかに左右へ振りながら進む
        sway = math.sin(t * math.pi * 3.0) * 0.9
        if t < 1.0 - LAST:
            cam.location = (sway, y, 2.1)
            # 26m 先を見ると消失点ばかりが写り、脇のモデルが米粒になる。
            # 1.5体分先(=次に主役になるモデル)を見る位置まで引き寄せる
            look = Vector((sway * 0.3, y - STEP * 1.5, PED_H + 1.6))
        else:
            u = (t - (1.0 - LAST)) / LAST
            e = u * u * (3.0 - 2.0 * u)          # なめらかに寄る
            # 真正面で止めると平らな前面しか見えず、線が輪郭だけになる
            # (押し出しの側面と面取りは斜めからしか見えない)。最後に
            # 横へ回り込み、少し見上げる位置で止める
            cam.location = (sway * (1.0 - e) + LOGO_SIDE * e,
                            y, 2.1 - 0.7 * e)
            look = Vector((0.0, logo_y, PED_H + 1.9))
        d = look - cam.location
        cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
        cam.keyframe_insert("location", frame=f + 1)
        cam.keyframe_insert("rotation_euler", frame=f + 1)
    for fc in cam.animation_data.action.fcurves:
        for kp in fc.keyframe_points:
            kp.interpolation = "LINEAR"
    scene.frame_start, scene.frame_end = 1, FRAMES


def main():
    fp_batch.install_addon()
    from freepencil2 import fp_core
    models = {m["name"]: m for m in scan_models.scan(scan_models.DEFAULT_ROOT)
              }
    info = build(models)
    add_camera(info)

    scene = bpy.context.scene
    scene.fp_use_random_seed = False
    scene.fp_color_seed = 42
    scene.fp_enable_compositor_view = False
    scene.fp_auto_detect_aov = False
    scene.fp_preview_mode = 'MONO_LIGHT'
    scene.fp_mono_floor = FLOOR
    # 細線化はここで切っておく。Scale 0.5 は STEP0 がノードに焼き込むので、
    # STEP0 より後に落としてもツリーからは消えない
    scene.fp_auto_supersample = False
    scene.fp_supersample = False

    meshes = [o for o in scene.objects if o.type == "MESH"]
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    t = time.time()
    bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
    say(f"STEP0 完了 {time.time() - t:.1f}s")

    scene.fp_preview_mode = 'MONO_LIGHT'      # STEP0 後にもう一度立てる

    # ロゴだけ低い角度で塗り直す。
    #
    # 自動しきい値はこのメッシュを「有機」と判定して 85度を返し、島は 42個
    # しか作らない。押し出し文字は面取りと側面で割れてほしいのに、そこが
    # 全部1島にまとまって輪郭線しか出なかった(単体テストで手動20度に
    # すると 474島)。しきい値はシーン単位の設定しか無いので、STEP0 の後に
    # ロゴだけ選び直して塗り替える
    logo = bpy.data.objects.get("FP_LOGO")
    if logo is not None:
        keep_auto = scene.fp_sharp_auto
        keep_deg = scene.fp_sharp_edges
        scene.fp_sharp_auto = False
        scene.fp_sharp_edges = LOGO_DEG
        bpy.ops.object.select_all(action="DESELECT")
        logo.select_set(True)
        bpy.context.view_layer.objects.active = logo
        bpy.ops.freepencil.auto_vertex_color("EXEC_DEFAULT")
        scene.fp_sharp_auto = keep_auto
        scene.fp_sharp_edges = keep_deg
        say(f"ロゴを {LOGO_DEG}度 で塗り直した")
    if RELIEF > 0:
        scene.fp_far_relief = RELIEF
        for ng in bpy.data.node_groups:
            if ng.name.startswith(fp_core.NODE_GROUP_PREFIX):
                fp_core.far_relief_from_scene(ng, scene)

    scene.render.engine = fp_batch.eevee_engine()
    scene.eevee.taa_render_samples = 16
    # 灯が15個あるので影のページが足りず「Shadow buffer full」が出る
    # (実測 2295 / 2048)。プールを上限まで広げ、1灯あたりの影の解像度も
    # 落とす。線画では影の輪郭の精度はほぼ効かないので、解像度は下げてよい
    if hasattr(scene.eevee, "shadow_pool_size"):
        scene.eevee.shadow_pool_size = '1024'
    if hasattr(scene.eevee, "shadow_resolution_scale"):
        scene.eevee.shadow_resolution_scale = 0.5
    # スーパーサンプリングはここで一本化する。
    #
    # アドオンの fp_supersample は「解像度200% + コンポジタで Scale 0.5」で
    # 既に等倍の絵を作る。そこへ render_still の箱縮小(ss=2)を重ねると
    # 絵そのものが画面の半分に縮み、線が灰色に潰れる(実測: 絵の幅
    # 1564px→782px, ink 0.01522→0.00174, 真っ黒画素 0.01245→0.00001)。
    # 「動画がくすむ」原因はこれだった。
    #
    # アドオン側を切り、素直に2倍で描いて箱縮小する。全画面のまま線が残る
    # (ink 0.00836 / 黒 0.00368 = 従来の5倍・368倍)。
    scene.render.resolution_percentage = 100
    scene.render.resolution_x = RES * SS
    scene.render.resolution_y = int(RES * 9 / 16) * SS
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"

    if "--no-render" in ARGV:
        # 構図を見て決めたいときは、ここで保存して終わる。
        # カメラのキーは本番と同じ FRAMES 分入っている
        blend = OUT / "showcase.blend"
        bpy.ops.wm.save_as_mainfile(filepath=str(blend))
        say(f"保存 {blend} ({blend.stat().st_size / 2**20:.0f} MB) "
            f"— フレーム 1..{FRAMES}, {scene.render.resolution_x}x"
            f"{scene.render.resolution_y}")
        return

    frame_dir = OUT / "frames"
    frame_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    t = time.time()
    # --sample N: 全体から N 枚だけ等間隔で描く。本番前の絵の確認用で、
    # 動画は作らない(飛び飛びのフレームを繋いでも意味がないため)
    if ONLY > 0:
        scene.frame_set(ONLY)
        png = frame_dir / f"only_f{ONLY:04d}.png"
        fp_batch.render_still(scene, png, SS)
        say(f"  1枚だけ f{ONLY} → {png}")
        return
    if SAMPLE > 0:
        picks = [1 + round(i * (FRAMES - 1) / max(SAMPLE - 1, 1))
                 for i in range(SAMPLE)]
        for f in picks:
            scene.frame_set(f)
            png = frame_dir / f"sample_f{f:04d}.png"
            fp_batch.render_still(scene, png, SS)
            say(f"  見本 f{f} → {png.name} ({time.time() - t:.0f}s)")
        return
    for f in range(1, FRAMES + 1):
        scene.frame_set(f)
        png = frame_dir / f"f{f:04d}.png"
        fp_batch.render_still(scene, png, SS)
        paths.append(png)
        if f % 25 == 0 or f == FRAMES:
            say(f"  {f}/{FRAMES} ({time.time() - t:.0f}s, "
                f"{(time.time() - t) / f:.1f}s/frame)")
    say(f"レンダ完了 {time.time() - t:.1f}s")

    video = OUT / "showcase_lineart.mp4"
    # PNG は箱縮小後なので、レンダ解像度(SS倍)ではなく最終サイズを渡す
    fp_batch.encode_video(paths, video, FPS, RES, int(RES * 9 / 16))
    say(f"動画 {video} ({video.stat().st_size // 1024} KB)")
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "showcase.blend"))


if __name__ == "__main__":
    main()
