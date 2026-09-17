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
    """グループの mecha_color / Alpha 入力の手前に隙間埋めを挿す。戻り値はノード数。"""
    from . import line_weight
    px = int(getattr(scene, "fp_gap_fill", 0))
    pct = max(1, getattr(scene.render, "resolution_percentage", 100))
    px = max(0, round(px * pct / 200.0))          # 200% 基準の px
    if px <= 0:
        return 0
    src = rl.outputs.get("mecha_color")
    alpha = rl.outputs.get("Alpha")
    dst = group_node.inputs.get("mecha_color")
    dst_a = group_node.inputs.get("Alpha")
    if src is None or alpha is None or dst is None or dst_a is None:
        return 0
    for lk in list(dst.links) + list(dst_a.links):
        tree.links.remove(lk)
    x, y = group_node.location.x - 700, group_node.location.y - 900
    made = []

    def new(idn, dx, dy):
        n = tree.nodes.new(idn)
        n.label = NODE_LABEL
        n.location = (x + dx, y + dy)
        n.hide = True
        made.append(n)
        return n

    sa = new("CompositorNodeSetAlpha", 0, 0)
    compat.set_node_value(sa, "mode", "REPLACE_ALPHA")
    tree.links.new(src, sa.inputs["Image"])
    tree.links.new(alpha, sa.inputs["Alpha"])
    ip = new("CompositorNodeInpaint", 160, 0)
    if hasattr(ip, "distance"):
        ip.distance = px
    else:
        line_weight._set_num_socket(ip, "Size", px)
    tree.links.new(sa.outputs[0], ip.inputs[0])
    dil = new("CompositorNodeDilateErode", 160, -160)
    line_weight._set_dilate(dil, px)
    tree.links.new(alpha, dil.inputs[0])
    ero = new("CompositorNodeDilateErode", 320, -160)
    line_weight._set_dilate(ero, -px)
    tree.links.new(dil.outputs[0], ero.inputs[0])
    mix = new("CompositorNodeMixRGB", 480, 0)
    mix.blend_type = "MULTIPLY"
    mix.inputs[0].default_value = 1.0
    tree.links.new(ip.outputs[0], mix.inputs[1])
    tree.links.new(ero.outputs[0], mix.inputs[2])
    tree.links.new(mix.outputs[0], dst)
    tree.links.new(ero.outputs[0], dst_a)
    return len(made)
