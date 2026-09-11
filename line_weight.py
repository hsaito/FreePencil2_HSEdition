"""線の強弱(入り抜き)を、くぼみ(AO)から作る。

線を一様な太さで出すと図面に見える。人が描くときは、奥まったところを
太く濃く、明るく開いたところを細くする。それを AO(アンビエント
オクルージョン)パスで再現する。

なぜ AO なのか。強弱を作るには「線に沿って連続に変わるスカラー場」が
要る。曲率・線の密度・形の太さは、どれも線の途中で不連続に飛ぶので
使えなかった。使える材料をコンポジタに届くパスから全部出して比べた
結果(dev/note_assets/eval_survey_drivers.py)、次が分かった。

    ・光(Diffuse Direct)  効くが、ライトの向きで絵柄が変わる
    ・AO                  効く。形だけで決まるので回しても絵柄が動かない
    ・奥行き(Mist)        弱い
    ・落ち影              2値なので段に切れない

回転させて確かめたところ(dev/note_assets/eval_ao_mix.py、120フレーム)、
隣り合うフレームのインク量の差は

    強弱なし 1.99%  /  AO 1.83%  /  光 1.86%

で、AO は強弱なしの土台よりも揺れが小さい。つまり AO はちらつきを
持ち込まない。

しきい値だけは自動で決められない。実モデル11体で「線の画素における
d = 1 - AO」の20%点を測ると 0.0013〜0.0193 と15倍ひらいた。ぼかしで
正規化する案も試したが、かえって悪化した(32〜63倍)。だから
「1カットに1回、測ってから固定する」形にしている。カットの中で
固定するのは、フレームごとに測り直すと絵が変わるたびにしきい値が
動いて線がちらつくため(前回の実測でフレーム間26%振れた)。
"""

import math
import os
import shutil
import tempfile

import bpy

from . import compat

# 段ごとの太さ(px)。くぼんでいる側から太い順。2倍レンダを前提とする。
# 一番細い段を 1px にすると 50% 縮小で 0.5px になり、線が破線に見えた
# (実測: 頬と瞼が点線)。2px を下限にする
#
# 6/5/4/3/2 では縮小後 3/2/2/2/1 で真ん中の3段が同じ太さになり、段分けを
# 直しても目のまわりしか変わらなかった(実測)。太い側を伸ばして比を 6倍
# (縮小後 6/4/2/2/1)にし、濃さの強弱(fp_lw_tone)と合わせて差を出す。
# スザンヌの耳・カメラのレンズ・車のグリルで詰まりの守りが効くことは
# 確認済み(dev/note_assets/eval_lw_crowd_check.py)
LEVELS = (12, 8, 5, 3, 2)

# 再生成時に消す目印。fp_core.setup_compositor のクリーンアップが
# label.startswith("FreePencil") のノードを消すので、それに乗せる
NODE_LABEL = "FreePencil_line_weight"


def effective_sensitivity(scene) -> float:
    """線の検出しきい値。強弱がONのときは弱め(=線を減らす)に倒す。

    強弱は線を太く濃くするので、土台の線をそのままにすると絵が
    重くなり、細かい補助線まで太って画面が埋まる。実測(1920、
    強弱ONのインク率):

        カメラ  感度0.5 -> 9.53%  /  感度1.1 -> 8.40%
        車      感度0.5 -> 9.06%  /  感度1.1 -> 8.24%
        スザンヌ 感度0.25 -> 2.08%  /  感度0.9 -> 1.67%

    数字の差は2割ほどだが、絵は明確に変わる。ボディの薄い補助線が
    落ちて、輪郭とパネルの切れ目だけが残る。連結成分も減った
    (スザンヌ 11 -> 8)ので、途切れも減っている。
    """
    sens = float(getattr(scene, "fp_line_sensitivity", 1.0))
    if not getattr(scene, "fp_line_weight", False):
        return sens
    bias = float(getattr(scene, "fp_lw_line_bias", 1.0))
    return max(0.05, min(4.0, sens * max(1.0, bias)))


