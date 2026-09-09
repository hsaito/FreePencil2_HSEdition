"""角度を上げて耳を直し、口は稜線の起伏で取り戻せるかを試す。

角度ひとつでは口と耳を両立できないことが分かっている(1度刻みで確認:
口は10->11度で消え、耳は13->14度で直る)。境界の二面角で採点する案も
逆効果だった(耳14.89度 > 口11.98度)。

そこで役割を分ける。島を切る角度は「はっきりした折れ」だけに使い、
なめらかな折れは稜線の起伏で拾う。稜線は島を割らずに面の中へ起伏を
足す仕組みなので、もともと役割が違う。

実測(スザンヌ サブサーフ2適用):
     5度 稜線0.25(現状)   口○  耳×(面を横切る線)
    14度 稜線0.25         口×  耳○
    14度 稜線0.45         口○  耳○   <- これ
    14度 稜線0.45 距離0.03 口△  耳○

  blender -b --factory-startup --python eval_floor_ridge.py
"""
import sys, math
from pathlib import Path
HERE = Path(r"E:/10_cowork/00_code/22_FreePencil/dev/note_assets")
OUT = HERE/"out"/"floor_ridge"
sys.argv = ["blender","--","--out",str(OUT),"--res","1200","--ss","1"]
sys.path.insert(0,str(HERE))
import make_demo_movie as dm, bpy, fp_batch
from mathutils import Vector
dm.OUT = OUT; OUT.mkdir(parents=True, exist_ok=True)
fp_batch.install_addon()

VIEWS = {"ear": (208.0, 12.0, Vector((1.25,0,0.35)), 2.4),
         "face": (20.0, 8.0, Vector((0,0,0.1)), 5.2)}

def run(floor, ridge, radius, tag):
    for vn,(az,el,tgt,d) in VIEWS.items():
        bpy.ops.wm.read_homefile(use_empty=True)
        bpy.ops.mesh.primitive_monkey_add()
        o=bpy.context.object
        m=o.modifiers.new("S","SUBSURF"); m.levels=m.render_levels=2
        bpy.ops.object.modifier_apply(modifier=m.name); bpy.ops.object.shade_smooth()
        dm.grey([o])
        sc=bpy.context.scene
        cd=bpy.data.cameras.new("C"); cd.lens=70.0; cd.clip_end=100
        cam=bpy.data.objects.new("C",cd); sc.collection.objects.link(cam); sc.camera=cam
        a,e=math.radians(az),math.radians(el)
        cam.location=(tgt.x+math.sin(a)*math.cos(e)*d, tgt.y-math.cos(a)*math.cos(e)*d,
                      tgt.z+math.sin(e)*d)
        cam.rotation_euler=(tgt-Vector(cam.location)).to_track_quat("-Z","Y").to_euler()
        w=bpy.data.worlds.new("W"); w.use_nodes=True; sc.world=w
        lt=bpy.data.lights.new("K",type="SUN"); lo=bpy.data.objects.new("K",lt)
        sc.collection.objects.link(lo); lo.rotation_euler=(math.radians(62),0,math.radians(40))
        for p in ("fp_use_random_seed","fp_enable_compositor_view",
                  "fp_auto_detect_aov","fp_auto_white_preview","fp_auto_supersample"):
            setattr(sc,p,False)
        sc.fp_white_preview=True; sc.fp_supersample=False
        sc.fp_auto_split_floor=floor
        sc.fp_auto_merge=False
        sc.fp_min_island_area_pct=1.0
        sc.fp_ridge_amount=ridge
        sc.fp_ridge_radius=radius
        bpy.ops.object.select_all(action="DESELECT"); o.select_set(True)
        bpy.context.view_layer.objects.active=o
        bpy.ops.freepencil.auto_setup("EXEC_DEFAULT")
        sc.fp_white_preview=True
        sc.render.engine=fp_batch.eevee_engine(); sc.eevee.taa_render_samples=16
        sc.render.resolution_percentage=100
        sc.render.resolution_x=2400; sc.render.resolution_y=2400
        sc.render.image_settings.file_format="PNG"
        sc.render.image_settings.color_mode="RGBA"; sc.render.film_transparent=True
        fp_batch.render_still(sc, OUT/f"{vn}_{tag}.png", 2)
    print(f"@@@ {tag} 完了", flush=True)

run(5.0,  0.25, 0.08, "base")            # 現状
run(14.0, 0.25, 0.08, "f14_r025")        # 角度だけ上げる
run(14.0, 0.45, 0.08, "f14_r045")        # 稜線を強く
run(14.0, 0.45, 0.03, "f14_r045_s")      # 稜線を強く・細かく
