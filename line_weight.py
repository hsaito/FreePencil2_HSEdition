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

# 奥ほど線を減らす分は、線を検出するノードグループの中(ColorRamp の
# 手前)に挿す。グループは STEP3 で使い回されるので、この目印で毎回
# 外してから挿し直す
FAR_LABEL = "FreePencil_line_weight_far"
DEPTH_SOCKETS = ("Depth", "Z")



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


def far_wanted(scene) -> bool:
    """奥の扱い(細く・減らす・薄く)のどれかが入っているか。"""
    return (float(getattr(scene, "fp_lw_far", 0.0)) > 0.0
            or float(getattr(scene, "fp_lw_far_sens", 1.0)) > 1.0
            or float(getattr(scene, "fp_lw_far_fade", 0.0)) > 0.0)


def far_range(scene):
    """奥の扱いが始まる距離と、全部かかる距離。0 のままなら未計測。"""
    a = float(getattr(scene, "fp_lw_far_start", 0.0))
    b = float(getattr(scene, "fp_lw_far_end", 0.0))
    if b <= a:
        return None
    return a, b


def far_chain(tree, depth_sock, alpha_sock, scene, x0, y0, spread,
              label=NODE_LABEL):
    """深度パスから「奥度」0..1 を作る。

    町のデモ(dev/note_assets/eval_far_ideas.py、24案)で比べた結果、
    奥をぼかすのでも局所密度で薄めるのでもなく、「奥ほど強弱を切って
    線を間引く」のが一番絵に見えた。手前の太い線は残し、奥は精密と
    同じ細い線に戻る。奥度は距離を線形に 0..1 にして 0.7 乗(手前から
    早めに効き始める)。

    背景の深度はクリップ距離なので奥度が 1 になる。輪郭を外へ太らせる
    画素はシルエットの外にあり、そのままだと手前の球の輪郭まで外側が
    削れて細くなった(実測: t51)。奥度をシルエットの中だけで取り、
    正規化ぼかし blur(far*a)/blur(a) で外へ spread px 伸ばす。
    """
    rng = far_range(scene)
    if rng is None:
        return None
    a, b = rng
    sub = _math(tree, "SUBTRACT", x0, y0, b=a)
    tree.links.new(depth_sock, sub.inputs[0])
    div = _math(tree, "DIVIDE", x0 + 120, y0, b=b - a)
    div.use_clamp = True
    tree.links.new(sub.outputs[0], div.inputs[0])
    pw = _math(tree, "POWER", x0 + 240, y0, b=0.7)
    tree.links.new(div.outputs[0], pw.inputs[0])
    made = [sub, div, pw]
    last = pw
    if alpha_sock is not None:
        masked = _math(tree, "MULTIPLY", x0 + 360, y0)
        tree.links.new(pw.outputs[0], masked.inputs[0])
        tree.links.new(alpha_sock, masked.inputs[1])
        bm = tree.nodes.new("CompositorNodeBlur")
        bm.location = (x0 + 480, y0)
        _set_blur(bm, int(spread))
        tree.links.new(masked.outputs[0], bm.inputs[0])
        ba = tree.nodes.new("CompositorNodeBlur")
        ba.location = (x0 + 480, y0 - 120)
        _set_blur(ba, int(spread))
        tree.links.new(alpha_sock, ba.inputs[0])
        floor = _math(tree, "MAXIMUM", x0 + 600, y0 - 120, b=1e-3)
        tree.links.new(ba.outputs[0], floor.inputs[0])
        ext = _math(tree, "DIVIDE", x0 + 720, y0)
        ext.use_clamp = True
        tree.links.new(bm.outputs[0], ext.inputs[0])
        tree.links.new(floor.outputs[0], ext.inputs[1])
        made += [masked, bm, ba, floor, ext]
        last = ext
    for n in made:
        n.label = label
    last["fp_tap"] = "far"
    return last


