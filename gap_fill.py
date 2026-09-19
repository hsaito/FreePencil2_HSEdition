"""葉の隙間を線にしない(手描き背景モード)。

ヤシの葉や針葉樹は葉の間から空が見える。その穴の縁は「葉の色 -> 背景」
の差で線になり、葉1枚ごとに輪郭が出て遠くでは黒い塊になる。
線を検出するグループに入る前で、AOV の穴を Inpaint で埋め、閉じた
(膨張してから収縮した)alpha を一緒に渡す。px より狭い穴だけ埋まり、
外側の輪郭は動かない。alpha を渡さないと、グループが白に載せる段で
穴が戻る(実測)。既定 0 = ノードを1つも挿さない。
"""

from . import compat

NODE_LABEL = "FreePencil_gap_fill"


def apply(tree, scene, rl, group_node) -> int:
    """グループの画像入力(mecha_color と Image)と Alpha の手前に隙間埋めを挿す。

    Image(ビューティ)と Depth も埋める。mecha_color だけ埋めても穴の線が
    残った(実測: 深度チャンネルが穴の深度の段差を線にする)。戻り値はノード数。
    """
    from . import line_weight
    px = int(getattr(scene, "fp_gap_fill", 0))
    pct = max(1, getattr(scene.render, "resolution_percentage", 100))
    px = max(0, round(px * pct / 200.0))          # 200% 基準の px
    if px <= 0:
        return 0
    alpha = rl.outputs.get("Alpha")
    dst_a = group_node.inputs.get("Alpha")
    if alpha is None or dst_a is None:
        return 0
    x, y = group_node.location.x - 700, group_node.location.y - 900
    made = []

    def new(idn, dx, dy):
        n = compat.new_node(tree, idn)      # 5.x は MixRGB が別名(compat が吸収)
        n.label = NODE_LABEL
        n.location = (x + dx, y + dy)
        n.hide = True
        made.append(n)
        return n

    # 穴の縁の画素は alpha が半端で、色は背景の黒と混ざって暗い。そのまま
    # だと Inpaint(alpha 0 だけ埋める)が縁を残し、暗い縁が線になった
    # (実測: 埋めても穴の輪郭が細く残った)。縁も穴として埋める
    hard = line_weight._math(tree, "GREATER_THAN", x - 160, y, b=0.98)
    hard.label = NODE_LABEL
    hard.hide = True
    made.append(hard)
    tree.links.new(alpha, hard.inputs[0])
    alpha = hard.outputs[0]

    # 閉じた alpha(膨張してから収縮)。px より狭い穴だけ埋まる
    dil = new("CompositorNodeDilateErode", 160, -160)
    line_weight._set_dilate(dil, px)
    tree.links.new(alpha, dil.inputs[0])
    ero = new("CompositorNodeDilateErode", 320, -160)
    line_weight._set_dilate(ero, -px)
    tree.links.new(dil.outputs[0], ero.inputs[0])

    def _math(tree_, op, px_, py_, a=None, b=None):
        n = line_weight._math(tree_, op, px_, py_, a=a, b=b)
        n.label = NODE_LABEL
        n.hide = True
        return n

    def fill(src, dst, dy):
        sa = new("CompositorNodeSetAlpha", 0, dy)
        compat.set_node_value(sa, "mode", "REPLACE_ALPHA")
        tree.links.new(src, sa.inputs["Image"])
        tree.links.new(alpha, sa.inputs["Alpha"])
        ip = new("CompositorNodeInpaint", 160, dy)
        if hasattr(ip, "distance"):
            ip.distance = px
        else:
            line_weight._set_num_socket(ip, "Size", px)
        tree.links.new(sa.outputs[0], ip.inputs[0])
        mix = new("CompositorNodeMixRGB", 480, dy)
        compat.set_node_value(mix, "blend_type", "MULTIPLY")
        mix.inputs[0].default_value = 1.0
        tree.links.new(ip.outputs[0], mix.inputs[1])
        tree.links.new(ero.outputs[0], mix.inputs[2])
        for lk in list(dst.links):
            tree.links.remove(lk)
        tree.links.new(mix.outputs[0], dst)

    # Depth も埋める。穴の深度は背景(クリップ距離)で、深度チャンネルが
    # そこを段差として線にする(実測: t54 は深度で穴の線が残った)
    for i, name in enumerate(("mecha_color", "Image")):
        dst = group_node.inputs.get(name)
        if dst is None or not dst.is_linked:
            continue
        fill(dst.links[0].from_socket, dst, -i * 100)
    # Depth は 1/z にしてから埋める。深度そのもの(1 を超える値)を Inpaint
    # に通すと穴の中が 0 になり、深度チャンネルが穴を黒い棒にした(実測)。
    # 1/z は 0..1 に収まり、背景(クリップ距離)は 0 なので埋まる
    dst = group_node.inputs.get("Depth")
    if dst is not None and dst.is_linked:
        zsrc = dst.links[0].from_socket
        inv = _math(tree, "DIVIDE", x, y - 300, a=1.0)
        zmax = _math(tree, "MAXIMUM", x - 120, y - 300, b=1e-3)
        tree.links.new(zsrc, zmax.inputs[0])
        tree.links.new(zmax.outputs[0], inv.inputs[1])
        made += [inv, zmax]
        back = _math(tree, "DIVIDE", x + 620, y - 300, a=1.0)
        bmax = _math(tree, "MAXIMUM", x + 560, y - 300, b=1e-6)
        made += [back, bmax]
        fill(inv.outputs[0], bmax.inputs[0], -300)
        tree.links.new(bmax.outputs[0], back.inputs[1])
        for lk in list(dst.links):
            tree.links.remove(lk)
        tree.links.new(back.outputs[0], dst)
    for lk in list(dst_a.links):
        tree.links.remove(lk)
    tree.links.new(ero.outputs[0], dst_a)
    return len(made)