def island_ratio(scene, base: float) -> float:
    """島を切る細かさの上限。強弱がONのときは粗くする(=線を減らす)。

    v2.7 でメカの線を強く出すために判定を細かくした結果、なめらかな
    形では切れすぎるようになった。スザンヌの耳のように薄い縁を斜めから
    見ると、サブサーフの輪が1本ずつ別の島になり、4〜5本の平行線として
    出る。強弱はそれを太らせるので、まとめて黒い帯になる。

    しきい値の角度を直接上げる案も試したが、18度でも26度でも島が
    3つまで落ちて目の虹彩の輪まで消えた。角度はモデルごとに効き方が
    違いすぎる。ここでは「島が何個までなら許すか」を下げて、角度は
    既存の自動ループに決めさせる。
    """
    if not getattr(scene, "fp_line_weight", False):
        return base
    return max(0.002, base * float(getattr(scene, "fp_lw_island_bias", 1.0)))


def edges_from_scene(scene) -> list:
    """段の境目を小さい順に返す。"""
    return sorted(getattr(scene, f"fp_lw_e{i}", 0.0) for i in range(1, 5))


def levels_from_scene(scene) -> list:
    """段ごとの太さ。強さの倍率とレンダー倍率をかけ、1px 以上に丸める。

    LEVELS は「200%でレンダして50%に縮小する」細線化を前提にした値。
    細線化を切ると縮小が無くなるので、そのままでは線が太くなりすぎる
    (実測、同じ最終サイズで インク 0.367% -> 2.892%)。レンダー倍率で
    割って、どちらでも同じ太さになるようにする。
    """
    mul = getattr(scene, "fp_lw_strength", 1.0)
    pct = max(1, getattr(scene.render, "resolution_percentage", 100))
    return [max(1, round(px * mul * pct / 200.0)) for px in LEVELS]


# 計算ノードの識別子。5.x で CompositorNodeMath が無くなり、
# ShaderNodeMath に統合された(実測: 5.2 で "Node type
# CompositorNodeMath undefined")。4.x は両方あるので、既存の挙動を
# 変えないよう Compositor 版を先に試す
_MATH_TYPES = ("CompositorNodeMath", "ShaderNodeMath")


def _new_math(tree):
    last = None
    for idn in _MATH_TYPES:
        try:
            return tree.nodes.new(idn)
        except RuntimeError as e:                    # noqa: PERF203
            last = e
    raise last


def _set_num_socket(node, name, value):
    """数値のソケットに入れる。5.x の Size はベクトルのことがある。"""
    sock = node.inputs.get(name)
    if sock is None:
        return
    for v in (value, (value, value), (value, value, value)):
        try:
            sock.default_value = v
            return
        except (TypeError, ValueError):
            continue


def _set_enum_socket(node, name, *candidates):
    """列挙のソケットに、識別子でも表示名でも入るように試す。"""
    sock = node.inputs.get(name)
    if sock is None:
        return
    for v in candidates:
        try:
            sock.default_value = v
            return
        except (TypeError, ValueError):
            continue


def _set_blur(node, px):
    """ぼかしの半径。5.x で設定がソケットへ移った(実測: 5.2 の
    CompositorNodeBlur に filter_type が無い)。"""
    if hasattr(node, "size_x"):
        node.filter_type = "GAUSS"
        node.size_x = px
        node.size_y = px
        node.use_relative = False
        return
    _set_num_socket(node, "Size", px)
    _set_enum_socket(node, "Type", "GAUSS", "Gaussian")


def _set_feather(node, px):
    """距離で薄れる膨張。芯で 1、px 離れると 0 に直線で落ちる。

    5.x では mode/distance/falloff がソケット Type/Size/Falloff になった。
    """
    if hasattr(node, "distance"):
        node.mode = "FEATHER"
        node.distance = px
        node.falloff = "LINEAR"
        return
    _set_num_socket(node, "Size", px)
    _set_enum_socket(node, "Type", "FEATHER", "Feather")
    _set_enum_socket(node, "Falloff", "LINEAR", "Linear")


def _set_dilate(node, px):
    """太らせる量。5.x では distance/mode がソケット Size/Type になった。"""
    if hasattr(node, "distance"):
        node.mode = "STEP"
        node.distance = px
        return
    _set_num_socket(node, "Size", px)
    _set_enum_socket(node, "Type", "STEP", "Step")


