"""Scene properties used by FreePencil operators."""

import bpy
import logging
from bpy.props import (
    FloatProperty,
    FloatVectorProperty,
    IntProperty,
    EnumProperty,
    BoolProperty,
)

logger = logging.getLogger(__name__)

def _update_line_tuning(self, context):
    """線の感度/チャンネル強さスライダーの即時反映。

    生成済みの FreePencil ノードグループのランプ位置を直接更新する
    (ノードエディタを開かずにサイドバーだけで調整できる)。
    """
    from . import fp_core
    from . import line_weight
    scene = context.scene
    for ng in bpy.data.node_groups:
        if ng.name.startswith(fp_core.NODE_GROUP_PREFIX):
            fp_core.apply_line_tuning(
                ng,
                line_weight.effective_sensitivity(scene),
                fp_core.channel_strengths_from_scene(scene))


def _update_far_relief(self, context):
    """遠景つぶれ軽減のスライダーを、生成済みノードへ即時反映する。"""
    from . import fp_core
    from . import line_weight
    scene = context.scene
    for ng in bpy.data.node_groups:
        if ng.name.startswith(fp_core.NODE_GROUP_PREFIX):
            fp_core.far_relief_from_scene(ng, scene)


def _apply_preview_mode(scene) -> None:
    """プレビューの種類を1か所で反映する。

    どちらも「PROノードの Image 入力に何を流すか」を変えるだけなので、
    同時には成立しない。片方を立てるときは必ずもう片方を下ろす。
    """
    from . import fp_core
    mode = getattr(scene, "fp_preview_mode", "NONE")
    fp_core.set_white_preview(
        scene, mode == "WHITE",
        keep_glass=getattr(scene, "fp_white_keep_glass", True))
    fp_core.set_mono_light_preview(
        scene, mode == "MONO_LIGHT",
        floor=getattr(scene, "fp_mono_floor", 0.25))
    if mode == "MONO_LIGHT":
        # 陰影の素になるパスが無いと真っ黒になる
        vl = bpy.context.view_layer
        if not vl.use_pass_diffuse_direct:
            vl.use_pass_diffuse_direct = True
            logger.info("Enabled the Diffuse Direct pass for mono preview")
    logger.info(f"Preview mode: {mode}")


def _update_preview_mode(self, context):
    _apply_preview_mode(context.scene)


def _update_white_preview(self, context):
    """旧トグル。種類へ橋渡しして、古いスクリプトでも動くようにする。"""
    scene = context.scene
    want = "WHITE" if scene.fp_white_preview else "NONE"
    if getattr(scene, "fp_preview_mode", "NONE") != want:
        scene.fp_preview_mode = want   # 種類側の更新フックが実処理をする
    else:
        _apply_preview_mode(scene)


def _update_white_keep_glass(self, context):
    """プレビュー中にガラス維持を切り替えたら復元→再適用で反映する。"""
    from . import fp_core
    scene = context.scene
    if scene.fp_white_preview:
        fp_core.set_white_preview(scene, False)
        fp_core.set_white_preview(scene, True,
                                  keep_glass=scene.fp_white_keep_glass)