def build_weight(tree, line_sock, ao_sock, scene, x0=900, y0=-200,
                 alpha_sock=None, depth_sock=None):
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
    inv["fp_tap"] = "inv"

    # 2値化。薄い線も拾いたいのでしきい値は低め。ここで芯を作っておく
    # と、縮小したときに面積平均でアンチエイリアスが戻る
    # 芯は「その画素が濃い」だけでなく「周りも濃い」ことを条件にする。
    # 薄い線は山がしきい値をまたいでまばらな点になり、その点が隣の
    # 濃い線の濃さ(soft は max)で真っ黒に塗られて点線に見えた(実測:
    # テレビのベゼル内側)。3px ぼかした線も一定以上ある画素だけを芯に
    # すると、まばらな点は周りが薄いので外れ、濃い線(中心 1.0 で 2〜3px)
    # は通る。外れた薄い線は元の線を重ねて残すので消えない
    hard = _math(tree, "GREATER_THAN", x0 + 200, y0, b=binv)
    tree.links.new(inv.outputs[0], hard.inputs[0])
    nb = tree.nodes.new("CompositorNodeBlur")
    nb.location = (x0 + 200, y0 + 90)
    nb.label = NODE_LABEL
    _set_blur(nb, 3)
    tree.links.new(inv.outputs[0], nb.inputs[0])
    solid = _math(tree, "GREATER_THAN", x0 + 320, y0 + 90, b=binv * 0.65)
    tree.links.new(nb.outputs[0], solid.inputs[0])
    binz = _math(tree, "MULTIPLY", x0 + 440, y0)
    tree.links.new(hard.outputs[0], binz.inputs[0])
    tree.links.new(solid.outputs[0], binz.inputs[1])
    binz["fp_tap"] = "binz"

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
    crowd_w = None   # 後で「閉じで埋まる隙間」から作る(reach が要る)

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
    # 密なモデルは最大幅を下げる。帆船の索具や機関車の足回りは、間隔が
    # 中くらいの線が全部太って画面が重くなった(実測)。詰まりの守りは
    # 「隣とつながる所」しか止めないので、全体の密度で天井を下げる。
    # 密度は measure_edges が 100%(最終の大きさ)で測る。フルHD の実測:
    #   スザンヌ 0.02 / カメラ 0.22 / ランチア 0.23 / メカ 0.41 /
    #   機関車 0.42 / 帆船 0.55
    #   密度 5% 以下      そのまま
    #   密度 50% 以上     最大幅を 1/4 に
    #   間は直線で補間(カメラ 0.72、メカ 0.40、機関車 0.38)
    dens = float(getattr(scene, "fp_lw_density", 0.0))
    t = max(0.0, min(1.0, (dens - 0.05) / 0.45))
    hw_max = hw_min + (hw_max - hw_min) * (1.0 - 0.75 * t)
    # Feather は芯で 1、reach 離れると 0 に直線で落ちる。裾(値が 0 に
    # 近い所)は距離の近似で周期的な凹凸が出て、しきい値がそこに掛かると
    # 本体から離れた点が並ぶ(実測: テレビのベゼルの内側に点線)。裾を
    # 使わないよう、最大の広がりの 1.5 倍を半径にしてしきい値が 1/3 より
    # 下がらないようにする
    reach = int(math.ceil(hw_max * 1.5)) + 1
    fe = tree.nodes.new("CompositorNodeDilateErode")
    fe.location = (x0 + 940, y0 - 360)
    fe.label = NODE_LABEL
    _set_feather(fe, reach)
    tree.links.new(binz.outputs[0], fe.inputs[0])
    # Feather の距離は斜めの縁で階段状に落ちる(実測: 平板の縁に周期的な
    # うねり)。少しぼかして階段をならす。芯の値は 1 のまま
    fes = tree.nodes.new("CompositorNodeBlur")
    fes.location = (x0 + 1030, y0 - 360)
    fes.label = NODE_LABEL
    _set_blur(fes, 3)
    tree.links.new(fe.outputs[0], fes.inputs[0])
    fe = fes
    fe["fp_tap"] = "feather"

    # 深さを 0..1 に。20% 点より浅ければ 0、80% 点より深ければ 1
    e_lo, e_hi = edges[0], edges[-1]
    span = max(1e-6, e_hi - e_lo)
    s_sub = _math(tree, "SUBTRACT", x0 + 400, y0 - 360, b=e_lo)
    tree.links.new(dep.outputs[0], s_sub.inputs[0])
    s_div = _math(tree, "DIVIDE", x0 + 560, y0 - 360, b=span)
    s_div.use_clamp = True
    tree.links.new(s_sub.outputs[0], s_div.inputs[0])
    depth01 = s_div
    # どちらを太くするか。線画の常識は「輪郭が太く、内側の線が細い」で、
    # くぼみに入る所で細くなるのが入り抜き。深い所を太くすると目や眉が
    # 太く輪郭が細くなり、逆に見えた(実測、指摘あり)。既定は開いた所を太く
    if not getattr(scene, "fp_lw_deep_thick", False):
        flip = _math(tree, "SUBTRACT", x0 + 640, y0 - 460, a=1.0)
        tree.links.new(s_div.outputs[0], flip.inputs[1])
        depth01 = flip

    # 望む広がり hw = hw_min + (hw_max - hw_min) * s。Feather は芯で 1、
    # reach 離れると 0 に直線で落ちるので、しきい値 T = 1 - hw / reach で
    # 「芯から hw まで」が線になる
    if crowd > 0.0:
        # 詰まりの守り。「太らせたら隣の線とつながるか」を直接測る。
        # 線の密度(ぼかした芯)で測っていた頃は、密度の尺度が線幅と合わず
        # 帆船の船体や機関車のボイラーが黒い塊になった(実測)。
        # 芯を r だけ膨らませてから同じだけ縮める(閉じ)と、間隔が 2r より
        # 狭い線の間だけが埋まる。その埋まった所 = 広げるとつながる所。
        # 1段だけだと「間隔が 2r より広いが、両側から伸びると埋まる」
        # 隙間が残って網目が面に見えた(実測: 甲板 29% -> 34%)。半径を
        # 3段(reach の 1/2, 1, 2 倍)にして、狭いほど強く抑える:
        #   間隔 < reach      広げない
        #   間隔 < 2*reach    1/3 だけ
        #   間隔 < 4*reach    2/3 まで
        # 隙間は線の上では 0 なので、線側へ少し広げて線の縁まで届かせる
        # (ぼかすと隣で 0.5 になり、半分だけ太った。実測)
        levels_r = ((max(1, reach // 2), 1.0), (reach, 0.66), (reach * 2, 0.33))
        acc = None
        for k, (r, wgt) in enumerate(levels_r):
            yy = y0 - 60 - k * 90
            dil = tree.nodes.new("CompositorNodeDilateErode")
            dil.location = (x0 + 380, yy)
            dil.label = NODE_LABEL
            _set_dilate(dil, r)
            tree.links.new(binz.outputs[0], dil.inputs[0])
            ero = tree.nodes.new("CompositorNodeDilateErode")
            ero.location = (x0 + 500, yy)
            ero.label = NODE_LABEL
            _set_dilate(ero, -r)
            tree.links.new(dil.outputs[0], ero.inputs[0])
            gap = _math(tree, "SUBTRACT", x0 + 620, yy)
            tree.links.new(ero.outputs[0], gap.inputs[0])
            tree.links.new(binz.outputs[0], gap.inputs[1])
            gap.use_clamp = True
            near = tree.nodes.new("CompositorNodeDilateErode")
            near.location = (x0 + 740, yy)
            near.label = NODE_LABEL
            _set_dilate(near, 3)
            tree.links.new(gap.outputs[0], near.inputs[0])
            wg = _math(tree, "MULTIPLY", x0 + 860, yy, b=wgt)
            tree.links.new(near.outputs[0], wg.inputs[0])
            if acc is None:
                acc = wg
            else:
                mx = _math(tree, "MAXIMUM", x0 + 980, yy)
                tree.links.new(acc.outputs[0], mx.inputs[0])
                tree.links.new(wg.outputs[0], mx.inputs[1])
                acc = mx
        crowd_w = _math(tree, "MULTIPLY", x0 + 1100, y0 - 60, b=crowd)
        tree.links.new(acc.outputs[0], crowd_w.inputs[0])
        crowd_w["fp_tap"] = "crowd"

    hw = _math(tree, "MULTIPLY_ADD", x0 + 700, y0 - 360, b=hw_max - hw_min)
    hw.inputs[2].default_value = hw_min
    tree.links.new(depth01.outputs[0], hw.inputs[0])
    if crowd_w is not None:
        # 詰まっている所は広がりをゼロ(芯だけ)まで縮める。以前は太らせた
        # 絵と元の線を混ぜていたが、混ぜると半端な灰色になり、密度が線に
        # 沿って揺れると太い区間と細い区間が交互に出て点線に見えた(実測:
        # テレビのベゼル)。上乗せ分だけ縮めるのでは足りない: 帆船の船体は
        # 線の間隔が 2倍レンダで 4px しかなく、最細の +2px でも隣と
        # つながって塊になった(実測)。芯が消えないよう、しきい値に小さな
        # 余裕を入れる(Feather の芯の値はちょうど 1.0 で、> 1.0 は偽)
        keep = _math(tree, "SUBTRACT", x0 + 700, y0 - 460, a=1.0)
        tree.links.new(crowd_w.outputs[0], keep.inputs[1])
        hw2 = _math(tree, "MULTIPLY", x0 + 780, y0 - 420)
        tree.links.new(hw.outputs[0], hw2.inputs[0])
        tree.links.new(keep.outputs[0], hw2.inputs[1])
        hw = hw2
    # 奥ほど広がりを縮める(奥度 1 で芯だけ)。詰まりの守りと同じ場所
    far = None
    far_w = max(0.0, min(1.0, float(getattr(scene, "fp_lw_far", 0.0))))
    far_fade = max(0.0, min(1.0, float(getattr(scene, "fp_lw_far_fade", 0.0))))
    if depth_sock is not None and (far_w > 0.0 or far_fade > 0.0):
        far = far_chain(tree, depth_sock, alpha_sock, scene, x0 + 400, y0 - 700,
                        spread=reach)
    if far is not None and far_w > 0.0:
        shrink = _math(tree, "MULTIPLY_ADD", x0 + 780, y0 - 520, b=-far_w)
        shrink.inputs[2].default_value = 1.0            # 1 - far * far_w
        tree.links.new(far.outputs[0], shrink.inputs[0])
        hw3 = _math(tree, "MULTIPLY", x0 + 820, y0 - 480)
        tree.links.new(hw.outputs[0], hw3.inputs[0])
        tree.links.new(shrink.outputs[0], hw3.inputs[1])
        hw = hw3
    thr = _math(tree, "MULTIPLY_ADD", x0 + 860, y0 - 460, b=-1.0 / reach)
    thr.inputs[2].default_value = 1.0 - 1e-3     # 芯(=1.0)は必ず通す
    tree.links.new(hw.outputs[0], thr.inputs[0])
    ink = _math(tree, "GREATER_THAN", x0 + 1120, y0 - 360)
    tree.links.new(fe.outputs[0], ink.inputs[0])
    tree.links.new(thr.outputs[0], ink.inputs[1])
    thr["fp_tap"] = "thr"
    hw["fp_tap"] = "hw"
    # 太らせた領域の先端は Feather の値がしきい値ぎりぎりで、AO の粒で
    # しきい値が揺れると本体から離れた孤立点になる(実測: テレビのベゼル
    # の内側に点線が並んだ)。ぼかした ink が半分に満たない画素は孤立点
    # なので落とす。細い芯がここで落ちても元の線を後で重ねるので消えない
    ib = tree.nodes.new("CompositorNodeBlur")
    ib.location = (x0 + 1240, y0 - 460)
    ib.label = NODE_LABEL
    _set_blur(ib, 2)
    tree.links.new(ink.outputs[0], ib.inputs[0])
    dense = _math(tree, "GREATER_THAN", x0 + 1360, y0 - 460, b=0.5)
    tree.links.new(ib.outputs[0], dense.inputs[0])
    ink2 = _math(tree, "MULTIPLY", x0 + 1480, y0 - 360)
    tree.links.new(ink.outputs[0], ink2.inputs[0])
    tree.links.new(dense.outputs[0], ink2.inputs[1])
    ink2["fp_tap"] = "ink"
    prev = ink2

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
    soft["fp_tap"] = "soft"
    keep_ink["fp_tap"] = "keep"

    g = _math(tree, "MULTIPLY", x0 + 1320, y0 - 400, b=gain)
    tree.links.new(prev.outputs[0], g.inputs[0])
    cl_w = _math(tree, "MINIMUM", x0 + 1480, y0 - 400, b=1.0)
    tree.links.new(g.outputs[0], cl_w.inputs[0])

    # 元の線を足し戻す。
    # 芯(binz)は「線 > しきい値」の2値化で、細い線が密集して灰色に
    # 見える所(帆船の船体、機関車のボイラー)は全部が芯になって塗り
    # 潰れた(実測: 太らせる前の芯の段階で既に黒い塊)。しきい値を上げれば
    # 塊は消えるが、薄い線が芯から外れて消える(0.25 で点線になった)。
    # 芯はしきい値を上げて「はっきりした線」だけにし、芯から外れた薄い
    # 線と灰色は元の線をそのまま重ねて残す(精密と同じ見え方になる)
    cl = _math(tree, "MAXIMUM", x0 + 1520, y0 - 300)
    tree.links.new(cl_w.outputs[0], cl.inputs[0])
    tree.links.new(inv.outputs[0], cl.inputs[1])
    last = cl
    cl_w["fp_tap"] = "gained"
    cl["fp_tap"] = "maxed"

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
        shade["fp_tap"] = "shade"

    # 奥ほど紙の色へ寄せる(空気遠近)。濃さの強弱と同じく表示の薄さで
    # 決めてリニアの倍率にする: 倍率 = 1 - (far * fade)^2.2
    if far is not None and far_fade > 0.0:
        fm = _math(tree, "MULTIPLY", x0 + 1250, y0 - 660, b=far_fade)
        tree.links.new(far.outputs[0], fm.inputs[0])
        fl = _math(tree, "POWER", x0 + 1380, y0 - 660, b=2.2)
        tree.links.new(fm.outputs[0], fl.inputs[0])
        fdk = _math(tree, "SUBTRACT", x0 + 1500, y0 - 660, a=1.0)
        tree.links.new(fl.outputs[0], fdk.inputs[1])
        faded = _math(tree, "MULTIPLY", x0 + 1600, y0 - 480)
        tree.links.new(last.outputs[0], faded.inputs[0])
        tree.links.new(fdk.outputs[0], faded.inputs[1])
        last = faded
        faded["fp_tap"] = "far_fade"

    # 太らせた線は 2値(しきい値)で決めているので、縁がギザギザのまま
    # 50% 縮小に入り、1080p で 2段階のアンチエイリアスしか残らなかった
    # (実測: 町のデモ、4倍拡大で縁が 0/0.5/1 の3値)。縮小の前に SMAA を
    # 掛けて縁をなだらかにする。線の太さは変えない(縁 1px を混ぜるだけ)
    aa = tree.nodes.new("CompositorNodeAntiAliasing")
    aa.location = (x0 + 1600, y0 - 560)
    aa.label = NODE_LABEL
    compat.set_node_value(aa, "threshold", 0.1)
    compat.set_node_value(aa, "contrast_limit", 0.2)
    tree.links.new(last.outputs[0], aa.inputs[0])
    last = aa
    aa["fp_tap"] = "aa"

    out = tree.nodes.new("CompositorNodeInvert")
    out.location = (x0 + 1660, y0 - 400)
    out.label = NODE_LABEL
    tree.links.new(last.outputs[0], out.inputs["Color"])
    out["fp_tap"] = "out"
    dep["fp_tap"] = "dep"
    # 2つ目は「線を描いた画素」。輪郭を外側へ太らせた分はシルエットの
    # 外にあってレンダーレイヤーのアルファが 0 なので、透明背景では
    # 消える(実測: テレビの外周が半分だけ、灰色に見えた)。呼ぶ側が
    # アルファにも立てる
    return out.outputs[0], last.outputs[0]


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
    depth = None
    if far_wanted(scene) and far_range(scene) is not None:
        view_layer.use_pass_z = True
        depth = compat.render_layer_socket(rl, DEPTH_SOCKETS)
    apply_far_sens(tree, scene, depth)
    line_sock = target_socket.links[0].from_socket
    out, ink_sock = build_weight(tree, line_sock, ao, scene,
                                 alpha_sock=rl.outputs.get("Alpha"),
                                 depth_sock=depth)
    for lnk in list(target_socket.links):
        tree.links.remove(lnk)
    tree.links.new(out, target_socket)
    # 線を描いた画素はアルファも立てる。輪郭を外側へ太らせた分は
    # シルエットの外でアルファが 0 になり、透明背景では消えていた
    node = target_socket.node
    if node.type == "SETALPHA" and "Alpha" in node.inputs:
        asock = node.inputs["Alpha"]
        mx = _math(tree, "MAXIMUM", node.location.x - 200, node.location.y - 200)
        if asock.is_linked:
            tree.links.new(asock.links[0].from_socket, mx.inputs[0])
            for lnk in list(asock.links):
                tree.links.remove(lnk)
        else:
            mx.inputs[0].default_value = float(asock.default_value)
        tree.links.new(ink_sock, mx.inputs[1])
        tree.links.new(mx.outputs[0], asock)
    return out


def _descending_ramps(group):
    """線を出す側の ColorRamp(白→暗)。fp_core.apply_line_tuning と同じ判定。"""
    def luma(c):
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    out = []
    for node in group.nodes:
        if node.type != "VALTORGB":
            continue
        ramp = node.color_ramp
        if len(ramp.elements) < 2:
            continue
        cols = node.get("fp_orig_colors")
        if cols is not None and len(cols) != len(ramp.elements):
            cols = None
        first = cols[0] if cols else ramp.elements[0].color
        last = cols[-1] if cols else ramp.elements[-1].color
        if luma(first) > luma(last):
            out.append(node)
    return out


def apply_far_sens(tree, scene, depth_sock):
    """奥ほど線を減らす: 検出グループの ColorRamp の手前で勾配を割る。

    しきい値を奥度で上げるのと同じ。倍率 s(fp_lw_far_sens)で、奥度 1 の
    所は勾配が 1/s になる(= 感度 s と同じ)。fp_core には触らず、
    fp_core.apply_far_relief と同じく「毎回外してから挿す」。
    グループに Depth の入力を1本足す(無いときだけ)。
    戻り値は挿した ColorRamp の数。
    """
    from . import fp_core
    gnode = next((n for n in tree.nodes
                  if n.type == "GROUP" and n.node_tree is not None
                  and n.node_tree.name.startswith(fp_core.NODE_GROUP_PREFIX)), None)
    if gnode is None:
        return 0
    group = gnode.node_tree
    # --- 前回の挿し込みを外す
    for ramp in [n for n in group.nodes if n.type == "VALTORGB"]:
        src = ramp.get("fp_far_src")
        if src is None:
            continue
        for lk in list(ramp.inputs[0].links):
            group.links.remove(lk)
        node = group.nodes.get(src["node"])
        if node is not None and int(src["index"]) < len(node.outputs):
            group.links.new(node.outputs[int(src["index"])], ramp.inputs[0])
        del ramp["fp_far_src"]
    for n in [n for n in group.nodes if n.label == FAR_LABEL]:
        group.nodes.remove(n)

    sens = max(1.0, min(4.0, float(getattr(scene, "fp_lw_far_sens", 1.0))))
    if depth_sock is None or sens <= 1.0 or far_range(scene) is None:
        return 0
    if "Depth" not in [i.name for i in gnode.inputs]:
        group.interface.new_socket("Depth", in_out="INPUT",
                                   socket_type="NodeSocketFloat")
    tree.links.new(depth_sock, gnode.inputs["Depth"])
    gi = next((n for n in group.nodes if n.type == "GROUP_INPUT"), None)
    if gi is None or "Depth" not in gi.outputs:
        return 0
    alpha = gi.outputs.get("Alpha")
    if alpha is not None and not gnode.inputs["Alpha"].is_linked:
        rl = next((n for n in tree.nodes if n.type == "R_LAYERS"), None)
        if rl is not None and "Alpha" in rl.outputs:
            tree.links.new(rl.outputs["Alpha"], gnode.inputs["Alpha"])
    # 線の検出は Sobel の 1〜2px 幅なので、伸ばす量は少なくてよい
    far = far_chain(group, gi.outputs["Depth"], alpha, scene, -900, -900,
                    spread=6, label=FAR_LABEL)
    # 倍率 = 1 / (1 + (s - 1) * far)
    den = _math(group, "MULTIPLY_ADD", -600, -900, b=sens - 1.0)
    den.inputs[2].default_value = 1.0
    group.links.new(far.outputs[0], den.inputs[0])
    fac = _math(group, "DIVIDE", -480, -900, a=1.0)
    group.links.new(den.outputs[0], fac.inputs[1])
    den.label = fac.label = FAR_LABEL
    count = 0
    for ramp in _descending_ramps(group):
        sock = ramp.inputs[0]
        if not sock.is_linked:
            continue
        src = sock.links[0].from_socket
        ramp["fp_far_src"] = {"node": src.node.name,
                              "index": list(src.node.outputs).index(src)}
        mul = _math(group, "MULTIPLY", ramp.location.x - 160, ramp.location.y - 40)
        mul.label = FAR_LABEL
        mul.hide = True
        group.links.new(src, mul.inputs[0])
        group.links.new(fac.outputs[0], mul.inputs[1])
        for lk in list(sock.links):
            group.links.remove(lk)
        group.links.new(mul.outputs[0], sock)
        count += 1
    return count


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


def measure_edges(scene, view_layer, percent=100):
    """1回レンダして、線の画素における d = 1 - AO の分位点を返す。

    絵ごとに 15 倍ひらくので固定値では配れない。カットごとに1回
    測って固定する。

    d は合成と同じ鎖(dep_chain: 背景埋め -> ぼかし -> 1-AO)を通し、
    EXR(float)で読む。生の AO を PNG で読んでいたときは 8bit の
    量子化で最初のしきい値が 1/255 = 0.0039 になっていた(実測)。
    ぼかしはレンダー倍率で割るので、倍率が違っても同じ広さ。
    100%(= 細線化 200% の半分、最終の大きさ)で測る。50% だと線の太さが
    モデルに対して倍になり、密度が 0.08 -> 0.5 に膨れた(実測)。
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
    view_layer.use_pass_z = True

    tmp = tempfile.mkdtemp(prefix="fp_lw_")
    keep_pct = scene.render.resolution_percentage
    fo = tree.nodes.new("CompositorNodeOutputFile")
    fo.label = NODE_LABEL
    # 4.x は base_path / file_slots、5.x は directory / file_output_items。
    # 名前も構造も違うので compat 経由で触る
    compat.file_output_set_dir(fo, tmp)
    compat.file_output_clear_slots(fo)
    # 強弱の鎖が既に組んであると、合成の入り口を辿った先は太らせた後の
    # 絵になる(実測: 密度が 0.08 -> 0.54 に膨れ、しきい値も太らせた画素で
    # 決まっていた)。鎖の入口(元の線)を読む
    line_src = None
    for n in tree.nodes:
        if n.label == NODE_LABEL and n.get("fp_tap") == "inv"                 and n.inputs["Color"].is_linked:
            line_src = n.inputs["Color"].links[0].from_socket
            break
    if line_src is None:
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
    # 奥の扱い(fp_lw_far*)の距離も同じレンダで測る。線の画素の深度の
    # 5% 点から 95% 点。深度は倍率に依らない
    z_sock = compat.render_layer_socket(rl, DEPTH_SOCKETS)
    if z_sock is not None:
        compat.file_output_add_slot(fo2, "z", "OPEN_EXR", "RGBA")
        tree.links.new(z_sock, fo2.inputs["z"])
    # 色管理を通すと値が変わり、分位点がずれる
    try:
        fo.format.color_management = "OVERRIDE"
        fo.format.view_settings.view_transform = "Standard"
        fo.format.view_settings.look = "None"
    except (AttributeError, TypeError):
        pass
    # 線だけを測る。合成の入り口は「ビューティの上に線」なので、白
    # プレビューが切れているとモデルの陰影が線として数えられ、密度が
    # 0.5〜0.9 になり、しきい値も陰影の AO で決まっていた(実測: STEP0 は
    # 白プレビューを最後に立てるので、計測は必ず陰影付きで走っていた)。
    # 計測の間だけ白にして、終わったら戻す
    from . import fp_core
    was_white = bool(getattr(scene, "fp_white_preview", False))
    if not was_white:
        fp_core.set_white_preview(
            scene, True, keep_glass=getattr(scene, "fp_white_keep_glass", True))
    try:
        scene.render.resolution_percentage = percent
        bpy.ops.render.render(write_still=False)
        d_all = _load_float(_find(tmp, "dep"))
        z_all = _load_float(_find(tmp, "z")) if z_sock is not None else None
        ln, _ = _load_gray(_find(tmp, "line"))
        al, _ = _load_gray(_find(tmp, "sil"))
    finally:
        tree.nodes.remove(fo)
        tree.nodes.remove(fo2)
        for n in chain_nodes:
            tree.nodes.remove(n)
        if not was_white:
            fp_core.set_white_preview(scene, False)
        scene.render.resolution_percentage = keep_pct
        # 測るたびに temp が残っていた
        shutil.rmtree(tmp, ignore_errors=True)

    if d_all.shape != ln.shape or d_all.shape != al.shape:
        return None
    ink = 1.0 - ln
    sil = al > 0.5
    on = (ink > getattr(scene, "fp_lw_bin", 0.15)) & sil
    if int(on.sum()) < 200:
        return None
    # 線の密度(シルエットに占める線の割合)。密なモデルほど太らせる余地が
    # 無いので、build_weight が最大幅を下げるのに使う。実測(精密):
    #   スザンヌ 1.4% / カメラ 8% / メカ 20% / 機関車 23% / 帆船 36%
    try:
        scene.fp_lw_density = float(on.sum()) / float(max(int(sil.sum()), 1))
    except (AttributeError, TypeError):
        pass
    if z_all is not None and z_all.shape == ln.shape:
        # シルエットの縁の画素は深度が背景(クリップ距離)になることがあり、
        # 4.2 では 95% 点が 1000 になった(実測)。縁を 1px 削った内側だけ
        inner = sil.copy()
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                inner &= np.roll(np.roll(sil, dy, 0), dx, 1)
        z = z_all[on & inner]
        z = z[np.isfinite(z) & (z < 1e6)]
        if len(z) >= 200:
            try:
                scene.fp_lw_far_start = float(np.percentile(z, 5))
                scene.fp_lw_far_end = float(np.percentile(z, 95))
            except (AttributeError, TypeError):
                pass
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