def _srgb_to_linear(c: float) -> float:
    """表示の明るさをリニアへ。濃さの段を表示基準で決めるために使う。"""
    if c <= 0.04045:
        return c / 12.92
    return ((c + 0.055) / 1.055) ** 2.4


def _math(tree, op, x, y, a=None, b=None):
    n = _new_math(tree)
    n.operation = op
    n.location = (x, y)
    n.label = NODE_LABEL
    if a is not None:
        n.inputs[0].default_value = a
    if b is not None:
        n.inputs[1].default_value = b
    return n


def blur_from_scene(scene) -> int:
    """くぼみのぼかし半径。段の太さと同じくレンダー倍率で割る。

    ぼかしは画素単位なので、25% で測って 200% で使うと模型に対する
    ぼかしの広さが 8 倍違い、しきい値が合わない。どの倍率でも同じ
    広さになるよう、200% を基準に割る。
    """
    px = max(0, int(getattr(scene, "fp_lw_ao_blur", 4)))
    pct = max(1, getattr(scene.render, "resolution_percentage", 100))
    return max(0, round(px * pct / 200.0))


def dep_chain(tree, ao_sock, alpha_sock, scene, x0, y0):
    """AO から「くぼみの深さ d = 1 - AO」を作る。合成と計測の両方が使う。

    計測(measure_edges)は生の AO を 25% で PNG に書いて読み、合成は
    4px ぼかした AO を使っていた。ぼかしは透明な背景(AO=0)を輪郭へ
    引き込むので、合成側の d は計測側より1桁大きく、線の画素の 88% が
    一番細い段に入っていた(実測: しきい値 0.004〜0.094 に対し合成側の
    20% 点が 0.136)。段分けは事実上働いていなかった。

    直し方は2つで、どちらもここに閉じ込める。
      - ぼかす前に、背景を「開いている(AO=1)」で埋める
      - 計測も同じ鎖を通した値を読む(同じ関数を呼ぶ)
    """
    src = ao_sock
    if alpha_sock is not None:
        # AO + (1 - alpha): モデルの外を 1 にしてから、1 を超えた分を切る
        inv_a = _math(tree, "SUBTRACT", x0, y0 - 300, a=1.0)
        tree.links.new(alpha_sock, inv_a.inputs[1])
        fill = _math(tree, "ADD", x0 + 120, y0 - 300)
        tree.links.new(ao_sock, fill.inputs[0])
        tree.links.new(inv_a.outputs[0], fill.inputs[1])
        cap = _math(tree, "MINIMUM", x0 + 240, y0 - 300, b=1.0)
        tree.links.new(fill.outputs[0], cap.inputs[0])
        src = cap.outputs[0]
    # AO は EEVEE のレイトレなので粒が乗る。粒がそのまま段の切り替わり
    # になって、1本の線が点線に見える。少しぼかしてから段に切る
    blur = tree.nodes.new("CompositorNodeBlur")
    blur.location = (x0, y0 - 180)
    blur.label = NODE_LABEL
    _set_blur(blur, blur_from_scene(scene))
    tree.links.new(src, blur.inputs[0])
    # d = 1 - AO。くぼんでいるほど大きい
    dep = _math(tree, "SUBTRACT", x0 + 200, y0 - 180, a=1.0)
    tree.links.new(blur.outputs[0], dep.inputs[1])
    return dep