def register_props():
    """プロパティを登録する関数"""
    scene = bpy.types.Scene

    t = bpy.app.translations.pgettext
    color_type_items = [
        ('mecha_color', t("Mecha Color"), t("Mecha Color")),
        ('mask_color',  t("Mask Color(paint to erase lines)"),
         t("Lines vanish where painted. The brightness does not matter")),
        ('line_color',  t("Line Color(line darkness)"),
         t("Sets how dark the line is. White makes it invisible")),
    ]
    node_type_items = [
        ('test', t("Test Node"), t("Test Node")),
        ('pro',  t("Pro Node"),  t("Pro Node")),
    ]

    props_to_register = {
        "fp_sharp_clear": BoolProperty(
            name="clear sharp",
            description="Erase outline's sharp edges",
            default=False
        ),
        "fp_mat_count": BoolProperty(
            name="material ID",
            description="Add the material ID",
            default=False
        ),
        "fp_sharp_auto": BoolProperty(
            name="Auto edge angle",
            description=(
                "Choose the sharp-edge angle automatically from the mesh's "
                "dihedral-angle distribution (per object)"
            ),
            # 既定OFF: 既存ワークフロー(特にボーン系キャラ)の挙動を変えない。
            # 一括評価パイプラインはプリセットで明示的にONにする。
            default=False
        ),
        "fp_auto_split_floor": FloatProperty(
            name="Artificial split floor",
            description=(
                "Lowest angle the auto threshold may pick for a model that "
                "has no structural edges at all. Too low and a smoothly "
                "curving surface gets cut across at an arbitrary place"
            ),
            # 既定 5.0 = v2.7 と同じ。STEP0 が仕上がり(fp_auto_style)ごとに
            # 入れる: 精密 5.0 / 強弱 14.0。14 の根拠は utils.py の
            # ARTIFICIAL_SPLIT_FLOOR
            default=5.0, min=1.0, max=45.0, step=0.5, precision=1
        ),
        "fp_sharp_edges": FloatProperty(
            name="Line sharp edges",
            description="Outline's angle threshold.",
            default=30.0,
            min=0.0,
            max=180.0
        ),
        "fp_seam_boundaries": BoolProperty(
            name="Seam/material boundaries",
            description=(
                "Treat UV seams and material borders as island boundaries "
                "in addition to the edge angle"
            ),
            default=False
        ),
        "fp_min_island_area_pct": FloatProperty(
            name="Min island area %",
            description=(
                "Merge islands smaller than this % of total mesh area "
                "into their largest neighbor (0 = off)"
            ),
            # 既定OFF(0): 既存挙動を変えない。バッチはプリセットで0.02を指定
            #
            # 上限は 5% だったが、これは「小島の掃除」しか想定していない値。
            # 実測では 1〜2% で塗りが広くまとまり(スザンヌ 429色 -> 6色)、
            # メカは 5% でパネルごとに1色になる。有機的な形はさらに上まで
            # 上げると最終的にルースパーツ単位の1色に行き着くので、
            # そこまで動かせるようにする
            default=0.0,
            min=0.0,
            max=100.0,
            step=0.01,
            precision=3
        ),
        "fp_ridge_amount": FloatProperty(
            name="Ridge relief",
            description=(
                "Add a faint normal-based relief inside each island so that "
                "smooth ridges (a brow, a fold) get a line. 0 = off"
            ),
            # 島の色は面ごとに一定なので、足しても島境界の段差は残る。
            # 隣接島の色距離の契約(既定0.5)を割らないよう小さく保つ
            default=0.0,
            min=0.0,
            max=0.5,
            step=0.01,
            precision=3
        ),
        "fp_ridge_radius": FloatProperty(
            name="Ridge scale",
            description=(
                "How far to look when deciding the 'overall direction' of a "
                "surface, as a fraction of the object size. Smaller = thinner "
                "lines on finer features"
            ),
            default=0.08,
            min=0.005,
            max=0.5,
            step=0.005,
            precision=3
        ),
        "fp_curve_blur_auto": BoolProperty(
            name="Auto blur on subdivided objects",
            description=(
                "For objects that carry a Subdivision modifier, cut islands "
                "at a low angle and then dissolve every boundary that is not "
                "a sharp edge. The modelling cage stops showing up as lines "
                "while the real creases stay"
            ),
            # 既定OFF。sample.blend で「ぼかし無し」と並べて比べたところ、
            # ぼかした方が悪かった。5度で切ると極小の島が大量にでき、少ない
            # 回数では中途半端にしか混ざらない。溶けきらない色差が破片として
            # 残り、眉と鼻のまわりにギザギザが出る。回数を増やすと今度は
            # 領域全体が一色に潰れる。どちらにも良い点が無い。
            #
            # 「4回で良くなった」と一度判断したが、比較対象が
            # 「5度で切っただけ(切りすぎ)」であって通常動作ではなかった。
            default=False
        ),
        "fp_curve_blur": IntProperty(
            name="Curve blur",
            description=(
                "Smooth the paint color across low-angle edges so the mesh "
                "grid on subdivided surfaces stops turning into lines. "
                "Sharp edges keep their hard step (0 = off)"
            ),
            # 既定OFF。サブサーフのかかった曲面ではメッシュの格子が
            # そのまま線になるが、島をまとめて消すと目や口の稜線まで
            # 消える(実測: スザンヌで内部の線が全滅)。島は残したまま
            # なめらかな境界の段差だけを溶かす
            default=0,
            min=0,
            max=20
        ),
        "fp_curve_blur_angle": FloatProperty(
            name="Curve blur angle",
            description=(
                "Only edges below this dihedral angle get smoothed. "
                "Edges above it keep a hard color step, so their lines stay"
            ),
            default=25.0,
            min=1.0,
            max=90.0,
            step=100,
            precision=1
        ),
        "fp_color_type": EnumProperty(
            name="Vertex color type",
            description="Select vertex color type.",
            items=color_type_items,
            default='mecha_color'
        ),
        "fp_node_type": EnumProperty(
            name="Select node type",
            description="Select Node Type",
            items=node_type_items,
            default='test'
        ),
        # Requires Blender 4.3+ for Real-Time Compositor preview
        "fp_enable_compositor_view": BoolProperty(
            name="Enable Compositor Preview",
            description="Enable Compositor Preview",
            default=True
        ),
        "fp_far_relief": FloatProperty(
            name="Far crush relief",
            description=(
                "Thin out lines where they have merged into solid black "
                "(typically the far background of a large set). "
                "0 = off, no change to the image"
            ),
            default=0.0, min=0.0, max=1.0, step=0.05, precision=2,
            update=_update_far_relief
        ),
        "fp_far_relief_radius": FloatProperty(
            name="Relief radius",
            description=(
                "How far to look when measuring how crowded the lines are, "
                "in pixels. Larger = only wide black areas are thinned"
            ),
            default=6.0, min=1.0, max=32.0, step=100, precision=0,
            update=_update_far_relief
        ),
        "fp_far_relief_threshold": FloatProperty(
            name="Relief threshold",
            description=(
                "How crowded an area must be before it is thinned. "
                "Lower = starts working on sparser lines"
            ),
            default=0.35, min=0.05, max=0.95, step=0.05, precision=2,
            update=_update_far_relief
        ),
        "fp_line_sensitivity": FloatProperty(
            name="Line sensitivity",
            description=(
                "Scale the line-detection thresholds inside the node group. "
                "Lower = weaker edges also become solid lines (1.0 = raw node)"
            ),
            # 既定を 0.5 にする。1.0 はノードの素の値で、塗り分けは
            # できているのに検出しきい値に届かず線が出ない境界が多かった。
            # 線が出るかは RGB距離で決まり、境目は実測で 0.05〜0.14。
            # 明度の近い隣接色(水色と白など)がここを越えられていない。
            #
            # 実測(1920等倍・4モデルのインク):
            #   戦車 0.0855 -> 0.0919 / メカ 0.1048 -> 0.1110
            #   帆船 0.0482 -> 0.0534 / カメラ 0.0894 -> 0.1004
            # 目視でも索具が点線から実線になり、ノイズは増えなかった。
            # 0.35 まで下げてもメカは破綻しないので余裕を残して 0.5。
            default=0.5,
            min=0.05,
            max=2.0,
            step=0.05,
            precision=2,
            update=_update_line_tuning
        ),
        # --- 線の強弱(入り抜き) -------------------------------------
        # くぼみ(AO)が深いほど線を太くする。詳細と実測は line_weight.py
        "fp_line_weight": BoolProperty(
            name="Line weight from cavities",
            description=(
                "Thicken the line where the shape is recessed and thin it "
                "where it is open, using the ambient-occlusion pass. "
                "Needs STEP3 to be run again"
            ),
            # 既定OFF。既存ファイルの絵を勝手に変えない
            default=False,
            # 切り替えたら線のしきい値も連動させる。STEP3 をやり直す
            # までノードは組まれないが、線の量はその場で変わる
            update=_update_line_tuning
        ),
        "fp_lw_island_bias": FloatProperty(
            name="Split less",
            description=(
                "While line weight is on, allow fewer islands so the mesh "
                "is cut more coarsely. A thin rim seen edge-on stops "
                "turning every mesh ring into its own line. "
                "1.0 = do not change it"
            ),
            # 既定 1.0(=何もしない)。
            #
            # はじめ 0.4 を既定にしたが、それは線の感度 0.25 で測った
            # 判断だった。v2.7 の既定である感度 0.5 で測り直すと、
            # 0.4 ではスザンヌの口の輪郭が消える。感度0.5での実測:
            #   島1.0  自動10.7度  口○  耳×(平行4本)
            #   島0.7  自動12.2度  口×  耳×(まだ平行3本)
            #   島0.6  自動12.4度  口×  耳×
            #   島0.5  自動13.3度  口×  耳×
            #   島0.4  自動14.0度  口×  耳○
            # 感度0.5では「口を残したまま耳を綺麗にする」値が無い。
            # 顔の部位が消えるほうが害が大きいので、既定は無効にして
            # 使う人が選べるようにする。感度を 0.25 まで下げるなら
            # 0.4 で両立する(実測済み)
            default=1.0, min=0.05, max=1.0, step=0.05, precision=2
        ),
        "fp_lw_line_bias": FloatProperty(
            name="Weaken the line",
            description=(
                "While line weight is on, raise the line-detection "
                "threshold by this factor so fewer, cleaner lines are "
                "thickened. 1.0 = do not change it"
            ),
            # 既定1.2。はじめ1.8にしたが、「切る細かさ」と重なって効きすぎ、
            # スザンヌの口の輪郭が消えた。両方を切り分けて実測した結果:
            #   島1.0 線1.0  口○ 耳×(平行4本)
            #   島0.4 線1.0  口○ 耳○
            #   島0.4 線1.2  口○ 耳○   <- これ
            #   島0.4 線1.4  口が欠け始める
            #   島0.4 線1.8  口が消える
            # メカ側は 1.8 のほうが綺麗になる(車 7.85% -> 7.38%)ので、
            # メカ中心のカットでは手で上げる
            # 1.2 -> 1.0。感度を弱めると検出の境目にある薄い線がとびとびになり、
            # 点線に見えた(実測: テレビのベゼル内側の線)。線の量は精密と
            # 同じにして、強弱は太さと濃さだけで付ける
            default=1.0, min=1.0, max=4.0, step=0.1, precision=2,
            update=_update_line_tuning
        ),
        "fp_lw_strength": FloatProperty(
            name="Weight strength",
            description=(
                "Multiplier on the step widths. 1.0 = 12/8/5/3/2 px before "
                "the 50% shrink"
            ),
            default=1.0, min=0.2, max=3.0, step=0.05, precision=2
        ),
        "fp_lw_bin": FloatProperty(
            name="Weight binarize",
            description=(
                "How dark a pixel must be to count as line before "
                "thickening. Lower = faint lines survive"
            ),
            # 0.15 だと、細い線が密集して灰色に見える所が全部芯になって
            # 塗り潰れた(帆船・機関車)。0.5 でも、薄い線(山が 0.5 前後)の
            # 芯がとびとびになり、その点が隣の濃い線の濃さで黒く塗られて
            # 点線に見えた(テレビのベゼル内側)。0.7 で「中心が黒い線」
            # だけを芯にする。芯から外れた薄い線は元の線を重ねて残すので
            # 消えない(以前 0.25 で点線になったのは足し戻しが無かった頃)
            default=0.7, min=0.02, max=0.9, step=0.01, precision=2
        ),
        "fp_lw_deep_thick": BoolProperty(
            name="Thick in cavities",
            description=(
                "Off: open areas (the outline) are thick and lines thin as "
                "they enter a crease, like a pen drawing. On: the reverse"
            ),
            default=False
        ),
        "fp_lw_tone": FloatProperty(
            name="Weight tone",
            description=(
                "Also vary darkness by step: the thinnest step fades to "
                "grey while the thickest stays black. 0 = width only"
            ),
            # 太さは整数画素で頭打ち(line_weight.build_weight に実測)。
            # 0.5 だと輪郭が灰色になって汚く見えた。0.25 は見てほぼ黒のまま
            # 少しだけ軽くなる。他の強弱のつまみと同じく反映は STEP3
            default=0.25, min=0.0, max=1.0, step=0.05, precision=2
        ),
        "fp_lw_gain": FloatProperty(
            name="Weight darkness",
            description=(
                "Lift the ink after the 50% shrink so the thin steps stay "
                "black"
            ),
            # 1.4 -> 1.0。薄い線の芯はしきい値をまたいでとびとびになり、
            # そこだけ持ち上げると点線に見えた(実測: テレビのベゼルの
            # 内側の線)。元の線は MAX で足し戻すので、持ち上げなくても
            # 消えない。強い線は元から 1.0 なので gain は要らない
            default=1.0, min=1.0, max=3.0, step=0.05, precision=2
        ),
        "fp_lw_crowd": FloatProperty(
            name="Keep crowded lines thin",
            description=(
                "Where lines are packed together, do not thicken them. "
                "A thin rim seen edge-on turns the mesh rings into several "
                "parallel lines that would otherwise merge into one blob. "
                "0 = off"
            ),
            # 既定ON。実測でスザンヌの耳と車のグリルが黒く潰れ、
            # 素の線より悪くなった。抑制すると潰れが解け、詰まって
            # いない場所(キャラの輪郭など)は1画素も変わらない
            default=1.0, min=0.0, max=1.0, step=0.05, precision=2
        ),
        "fp_lw_crowd_radius": IntProperty(
            name="Crowding radius",
            description=(
                "How far to look when deciding that lines are packed, in "
                "pixels of the render (before the 50% shrink)"
            ),
            default=10, min=1, max=40
        ),
        "fp_lw_crowd_threshold": FloatProperty(
            name="Crowding threshold",
            description=(
                "How packed an area must be before it stops being "
                "thickened. Lower = starts working on sparser lines"
            ),
            default=0.12, min=0.02, max=0.95, step=0.05, precision=2
        ),
        "fp_lw_ao_blur": IntProperty(
            name="Cavity smoothing",
            description=(
                "Blur the cavity map before it drives the width. "
                "EEVEE's AO is ray-traced and grainy; the grain turns a "
                "single stroke into a dashed line. Larger = smoother "
                "taper along a stroke"
            ),
            # 4 -> 12 (2026-09-14)。太さは深さに連続に追従するので、深さを
            # 線に沿ってならすと入り抜きがなめらかになる。4/12/24 を出荷
            # どおりの経路で比べ、12 は眉の端がなめらかに細り、カメラの
            # レンズと車も締まって見えた。24 は眉全体が太くなって差が消える
            default=12, min=0, max=48
        ),
        "fp_lw_ao_dist": FloatProperty(
            name="Cavity radius",
            description=(
                "How far to look when deciding how recessed a point is, "
                "as a fraction of the scene size. Not in scene units: an "
                "absolute value stops working as soon as the model is "
                "bigger or smaller"
            ),
            # シーン単位の絶対値にしていたら、大きいモデルで効かなかった。
            # 実測(既定0.6のまま、段の境目の幅):
            #   スザンヌ等倍(半径1.82)  0.031  効く
            #   10倍(半径18.2)          0.0039 ほぼ効かない
            #   0.1倍(半径0.18)         0.051  効く
            default=0.6, min=0.01, max=4.0, step=0.05, precision=3
        ),
        # 段の境目。d = 1 - AO の分位点。モデルごとに15倍ひらくので
        # 「しきい値を測る」ボタンでカットごとに入れ直す
        **{
            f"fp_lw_e{i}": FloatProperty(
                name=f"Weight edge {i}",
                description="Step boundary on 1 - AO. Measure it per cut",
                default=d, min=0.0, max=1.0, step=0.001, precision=4
            )
            for i, d in enumerate((0.0019, 0.0147, 0.0453, 0.1051), start=1)
        },
        **{
            f"fp_ch_{ch}": FloatProperty(
                name=f"{label} strength",
                description=(
                    f"Line strength of the {label} channel. "
                    "1.0 = current, higher = more/stronger lines, 0 = off"
                ),
                default=1.0,
                min=0.0,
                max=2.0,
                step=0.05,
                precision=2,
                subtype='FACTOR',
                update=_update_line_tuning
            )
            for ch, label in (
                ("mecha", "Mecha"), ("depth", "Depth"), ("bone", "Bone"),
                ("gen", "Generate"), ("mat", "Material"),
            )
        },
        # STEP0 の仕上がり。v2.7 の挙動を「精密」として残し、AO の強弱は
        # 別のスタイルとして選ぶ。既定は精密(既存ファイルの出力を変えない)
        "fp_auto_style": EnumProperty(
            name="Finish",
            description="What STEP0 aims for",
            items=[
                ('PRECISE', "Precise (mech)",
                 "Uniform lines, every panel edge. Same output as v2.7"),
                ('WEIGHTED', "Weighted (hand-drawn)",
                 "Line weight from cavities (AO): the outline is thick and "
                 "lines thin as they enter a crease. Smooth surfaces are "
                 "split less (14 deg floor, ridge 0.45) and the AO "
                 "thresholds are measured for this shot"),
            ],
            default='PRECISE'
        ),
        # STEP0 全自動が適用する項目の個別ON/OFF
        **{
            name: BoolProperty(name=label, description=desc, default=default)
            for name, label, desc, default in (
                ("fp_auto_sharp", "Auto: edge angle",
                 "Full auto sets the sharp-edge angle automatically", True),
                ("fp_auto_seam", "Auto: seam/material boundaries",
                 "Full auto splits islands at UV seams and material borders", True),
                ("fp_auto_merge", "Auto: merge small islands",
                 "Full auto merges tiny islands (0.02%)", True),
                ("fp_auto_part_tint", "Auto: part tint",
                 "Full auto separates touching parts by brightness bands", True),
                ("fp_auto_bone", "Auto: bone AOV by rig detection",
                 "Full auto enables the bone AOV when an armature is found", True),
                ("fp_auto_aa", "Auto: anti-aliasing",
                 "Full auto includes the anti-aliasing node", True),
                ("fp_auto_hashed", "Auto: BLEND to HASHED",
                 "Full auto converts BLEND materials (except real glass) to "
                 "HASHED so AOVs render", True),
                ("fp_auto_supersample", "Auto: 2x supersampling",
                 "Full auto enables 2x render + 50% output scaling. "
                 "Near-essential: FreePencil lines are too thick without it",
                 True),
                ("fp_auto_detect_aov", "Auto: AOVs from scene",
                 "Full auto owns the AOV setup: gen/mask/line follow whether "
                 "those vertex colors are painted, mat follows material ID. "
                 "STEP2 manual toggles are overridden while this is on", True),
                ("fp_auto_file_output", "Auto: enable File Output",
                 "Full auto also enables the STEP3 File Output node", False),
                ("fp_auto_white_preview", "Auto: white material preview",
                 "Full auto turns on the white material preview so the line "
                 "art is visible right after setup. Materials are untouched "
                 "(the compositor is switched); turn it off to see the "
                 "original materials", True),
            )
        },
        "fp_supersample": BoolProperty(
            name="2x supersampling (thin lines)",
            description=(
                "Render at 200% resolution and scale the compositor output "
                "back to 50%, turning 2px lines into crisp 1px lines. "
                "Applies to the Composite output and File Output slots"
            ),
            default=False
        ),
        "fp_preview_mode": EnumProperty(
            name="Preview",
            description=(
                "What to show under the lines. Both work the same way: "
                "they change what feeds the node group, so materials are "
                "never touched"
            ),
            items=[
                ('NONE', t("Materials"),
                 t("Show the scene as it is, with lines on top")),
                ('WHITE', t("White"),
                 t("Flat white under the lines. Pure line art")),
                ('MONO_LIGHT', t("Mono (diffuse light)"),
                 t("Grey shading from the diffuse light, with lines on "
                   "top. Texture patterns are not carried over")),
            ],
            default='NONE',
            update=_update_preview_mode
        ),
        "fp_mono_floor": FloatProperty(
            name="Shadow floor",
            description=(
                "How dark the shadows may get in mono preview. "
                "0 crushes them to black and the lines disappear"
            ),
            default=0.25, min=0.0, max=0.9, step=5, precision=2,
            update=_update_preview_mode
        ),
        "fp_white_preview": BoolProperty(
            name="White material preview",
            description=(
                "Temporarily replace all materials with a flat white "
                "emission (AOV-enabled) to preview pure line art. "
                "Original materials are backed up per object and fully "
                "restored when turned off"
            ),
            default=False,
            update=_update_white_preview
        ),
        "fp_white_keep_glass": BoolProperty(
            name="Keep glass transparent",
            description=(
                "While white preview is on, leave real glass materials "
                "(Transmission / low Alpha) untouched so you can still "
                "see through windows"
            ),
            default=True,
            update=_update_white_keep_glass
        ),
        "fp_file_output": BoolProperty(
            name="File Output",
            description=(
                "Add a File Output node to the generated compositor tree "
                "that writes the selected passes as PNGs"
            ),
            default=False
        ),
        # どのパスを書き出すかは個別に選ぶ。影は EEVEE だとノイズが多く
        # 使えないことが多いので既定 OFF、ディフューズ直接光を既定 ON。
        "fp_fo_line": BoolProperty(
            name="Write line pass",
            description="Write the line art to line.png",
            default=True
        ),
        "fp_fo_color": BoolProperty(
            name="Write color pass",
            description="Write the flat color output to color.png",
            default=True
        ),
        "fp_fo_light": BoolProperty(
            name="Write light pass",
            description=(
                "Write the diffuse direct light pass to light.png. "
                "Easier to composite than the shadow pass"
            ),
            default=True
        ),
        "fp_fo_shadow": BoolProperty(
            name="Write shadow pass",
            description=(
                "Write the shadow pass to shadow.png. "
                "EEVEE's shadow pass is often noisy"
            ),
            default=False
        ),
        "fp_file_output_path": bpy.props.StringProperty(
            name="File Output path",
            description="Base path for the File Output node",
            default="//render/",
            subtype='DIR_PATH'
        ),
        "fp_include_antialiasing": BoolProperty(
            name="Include Anti-Aliasing Node",
            description="Insert Anti-Aliasing node before Composite",
            default=False,
        ),
        "fp_gen_color": BoolProperty(
            name="generator color",
            description="AOV Generator Color",
            default=False
        ),
        "fp_mask_color": BoolProperty(
            name="mask color",
            description="AOV Mask Color(White erases lines)",
            default=False
        ),
        "fp_line_color": BoolProperty(
            name="line color",
            description="AOV Line Color",
            default=False
        ),
        "fp_mat_color": BoolProperty(
            name="material color",
            description="AOV Material Boundary Color",
            default=False
        ),
        "fp_bone_color": BoolProperty(
            name="bone color",
            description="AOV Bone Color",
            default=False
        ),
        "fp_color_noise_scale": FloatProperty(
            name="Color noise scale",
            description="Increasing the scale scatters island colors more randomly.",
            default=1.0,
            min=0.01,
            max=10.0,
            step=0.1,
            precision=2,
            subtype='FACTOR'
        ),
        "fp_min_neighbor_color_distance": FloatProperty(
            name="Min color distance",
            description="Minimum RGB distance between neighboring islands (0–1.732). Lower values allow similar colors.",
            default=0.5,
            min=0.0,
            max=1.732,
            step=0.01,
            precision=2
        ),
        "fp_max_color_retries": IntProperty(
            name="Max color retries",
            description="How many times to retry when a color already exists",
            default=30,
            min=1,
            max=200
        ),
        "fp_use_random_seed": BoolProperty(
            name="Random seed each run",
            description=(
                "Generate a new random seed every run. "
                "Turn this off to reproduce exactly the same island colors."
            ),
            default=True
        ),
        "fp_color_seed": IntProperty(
            name="Color seed",
            description=(
                "Seed for island color generation. "
                "The same seed with the same mesh reproduces the same colors."
            ),
            default=0,
            min=0,
            max=2147483647
        ),
        "fp_bone_grouping_mode": EnumProperty(
            name=t("Bone color grouping"),
            description=t("How to group bone names when coloring bone_color"),
            items=[
                ('exact', t("Exact"), t("Use the bone/vertex-group name as-is")),
                ('basename', t("Basename (.###)"), t("Treat suffix like .001 as the same")),
                ('stripdigits', t("Strip trailing digits"), t("Ignore trailing digits even without dot")),
            ],
            default='basename',
        ),
        "fp_part_tint": BoolProperty(
            name="Part tint (mecha color)",
            description=(
                "Give touching parts (objects) different brightness bands "
                "in mecha_color so part boundaries (hairline, collar) become "
                "lines; bone_color stays a pure weight blend and the node "
                "composites both channels"
            ),
            default=True
        ),
        "fp_bone_hard_names": bpy.props.StringProperty(
            name="Hard boundary bones",
            description=(
                "Comma-separated bone names whose region boundary should be "
                "a hard step in bone_color (so a line appears there, e.g. "
                "'head' for a chin line). Empty = all soft blending"
            ),
            default=""
        ),
        "fp_half_color": FloatVectorProperty(
            name="Half mask color",
            description="Color used by Half Fill",
            subtype='COLOR',
            size=4,
            min=0.0,
            max=1.0,
            default=(1.0, 0.0, 0.0, 1.0)
        )
    }

    for prop_name, prop_value in props_to_register.items():
        if not hasattr(bpy.types.Scene, prop_name):
            setattr(scene, prop_name, prop_value)
            logger.info(f"Registered property: {prop_name}")
        else:
            logger.info(f"Property already exists: {prop_name}")

    # カメラ一括レンダリング対象のチェック(オブジェクト単位)
    if not hasattr(bpy.types.Object, "fp_cam_render"):
        bpy.types.Object.fp_cam_render = BoolProperty(
            name="Render this camera",
            description=(
                "Include this camera in FreePencil's "
                "'Render checked cameras' batch"
            ),
            default=True
        )

