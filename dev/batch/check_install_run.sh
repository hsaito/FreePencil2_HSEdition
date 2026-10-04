#!/usr/bin/env bash
# check_install.py を段ごとに別の Blender プロセスで回す。プロファイルは毎回空から作る。
#   bash check_install_run.sh <新ZIP> <v2.7 ZIP> <出力の親フォルダ> <作業用の親フォルダ>
set -u
NEW=$1; OLD=$2; OUTROOT=$3; WORK=$4
HERE=$(cd "$(dirname "$0")" && pwd)
PY="$HERE/check_install.py"
w() { cygpath -w "$1"; }

run() {   # run <blender.exe> <profile> <out> args...
  local exe=$1 prof=$2 out=$3; shift 3
  BLENDER_USER_RESOURCES="$(w "$prof")" "$exe" -b --python "$(w "$PY")" -- --out "$(w "$out")" "$@" 2>&1 | grep "@@@"
}

for v in 4.2.3 4.3.2 4.5.2 5.2.0; do
  exe=/c/blender/blender-$v-windows-x64/blender.exe
  [ -x "$exe" ] || continue
  # A. 新規インストール
  prof="$WORK/prof_new_$v"; out="$OUTROOT/new_$v"; rm -rf "$prof" "$out"; mkdir -p "$prof" "$out"
  echo "== A $v 新規インストール"
  run "$exe" "$prof" "$out" --phase install --zip "$(w "$NEW")"
  run "$exe" "$prof" "$out" --phase version
  for st in PRECISE WEIGHTED BACKGROUND; do
    run "$exe" "$prof" "$out" --phase make --style $st --name "made_$st" --blend "$(w "$out")\\$st.blend"
  done
  # C. 保存して開き直す(手描き背景のファイルで)
  echo "== C $v 保存して開き直し"
  run "$exe" "$prof" "$out" --phase tweak --blend "$(w "$out")\\BACKGROUND.blend"
  run "$exe" "$prof" "$out" --phase reopen --blend "$(w "$out")\\BACKGROUND.blend"
done

for v in 4.5.2 5.2.0; do
  exe=/c/blender/blender-$v-windows-x64/blender.exe
  # B. v2.7 で作ったファイルを、2.8.1 に上書きしたあと開く
  prof="$WORK/prof_up_$v"; out="$OUTROOT/upgrade_$v"; rm -rf "$prof" "$out"; mkdir -p "$prof" "$out"
  echo "== B $v v2.7 -> 2.8.1"
  run "$exe" "$prof" "$out" --phase install --zip "$(w "$OLD")"
  run "$exe" "$prof" "$out" --phase version
  run "$exe" "$prof" "$out" --phase make --name made_v27 --blend "$(w "$out")\\v27.blend"
  run "$exe" "$prof" "$out" --phase install --zip "$(w "$NEW")"
  run "$exe" "$prof" "$out" --phase version
  run "$exe" "$prof" "$out" --phase touch --blend "$(w "$out")\\v27.blend"
done
echo "== done"