def build_weight(tree, line_sock, ao_sock, scene, x0=900, y0=-200,
                 alpha_sock=None):
    """線に強弱を付ける枝を組み、出口のソケットを返す。

    line_sock は「白背景・黒線」であること。グループの "line" 出力は
    極性が逆(黒背景・白線)で、そのまま反転すると背景まで線として
    拾い、画面が真っ黒になる(実測: インク100%)。合成に入る直前の
    ソケットを渡すこと。
    """
    edges = edges_from_scene(scene)
    levels = levels_from_scene(scene)
    binv = getattr(scene, "fp_lw_bin", 0.15)
    gain = getattr(scene, "fp_lw_gain", 1.4)

    inv = tree.nodes.new("CompositorNodeInvert")
    inv.location = (x0, y0)
    inv.label = NODE_LABEL
    tree.links.new(line_sock, inv.inputs["Color"])

    # 2値化。薄い線も拾いたいのでしきい値は低め。ここで芯を作っておく
    # と、縮小したときに面積平均でアンチエイリアスが戻る
    binz = _math(tree, "GREATER_THAN", x0 + 200, y0, b=binv)
    tree.links.new(inv.outputs[0], binz.inputs[0])

    dep = dep_chain(tree, ao_sock, alpha_sock, scene, x0, y0)

    # 線が詰まっているところは太らせない。
    # スザンヌの耳の縁のように、薄い縁を斜めから見るとメッシュの輪が
    # 4〜5本の平行線になる。そこは全部が同じ「深いくぼみ」の段に入る
    # ので、まとめて太って一塊の黒い帯になった。実モデルでも同じで、
    # 車のグリルの網が黒くつぶれる。
    # アドオンの遠景つぶれ軽減も同じ密度の考え方だが、あちらは線の
    # アルファを薄くするだけなので、こちらの2値化(0.15)で元に戻って
    # しまい効かない(実測: 0.9 まで上げても耳は変わらなかった)。
    # ここでは「詰まっている場所では太らせる前の線に戻す」形にする。
    # 段を一番細いところへ倒すだけでは足りなかった(耳の帯は残った)。
    crowd = max(0.0, min(1.0, float(getattr(scene, "fp_lw_crowd", 0.0))))
    crowd_w = None
    if crowd > 0.0:
        dens = tree.nodes.new("CompositorNodeBlur")
        dens.location = (x0 + 380, y0 - 60)
        dens.label = NODE_LABEL
        _set_blur(dens, max(1, int(getattr(scene, "fp_lw_crowd_radius", 5))))
        tree.links.new(binz.outputs[0], dens.inputs[0])
        # しきい値を超えた分だけを 0..1 にする
        th = float(getattr(scene, "fp_lw_crowd_threshold", 0.25))
        sub = _math(tree, "SUBTRACT", x0 + 560, y0 - 60, b=th)
        tree.links.new(dens.outputs[0], sub.inputs[0])
        div = _math(tree, "DIVIDE", x0 + 560, y0 - 150, b=max(1e-3, 1.0 - th))
        tree.links.new(sub.outputs[0], div.inputs[0])
        cl0 = _math(tree, "MINIMUM", x0 + 700, y0 - 60, b=1.0)
        tree.links.new(div.outputs[0], cl0.inputs[0])
        cl1 = _math(tree, "MAXIMUM", x0 + 700, y0 - 150, b=0.0)
        tree.links.new(cl0.outputs[0], cl1.inputs[0])
        crowd_w = _math(tree, "MULTIPLY", x0 + 840, y0 - 60, b=crowd)
        tree.links.new(cl1.outputs[0], crowd_w.inputs[0])

    # 太さは段ではなく連続に決める。
    #
    # 以前は 5 段の硬いしきい値と整数の膨張で太さを決めていた。段分けが
    # 働いていなかった頃は実質 1 段で、太さの変化は元の線の濃淡から
    # 連続的に出ていたので絵は綺麗だった。段分けを直した途端、1本の線の
    # 途中で太さが段になって切れ、眉や耳の縁が別々の線に見えた(実測)。
    # 段の境目で線が切れるのは設計そのものの問題なので、段をやめる。
    #
    # やり方: 線の芯を距離で薄れる形(Feather)に膨らませておき、
    # 「どこまでを線と見なすか」のしきい値を、くぼみの深さで連続的に
    # 動かす。深いほどしきい値が下がって太くなる。途中に段はできない。
    # しきい値は float なので、整数画素の壁(6/5/4/3/2 が 3/2/2/2/1 に
    # 潰れる)も無くなる。
    # 芯から外へ広げる量(px)。段があった頃の膨張距離と同じ範囲にする。
    # 2倍レンダなら 1..6 で、縮小後の太さは 2..7px
    hw_min = float(min(levels))
    hw_max = float(max(levels))
    reach = int(math.ceil(hw_max)) + 1
    fe = tree.nodes.new("CompositorNodeDilateErode")
    fe.location = (x0 + 940, y0 - 360)
    fe.label = NODE_LABEL
    _set_feather(fe, reach)
    tree.links.new(binz.outputs[0], fe.inputs[0])

    # 深さを 0..1 に。20% 点より浅ければ 0、80% 点より深ければ 1
    e_lo, e_hi = edges[0], edges[-1]
    span = max(1e-6, e_hi - e_lo)
    s_sub = _math(tree, "SUBTRACT", x0 + 400, y0 - 360, b=e_lo)
    tree.links.new(dep.outputs[0], s_sub.inputs[0])
    s_div = _math(tree, "DIVIDE", x0 + 560, y0 - 360, b=span)
    s_div.use_clamp = True
    tree.links.new(s_sub.outputs[0], s_div.inputs[0])
    depth01 = s_div

    # 望む広がり hw = hw_min + (hw_max - hw_min) * s。Feather は芯で 1、
    # reach 離れると 0 に直線で落ちるので、しきい値 T = 1 - hw / reach で
    # 「芯から hw まで」が線になる
    hw = _math(tree, "MULTIPLY_ADD", x0 + 700, y0 - 360, b=hw_max - hw_min)
    hw.inputs[2].default_value = hw_min
    tree.links.new(depth01.outputs[0], hw.inputs[0])
    thr = _math(tree, "MULTIPLY_ADD", x0 + 860, y0 - 460, b=-1.0 / reach)
    thr.inputs[2].default_value = 1.0
    tree.links.new(hw.outputs[0], thr.inputs[0])
    ink = _math(tree, "GREATER_THAN", x0 + 1120, y0 - 360)
    tree.links.new(fe.outputs[0], ink.inputs[0])
    tree.links.new(thr.outputs[0], ink.inputs[1])
    prev = ink

    # 元の線の濃さを取り戻す。
    # 2値化は 0.15 を境に 0/1 へ倒すので、線の「濃さ」を変える既存機能が
    # 全部無効になっていた。実測(カメラ、インク量の変化率):
    #     遠景つぶれ軽減 0->0.9   強弱OFF 73.26%  ->  強弱ON 1.47%
    #     メカの強さ 1.0->0.3     強弱OFF 26.98%  ->  強弱ON 7.35%
    # 太さは2値化した芯から作り、濃さは元の線から取る。元の濃さを
    # 一番太い段のぶんだけ広げてから掛けると、太らせた縁まで濃さが届く
    soft = tree.nodes.new("CompositorNodeDilateErode")
    soft.location = (x0 + 200, y0 + 160)
    soft.label = NODE_LABEL
    _set_dilate(soft, max(levels))
    tree.links.new(inv.outputs[0], soft.inputs[0])
    keep_ink = _math(tree, "MULTIPLY", x0 + 1180, y0 - 200)
    tree.links.new(prev.outputs[0], keep_ink.inputs[0])
    tree.links.new(soft.outputs[0], keep_ink.inputs[1])
    prev = keep_ink

    if crowd_w is not None:
        # 詰まっているところは、太らせる前の線へ戻す
        keep = _math(tree, "SUBTRACT", x0 + 1180, y0 - 300, a=1.0)
        tree.links.new(crowd_w.outputs[0], keep.inputs[1])
        fat = _math(tree, "MULTIPLY", x0 + 1180, y0 - 400)
        tree.links.new(prev.outputs[0], fat.inputs[0])
        tree.links.new(keep.outputs[0], fat.inputs[1])
        raw = _math(tree, "MULTIPLY", x0 + 1180, y0 - 500)
        tree.links.new(binz.outputs[0], raw.inputs[0])
        tree.links.new(crowd_w.outputs[0], raw.inputs[1])
        prev = _math(tree, "ADD", x0 + 1250, y0 - 400)
        tree.links.new(fat.outputs[0], prev.inputs[0])
        tree.links.new(raw.outputs[0], prev.inputs[1])

    g = _math(tree, "MULTIPLY", x0 + 1320, y0 - 400, b=gain)
    tree.links.new(prev.outputs[0], g.inputs[0])
    cl = _math(tree, "MINIMUM", x0 + 1480, y0 - 400, b=1.0)
    tree.links.new(g.outputs[0], cl.inputs[0])
    last = cl

    # 濃さでも強弱をつける。太さと同じ深さ s から連続に決める。
    # 一番深い所は黒のまま、一番浅い所は表示で (1 - 0.6*tone) まで薄く。
    # tone=0 で従来どおり。gain は薄い線を黒へ持ち上げるためのものなので、
    # その後で掛ける。
    #
    # 掛け算はリニアで行われ、出力で sRGB に変わる。リニアで 0.78 に
    # した線は表示では 0.5 になる(実測: 全画素が 0.5 以下に落ちた)。
    # 表示の濃さ shown を決めて、リニアの倍率 1 - (1-shown)^2.2 にする。
    #   shown = 1 - 0.6*tone*(1-s)
    tone = max(0.0, min(1.0, float(getattr(scene, "fp_lw_tone", 0.0))))
    if tone > 0.0:
        one_minus = _math(tree, "SUBTRACT", x0 + 1120, y0 - 560, a=1.0)
        tree.links.new(depth01.outputs[0], one_minus.inputs[1])
        fade = _math(tree, "MULTIPLY", x0 + 1250, y0 - 560, b=0.6 * tone)
        tree.links.new(one_minus.outputs[0], fade.inputs[0])       # 1-shown
        lin = _math(tree, "POWER", x0 + 1380, y0 - 560, b=2.2)
        tree.links.new(fade.outputs[0], lin.inputs[0])
        dk = _math(tree, "SUBTRACT", x0 + 1500, y0 - 560, a=1.0)
        tree.links.new(lin.outputs[0], dk.inputs[1])
        shade = _math(tree, "MULTIPLY", x0 + 1560, y0 - 400)
        tree.links.new(cl.outputs[0], shade.inputs[0])
        tree.links.new(dk.outputs[0], shade.inputs[1])
        last = shade

    out = tree.nodes.new("CompositorNodeInvert")
    out.location = (x0 + 1660, y0 - 400)
    out.label = NODE_LABEL
    tree.links.new(last.outputs[0], out.inputs["Color"])
    return out.outputs[0]