def unregister_props():
    """プロパティを解除する関数"""
    scene = bpy.types.Scene
    props_to_clear = [
        "fp_sharp_edges", "fp_sharp_auto", "fp_auto_split_floor",
        "fp_seam_boundaries",
        "fp_min_island_area_pct", "fp_sharp_clear",
        "fp_ridge_amount", "fp_ridge_radius",
        "fp_curve_blur", "fp_curve_blur_angle", "fp_curve_blur_auto",
        "fp_color_type", "fp_mat_count",
        "fp_gen_color", "fp_mask_color", "fp_line_color",
        "fp_mat_color", "fp_bone_color", "fp_enable_compositor_view",
        "fp_include_antialiasing", "fp_line_sensitivity",
        "fp_line_weight", "fp_lw_island_bias", "fp_lw_line_bias", "fp_lw_strength", "fp_lw_bin", "fp_lw_gain", "fp_lw_tone", "fp_lw_deep_thick",
        "fp_lw_ao_dist", "fp_lw_ao_blur", "fp_lw_crowd",
        "fp_lw_crowd_radius", "fp_lw_crowd_threshold", "fp_lw_e1", "fp_lw_e2", "fp_lw_e3", "fp_lw_e4",
        "fp_far_relief", "fp_far_relief_radius", "fp_far_relief_threshold",
        "fp_ch_mecha", "fp_ch_depth", "fp_ch_bone", "fp_ch_gen", "fp_ch_mat",
        "fp_file_output", "fp_file_output_path",
        "fp_fo_line", "fp_fo_color", "fp_fo_light", "fp_fo_shadow",
        "fp_white_preview", "fp_preview_mode", "fp_mono_floor",
        "fp_white_keep_glass", "fp_supersample",
        "fp_auto_sharp", "fp_auto_seam", "fp_auto_merge", "fp_auto_part_tint",
        "fp_auto_bone", "fp_auto_aa", "fp_auto_hashed", "fp_auto_file_output",
        "fp_auto_detect_aov", "fp_auto_supersample", "fp_auto_white_preview",
        "fp_auto_style",
        "fp_color_noise_scale", "fp_min_neighbor_color_distance",
        "fp_max_color_retries",
        "fp_use_random_seed", "fp_color_seed",
        "fp_bone_grouping_mode", "fp_bone_hard_names", "fp_part_tint",
        "fp_node_type",
        "fp_half_color"
    ]
    
    for prop_name in props_to_clear:
        if hasattr(scene, prop_name):
            try:
                delattr(scene, prop_name)
                logger.info(f"Cleared property: {prop_name}")
            except AttributeError:
                logger.exception(f"Failed to clear property: {prop_name}")
        else:
            logger.info(f"Property does not exist: {prop_name}")

    if hasattr(bpy.types.Object, "fp_cam_render"):
        try:
            delattr(bpy.types.Object, "fp_cam_render")
        except AttributeError:
            logger.exception("Failed to clear property: fp_cam_render")