def scene_radius(scene) -> float:
    """レンダーに写るメッシュを囲む半径。くぼみの半径の基準にする。"""
    from mathutils import Vector
    pts = []
    for o in scene.objects:
        if o.type != "MESH" or o.hide_render:
            continue
        for c in o.bound_box:
            pts.append(o.matrix_world @ Vector(c))
    if not pts:
        return 1.0
    center = Vector((sum(p.x for p in pts) / len(pts),
                     sum(p.y for p in pts) / len(pts),
                     sum(p.z for p in pts) / len(pts)))
    return max(1e-4, max((p - center).length for p in pts))


def ensure_ao_pass(scene, view_layer):
    """AO パスと、その半径を用意する。

    半径は「シーンの大きさに対する割合」で持つ。シーン単位の絶対値に
    していたら、大きいモデルで何も遮蔽されず強弱が付かなかった
    (実測、既定0.6のまま: スザンヌ等倍は段の幅0.031で効くが、10倍に
    すると 0.0039 でほぼ効かない)。
    """
    view_layer.use_pass_ambient_occlusion = True
    ee = scene.eevee
    r = getattr(scene, "fp_lw_ao_dist", 0.6) * scene_radius(scene)
    if hasattr(ee, "use_gtao"):
        ee.use_gtao = True
    # 4.5 は gtao_distance、5.x は fast_gi_distance。名前が変わった
    for name in ("gtao_distance", "fast_gi_distance"):
        if hasattr(ee, name):
            setattr(ee, name, r)


def apply(scene, view_layer, tree, target_socket):
    """STEP3 の最後から呼ぶ。強弱が切ってあれば何もしない。

    target_socket は合成(または Set Alpha)の画像入力。そこに入って
    いる線を取り出し、強弱を通してから同じところへ戻す。
    """
    if not getattr(scene, "fp_line_weight", False):
        return None
    if not target_socket.is_linked:
        return None
    rl = next((n for n in tree.nodes if n.type == "R_LAYERS"), None)
    if rl is None:
        return None
    ensure_ao_pass(scene, view_layer)
    # ソケット名はバージョンで変わる。4.x は 'AO'、5.x は
    # 'Ambient Occlusion'。パスを立てた直後は生えていないこともある
    ao = compat.render_layer_socket(rl, compat.AO_SOCKETS)
    if ao is None:
        return None
    line_sock = target_socket.links[0].from_socket
    out = build_weight(tree, line_sock, ao, scene,
                       alpha_sock=rl.outputs.get("Alpha"))
    for lnk in list(target_socket.links):
        tree.links.remove(lnk)
    tree.links.new(out, target_socket)
    return out


# ---------------------------------------------------------------- 計測

def _load_float(path):
    """EXR を float のまま読む(R だけ)。"""
    import numpy as np
    img = bpy.data.images.load(str(path))
    try:
        w, h = img.size
        buf = np.empty(w * h * 4, dtype=np.float32)
        img.pixels.foreach_get(buf)
        return buf.reshape(h, w, 4)[..., 0].copy()
    finally:
        bpy.data.images.remove(img)


def _load_gray(path):
    """PNG を、書いたときの値そのままで読む。

    既定では sRGB として読み込まれ、pixels がリニアに戻される。
    そうすると 2値化のしきい値が、ノード側(表示値で判定)と違う空間で
    かかってしまい、線とみなす画素がずれる。Non-Color で読む。
    """
    import numpy as np
    img = bpy.data.images.load(str(path))
    try:
        try:
            img.colorspace_settings.name = "Non-Color"
        except (TypeError, AttributeError):
            pass
        w, h = img.size
        buf = np.empty(w * h * 4, dtype=np.float32)
        img.pixels.foreach_get(buf)
        a = buf.reshape(h, w, 4)
        return a[..., :3].mean(axis=2), a[..., 3]
    finally:
        bpy.data.images.remove(img)


def _find(folder, slot):
    """スロット名で書き出されたファイルを探す。

    ファイル名の付き方はバージョンで違う(4.x は "ao0001.png"、
    5.x は接頭辞やフレーム番号の扱いが変わる)。決め打ちにすると
    「そんなファイルは無い」で落ちるので、名前で拾う。
    """
    import glob
    hits = sorted(glob.glob(os.path.join(folder, "**", f"*{slot}*"),
                            recursive=True))
    hits = [h for h in hits if os.path.isfile(h)]
    if not hits:
        raise FileNotFoundError(f"{slot} が書き出されていない: {folder}")
    return hits[0]


def _source_before_scale(socket):
    """縮小ノードを遡って、レンダー解像度のままのソケットを返す。

    細線化がONだと 200% でレンダして Scale 0.5 で戻すので、合成の
    入り口の絵は AO パスの半分の大きさになる。そのまま比べると
    「270 と 136 で形が合わない」と落ちる(実測)。
    """
    while socket.is_linked:
        src = socket.links[0].from_socket
        if src.node.type != "SCALE":
            return src
        socket = src.node.inputs[0]
    return None


def measure_edges(scene, view_layer, percent=50):
    """1回レンダして、線の画素における d = 1 - AO の分位点を返す。

    絵ごとに 15 倍ひらくので固定値では配れない。カットごとに1回
    測って固定する。

    d は合成と同じ鎖(dep_chain: 背景埋め -> ぼかし -> 1-AO)を通し、
    EXR(float)で読む。生の AO を PNG で読んでいたときは 8bit の
    量子化で最初のしきい値が 1/255 = 0.0039 になっていた(実測)。
    ぼかしはレンダー倍率で割るので、50% で測っても 200% と同じ広さ。
    """
    import numpy as np
    # 5.x は scene.node_tree が無く、コンポジタはノードグループになった。
    # 最終出力も Composite ではなく Group Output。compat 経由で取る
    tree = compat.get_compositor_tree(scene)
    if tree is None:
        return None
    rl = next((n for n in tree.nodes if n.type == "R_LAYERS"), None)
    comp = next((n for n in tree.nodes
                 if n.type in compat.OUTPUT_NODE_TYPES), None)
    if rl is None or comp is None or not comp.inputs:
        return None
    if not comp.inputs[0].is_linked:
        return None
    ensure_ao_pass(scene, view_layer)

    tmp = tempfile.mkdtemp(prefix="fp_lw_")
    keep_pct = scene.render.resolution_percentage
    fo = tree.nodes.new("CompositorNodeOutputFile")
    fo.label = NODE_LABEL
    # 4.x は base_path / file_slots、5.x は directory / file_output_items。
    # 名前も構造も違うので compat 経由で触る
    compat.file_output_set_dir(fo, tmp)
    compat.file_output_clear_slots(fo)
    line_src = _source_before_scale(comp.inputs[0])
    if line_src is None:
        tree.nodes.remove(fo)
        return None
    ao_sock = compat.render_layer_socket(rl, compat.AO_SOCKETS)
    if ao_sock is None:
        tree.nodes.remove(fo)
        return None
    for name, sock in (("line", line_src),
                       # アルファは線の絵ではなくレンダーレイヤーから取る。
                       # 線の絵は縮小の有無で大きさが変わる
                       ("sil", rl.outputs["Alpha"])):
        compat.file_output_add_slot(fo, name, "PNG", "RGBA")
        # 5.x は file_output_items と inputs の並びが一致しないことが
        # あるので、末尾ではなく名前で挿す(fp_core と同じやり方)
        tree.links.new(sock, fo.inputs[name])
    # d は合成と同じ鎖で作り、float のまま書く。4.x の File Output は
    # ノード単位でしか形式を持てないので、EXR 用にもう1つ置く
    scene.render.resolution_percentage = percent   # blur_from_scene が見る
    chain_start = len(tree.nodes)
    dep = dep_chain(tree, ao_sock, rl.outputs.get("Alpha"), scene,
                    x0=-600, y0=-600)
    chain_nodes = list(tree.nodes)[chain_start:]
    scene.render.resolution_percentage = keep_pct
    fo2 = tree.nodes.new("CompositorNodeOutputFile")
    fo2.label = NODE_LABEL
    compat.file_output_set_dir(fo2, tmp)
    compat.file_output_clear_slots(fo2)
    compat.file_output_add_slot(fo2, "dep", "OPEN_EXR", "RGBA")
    try:
        fo2.format.color_depth = "32"
    except (AttributeError, TypeError):
        pass
    tree.links.new(dep.outputs[0], fo2.inputs["dep"])
    # 色管理を通すと値が変わり、分位点がずれる
    try:
        fo.format.color_management = "OVERRIDE"
        fo.format.view_settings.view_transform = "Standard"
        fo.format.view_settings.look = "None"
    except (AttributeError, TypeError):
        pass
    try:
        scene.render.resolution_percentage = percent
        bpy.ops.render.render(write_still=False)
        d_all = _load_float(_find(tmp, "dep"))
        ln, _ = _load_gray(_find(tmp, "line"))
        al, _ = _load_gray(_find(tmp, "sil"))
    finally:
        tree.nodes.remove(fo)
        tree.nodes.remove(fo2)
        for n in chain_nodes:
            tree.nodes.remove(n)
        scene.render.resolution_percentage = keep_pct
        # 測るたびに temp が残っていた
        shutil.rmtree(tmp, ignore_errors=True)

    if d_all.shape != ln.shape or d_all.shape != al.shape:
        return None
    ink = 1.0 - ln
    on = (ink > getattr(scene, "fp_lw_bin", 0.15)) & (al > 0.5)
    if int(on.sum()) < 200:
        return None
    d = d_all[on]
    n = len(LEVELS)
    return [float(np.percentile(d, 100.0 * (k + 1) / n)) for k in range(n - 1)]


class FREEPENCIL_OT_measure_line_weight(bpy.types.Operator):
    """Render once and read the AO thresholds for line weight."""

    bl_idname = "freepencil.measure_line_weight"
    bl_label = "Measure line weight thresholds"
    bl_description = (
        "Render once at low resolution and read the AO thresholds from this "
        "shot. Fixed per cut so the line does not flicker"
    )
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        edges = measure_edges(scene, context.view_layer)
        if edges is None:
            self.report({"WARNING"},
                        bpy.app.translations.pgettext(
                            "Run STEP3 first, and point the camera at the "
                            "subject"))
            return {"CANCELLED"}
        for i, v in enumerate(edges, start=1):
            setattr(scene, f"fp_lw_e{i}", v)
        self.report({"INFO"}, "  ".join(f"{v:.4f}" for v in edges))
        return {"FINISHED"}
